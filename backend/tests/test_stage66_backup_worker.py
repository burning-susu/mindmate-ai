from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from mindmate.application import backup_worker as backup_worker_module
from mindmate.application import backups as backups_module
from mindmate.application.backup_worker import BackupCreationWorker
from mindmate.application.local_backup import create_backup_archive, verify_backup_archive
from mindmate.config import Settings
from mindmate.infrastructure.db import create_session_factory, create_sqlite_engine
from mindmate.infrastructure.models import (
    BackgroundTask,
    Backup,
    ContentObject,
    TaskAttempt,
    new_id,
)
from mindmate.main import create_app

ORIGIN = "http://127.0.0.1:5173"


def _make_app(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = Settings(data_dir=tmp_path, env="test", provider_mode="mock")
    return TestClient(create_app(settings), base_url="http://127.0.0.1"), settings


def _session_headers(client: TestClient, key: str | None = None) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "Idempotency-Key": key or str(uuid4())}


def _create_backup(client: TestClient, key: str | None = None):
    return client.post("/api/v1/backups", headers=_session_headers(client, key), json={})


def _wait_for_backup(client: TestClient, backup_id: str, expected: str = "COMPLETED") -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/backups/{backup_id}", headers={"Origin": ORIGIN})
        assert response.status_code == 200, response.text
        body = response.json()
        if body["status"] in {"COMPLETED", "FAILED"}:
            assert body["status"] == expected, body
            return body
        time.sleep(0.02)
    raise AssertionError(f"backup {backup_id} did not reach a terminal state")


def test_create_returns_while_worker_is_blocked_and_rejects_second_active_backup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _ = _make_app(tmp_path)
    started = threading.Event()
    release = threading.Event()
    original = backup_worker_module.create_backup_archive

    def blocked_create(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(backup_worker_module, "create_backup_archive", blocked_create)
    with client:
        key = str(uuid4())
        begin = time.monotonic()
        created = _create_backup(client, key)
        elapsed = time.monotonic() - begin
        assert created.status_code == 202, created.text
        body = created.json()
        assert body["status"] in {"QUEUED", "RUNNING"}
        assert elapsed < 1.0
        assert started.wait(2)

        repeated = _create_backup(client, key)
        assert repeated.status_code == 202
        assert repeated.json()["backup_id"] == body["backup_id"]

        blocked = _create_backup(client, str(uuid4()))
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "BACKUP_CREATE_IN_PROGRESS"

        listed = client.get("/api/v1/backups", headers={"Origin": ORIGIN})
        assert listed.status_code == 200
        assert listed.json()["items"][0]["backup_id"] == body["backup_id"]
        release.set()
        assert _wait_for_backup(client, body["backup_id"])["download_available"] is True
    release.set()


def test_worker_shutdown_waits_for_active_backup_to_finish(tmp_path: Path, monkeypatch) -> None:
    client, _ = _make_app(tmp_path)
    started = threading.Event()
    release = threading.Event()
    original = backup_worker_module.create_backup_archive

    def blocked_create(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(backup_worker_module, "create_backup_archive", blocked_create)
    with client:
        created = _create_backup(client)
        assert created.status_code == 202
        backup_id = created.json()["backup_id"]
        assert started.wait(2)
        stopper = threading.Thread(target=client.app.state.backup_worker.stop)
        stopper.start()
        time.sleep(0.05)
        assert stopper.is_alive()
        release.set()
        stopper.join(timeout=5)
        assert not stopper.is_alive()
        assert _wait_for_backup(client, backup_id)["status"] == "COMPLETED"
    release.set()


def test_retry_failed_backup_and_fail_closed_when_archive_disappears(tmp_path: Path) -> None:
    client, settings = _make_app(tmp_path)
    with client:
        content_id = new_id()
        relative = f"objects/{content_id[:2]}/{content_id}.txt"
        now = datetime.now(UTC)
        with client.app.state.session_factory() as session:
            session.add(
                ContentObject(
                    content_object_id=content_id,
                    sha256=hashlib.sha256(b"restored source").hexdigest(),
                    byte_size=15,
                    detected_mime_type="text/plain",
                    storage_relative_path=relative,
                    storage_state="READY",
                    reference_count=1,
                    created_at=now,
                    verified_at=now,
                )
            )
            session.commit()

        failed = _create_backup(client)
        assert failed.status_code == 202
        backup_id = failed.json()["backup_id"]
        _wait_for_backup(client, backup_id, expected="FAILED")

        source = settings.resolved_data_dir / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"restored source")
        retry_key = str(uuid4())
        retried = client.post(
            f"/api/v1/backups/{backup_id}/retry",
            headers=_session_headers(client, retry_key),
            json={},
        )
        assert retried.status_code == 202, retried.text
        assert retried.json()["backup_id"] == backup_id
        assert _wait_for_backup(client, backup_id)["download_available"] is True

        repeated = client.post(
            f"/api/v1/backups/{backup_id}/retry",
            headers=_session_headers(client, retry_key),
            json={},
        )
        assert repeated.status_code == 202
        assert repeated.json()["backup_id"] == backup_id

        archive_path = settings.resolved_data_dir / "backups" / next(
            path.name
            for path in (settings.resolved_data_dir / "backups").glob("*.mindmate-backup")
        )
        archive_path.unlink()
        download = client.get(
            f"/api/v1/backups/{backup_id}/download",
            headers={"Origin": ORIGIN},
        )
        assert download.status_code == 404
        assert str(tmp_path) not in download.text
        current = client.get(f"/api/v1/backups/{backup_id}", headers={"Origin": ORIGIN})
        assert current.json()["status"] == "FAILED"
        assert current.json()["download_available"] is False


def test_sequential_backups_keep_unique_archives_and_detect_manifest_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, settings = _make_app(tmp_path)
    fixed_time = datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(backups_module, "_now", lambda: fixed_time)
    with client:
        first = _create_backup(client)
        assert first.status_code == 202
        first_id = first.json()["backup_id"]
        _wait_for_backup(client, first_id)

        second = _create_backup(client)
        assert second.status_code == 202
        second_id = second.json()["backup_id"]
        _wait_for_backup(client, second_id)

        with client.app.state.session_factory() as session:
            first_row = session.get(Backup, first_id)
            second_row = session.get(Backup, second_id)
            assert first_row is not None and second_row is not None
            first_path = settings.resolved_data_dir / first_row.archive_relative_path
            second_path = settings.resolved_data_dir / second_row.archive_relative_path
            assert first_path != second_path
            second_payload = second_path.read_bytes()

        first_path.write_bytes(second_payload)
        rejected = client.get(f"/api/v1/backups/{first_id}/download", headers={"Origin": ORIGIN})
        assert rejected.status_code == 409
        assert str(tmp_path) not in rejected.text
        first_status = client.get(f"/api/v1/backups/{first_id}", headers={"Origin": ORIGIN})
        assert first_status.json()["status"] == "FAILED"
        second_download = client.get(
            f"/api/v1/backups/{second_id}/download",
            headers={"Origin": ORIGIN},
        )
        assert second_download.status_code == 200


def test_queued_backup_survives_worker_restart(tmp_path: Path) -> None:
    client, settings = _make_app(tmp_path)
    with client:
        client.app.state.backup_worker.stop()
        created = _create_backup(client)
        assert created.status_code == 202
        backup_id = created.json()["backup_id"]
        queued = client.get(f"/api/v1/backups/{backup_id}", headers={"Origin": ORIGIN})
        assert queued.json()["status"] == "QUEUED"

        restarted = BackupCreationWorker(
            client.app.state.session_factory,
            settings,
            worker_id="restarted-queued-worker",
        )
        assert restarted.run_once() is True
        assert _wait_for_backup(client, backup_id)["download_available"] is True


def test_expired_lease_reuses_verified_archive_and_cleans_stale_partial(tmp_path: Path, monkeypatch) -> None:
    client, settings = _make_app(tmp_path)
    with client:
        client.app.state.backup_worker.stop()
        created = _create_backup(client)
        assert created.status_code == 202
        backup_id = created.json()["backup_id"]
        factory = client.app.state.session_factory
        first_worker = BackupCreationWorker(factory, settings, worker_id="first-test-worker")
        task_id = first_worker._claim_one()
        assert task_id is not None
        competing_worker = BackupCreationWorker(factory, settings, worker_id="competing-test-worker")
        assert competing_worker._claim_one() is None

        with factory() as session:
            backup = session.get(Backup, backup_id)
            assert backup is not None
            destination = settings.resolved_data_dir / backup.archive_relative_path
            schema_version = backup.schema_version
        manifest = create_backup_archive(settings.resolved_data_dir, destination, schema_version)
        assert manifest["file_count"] >= 1
        partial = destination.parent / "mindmate-backup-stale.partial"
        partial.write_bytes(b"partial archive")
        with factory() as session:
            task = session.get(BackgroundTask, task_id)
            assert task is not None
            task.lease_until = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()

        def unexpected_rebuild(*_args, **_kwargs):
            raise AssertionError("a complete verified archive should have been reused")

        monkeypatch.setattr(backup_worker_module, "create_backup_archive", unexpected_rebuild)
        recovered = BackupCreationWorker(factory, settings, worker_id="second-test-worker")
        assert recovered.run_once() is True
        with factory() as session:
            backup = session.get(Backup, backup_id)
            task = session.get(BackgroundTask, task_id)
            attempts = list(
                session.scalars(
                    select(TaskAttempt)
                    .where(TaskAttempt.task_id == task_id)
                    .order_by(TaskAttempt.attempt_number)
                )
            )
        assert backup is not None and backup.status == "COMPLETED"
        assert task is not None and task.status == "COMPLETED"
        assert [attempt.status for attempt in attempts] == ["INTERRUPTED", "COMPLETED"]
        assert not partial.exists()
        assert verify_backup_archive(destination)["file_count"] == backup.file_count


def test_process_restart_takes_over_partial_archive_and_verifies_completion(tmp_path: Path) -> None:
    data_root = tmp_path / "isolated-data"
    crash_signal = tmp_path / "crash-worker-entered-archive.txt"
    done_signal = tmp_path / "restarted-worker-completed.txt"
    error_signal = tmp_path / "worker-error.txt"
    client, settings = _make_app(data_root)
    with client:
        client.app.state.backup_worker.stop()
        created = _create_backup(client)
        assert created.status_code == 202
        backup_id = created.json()["backup_id"]

    script = """
import sys, time
from pathlib import Path
from mindmate.application import backup_worker as worker_module
from mindmate.application.backup_worker import BackupCreationWorker
from mindmate.config import Settings
from mindmate.infrastructure.db import create_session_factory, create_sqlite_engine
from mindmate.infrastructure.models import Backup

root, mode, signal, error_signal = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
try:
    settings = Settings(data_dir=root, env='test', provider_mode='mock')
    engine = create_sqlite_engine(settings.database_path)
    factory = create_session_factory(engine)
    if mode == 'crash':
        def interrupted_archive(_source, destination, _schema, **_kwargs):
            (destination.parent / 'mindmate-backup-process.partial').write_bytes(b'incomplete')
            signal.write_text('writing', encoding='utf-8')
            while True:
                time.sleep(0.1)
        worker_module.create_backup_archive = interrupted_archive
    worker = BackupCreationWorker(factory, settings, worker_id=f'process-{mode}', poll_seconds=0.02, lease_seconds=1)
    worker.start()
    if mode == 'wait':
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with factory() as session:
                row = session.scalar(__import__('sqlalchemy').select(Backup).order_by(Backup.created_at.desc()).limit(1))
                status = row.status if row else None
            if status == 'COMPLETED':
                signal.write_text('completed', encoding='utf-8')
                worker.stop()
                engine.dispose()
                raise SystemExit(0)
            if status == 'FAILED':
                raise RuntimeError('backup ended in FAILED')
            time.sleep(0.02)
        raise TimeoutError('worker did not finish after restart')
    while True:
        time.sleep(0.1)
except SystemExit:
    raise
except BaseException as exc:
    error_signal.write_text(f'{type(exc).__name__}: {exc}', encoding='utf-8')
    raise
"""
    env = os.environ.copy()
    source_dir = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = source_dir + os.pathsep + env.get("PYTHONPATH", "")

    first = subprocess.Popen(
        [sys.executable, "-c", script, str(data_root), "crash", str(crash_signal), str(error_signal)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    second = None
    parent_engine = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not crash_signal.exists():
            if first.poll() is not None:
                break
            time.sleep(0.02)
        assert crash_signal.exists(), error_signal.read_text(encoding="utf-8") if error_signal.exists() else "first worker did not reach archive write"
        first.terminate()
        first.wait(timeout=5)

        parent_engine = create_sqlite_engine(settings.database_path)
        factory = create_session_factory(parent_engine)
        second = subprocess.Popen(
            [sys.executable, "-c", script, str(data_root), "wait", str(done_signal), str(error_signal)],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not done_signal.exists():
            if second.poll() is not None:
                break
            time.sleep(0.05)
        assert done_signal.exists(), error_signal.read_text(encoding="utf-8") if error_signal.exists() else "restarted worker did not complete"
        second.wait(timeout=5)

        with factory() as session:
            backup = session.scalar(select(Backup).where(Backup.backup_id == backup_id))
            tasks = list(session.scalars(select(BackgroundTask).where(BackgroundTask.task_type == "BACKUP_CREATE")))
            task = next(
                item
                for item in tasks
                if isinstance(item.checkpoint_json, dict)
                and item.checkpoint_json.get("backup_id") == backup_id
            )
            attempts = list(
                session.scalars(
                    select(TaskAttempt)
                    .where(TaskAttempt.task_id == task.task_id)
                    .order_by(TaskAttempt.attempt_number)
                )
            )
            assert backup is not None and backup.status == "COMPLETED"
            assert task.status == "COMPLETED"
            assert len(attempts) == 2
            assert attempts[0].status == "INTERRUPTED"
            assert attempts[1].status == "COMPLETED"
            archive_path = data_root / backup.archive_relative_path
        assert verify_backup_archive(archive_path)["file_count"] == backup.file_count
        assert not list((data_root / "backups").glob("*.partial"))
    finally:
        for process in (first, second):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        if parent_engine is not None:
            parent_engine.dispose()
