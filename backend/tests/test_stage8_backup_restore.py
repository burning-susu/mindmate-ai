"""Isolated full-restore checks. Live data stays readable when a switch fails."""

from __future__ import annotations

import hashlib
import io
import sqlite3
import threading
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import mindmate.application.local_restore as local_restore_module
from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.application.local_backup import BackupBuildError
from mindmate.application.local_restore import (
    CONFIRM_PHRASE,
    apply_pending_restore,
    inspect_restore_archive,
    swap_tree,
)
from mindmate.application.provider_configuration import DEEPSEEK_SECRET_REFERENCE
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    ChunkingConfig,
    ContentObject,
    EmbeddingConfig,
    IndexVersion,
    KnowledgeBase,
    new_id,
)
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore

ORIGIN = "http://127.0.0.1:5173"

SECRET = "fixture-restore-secret-do-not-pack"
_APP_WORKER_THREAD_PREFIXES = (
    "mindmate-",
    "history-search-backfill",
    "history-trash-purge",
    "task-retention-purge",
)


def _make_app(tmp_path: Path) -> tuple[TestClient, InMemoryCredentialStore, Settings]:
    settings = Settings(data_dir=tmp_path, env="test", provider_base_url="https://fixture.invalid")
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model=DEEPSEEK_MODEL,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}, request=request)),
    )
    return TestClient(app, base_url="http://127.0.0.1"), store, settings


def _assert_test_app_released(client: TestClient) -> None:
    app = cast(Any, client.app)
    engine = getattr(app.state, "engine", None)
    checked_out_before = engine.pool.checkedout() if engine is not None else 0
    deadline = time.monotonic() + 10
    active = [
        thread
        for thread in threading.enumerate()
        if thread.name.startswith(_APP_WORKER_THREAD_PREFIXES)
    ]
    waited_for: set[str] = set()
    while active and time.monotonic() < deadline:
        waited_for.update(thread.name for thread in active)
        for thread in active:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        active = [thread for thread in active if thread.is_alive()]
    assert not active, f"应用 Worker 未退出：{sorted(thread.name for thread in active)}"

    if engine is not None:
        checked_out_after = engine.pool.checkedout()
        assert checked_out_after == 0
        if waited_for or checked_out_before:
            print(
                "APP_SHUTDOWN_DIAGNOSTIC "
                f"waited_for={sorted(waited_for)} checked_out_before={checked_out_before} "
                f"checked_out_after={checked_out_after}"
            )
        engine.dispose()


def _session_headers(client: TestClient, *, idempotency: str | None = None) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "Idempotency-Key": idempotency or str(uuid4())}


def _seed_content_object(session: Session, settings: Settings, payload: bytes) -> ContentObject:
    now = datetime.now(UTC)
    content_id = new_id()
    relative = f"objects/{content_id[:2]}/{content_id}.txt"
    absolute = settings.resolved_data_dir / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(payload)
    row = ContentObject(
        content_object_id=content_id,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        detected_mime_type="text/plain",
        storage_relative_path=relative,
        storage_state="READY",
        reference_count=1,
        created_at=now,
        verified_at=now,
    )
    session.add(row)
    session.commit()
    return row


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _download_archive(client: TestClient) -> tuple[str, bytes]:
    headers = _session_headers(client)
    created = client.post("/api/v1/backups", headers=headers, json={})
    assert created.status_code == 202, created.text
    backup_id = created.json()["backup_id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/backups/{backup_id}", headers={"Origin": ORIGIN})
        assert status.status_code == 200, status.text
        if status.json()["status"] in {"COMPLETED", "FAILED"}:
            assert status.json()["status"] == "COMPLETED", status.text
            break
        time.sleep(0.02)
    else:
        raise AssertionError(f"backup {backup_id} did not complete")
    downloaded = client.get(f"/api/v1/backups/{backup_id}/download", headers={"Origin": ORIGIN})
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content[:2] == b"PK"
    assert SECRET.encode() not in downloaded.content
    return backup_id, downloaded.content


def _upload(client: TestClient, payload: bytes, name: str = "sample.mindmate-backup") -> dict:
    response = client.post(
        "/api/v1/backups/restore/uploads",
        headers=_session_headers(client),
        files={"archive": (name, payload, "application/zip")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "\\" not in response.text or "Users" not in response.text
    return body


def _precheck(client: TestClient, upload_id: str) -> httpx.Response:
    return client.post(
        "/api/v1/backups/restore/prechecks",
        headers=_session_headers(client),
        json={"upload_id": upload_id},
    )


def _execute(
    client: TestClient,
    precheck_id: str,
    *,
    phrase: str = CONFIRM_PHRASE,
    confirm: bool = True,
    idempotency: str | None = None,
) -> httpx.Response:
    return client.post(
        "/api/v1/backups/restore/executions",
        headers=_session_headers(client, idempotency=idempotency),
        json={
            "precheck_id": precheck_id,
            "confirm_full_replace": confirm,
            "confirm_phrase": phrase,
        },
    )


def _seed_ready_index(client: TestClient) -> str:
    now = datetime.now(UTC)
    knowledge_base_id = new_id()
    chunking_id = new_id()
    embedding_id = new_id()
    version_id = new_id()
    with client.app.state.session_factory() as session:
        session.add(
            KnowledgeBase(
                knowledge_base_id=knowledge_base_id,
                name="恢复前知识库",
                status="READY",
                active_index_version_id=None,
                created_at=now,
                updated_at=now,
                row_version=1,
            )
        )
        session.add(
            ChunkingConfig(
                chunking_config_id=chunking_id,
                config_version="v1",
                algorithm_id="fixture",
                measurement_unit="chars",
                target_size=100,
                min_size=10,
                max_size=200,
                overlap_size=0,
                structure_rules_hash="a" * 64,
                config_fingerprint=(chunking_id.replace("-", "") + "abcdabcdabcdabcdabcdabcdabcd"),
                created_at=now,
            )
        )
        session.add(
            EmbeddingConfig(
                embedding_config_id=embedding_id,
                config_version="v1",
                provider_type="local",
                model_name="fixture",
                model_revision="fixture",
                vector_dimension=512,
                normalization=True,
                distance_metric="cosine",
                config_fingerprint=(embedding_id.replace("-", "") + "abcdabcdabcdabcdabcdabcdabcd"),
                created_at=now,
            )
        )
        session.flush()
        session.add(
            IndexVersion(
                index_version_id=version_id,
                scope_type="KNOWLEDGE_BASE",
                scope_id=knowledge_base_id,
                parse_revision_set_hash="b" * 64,
                chunking_config_id=chunking_id,
                embedding_config_id=embedding_id,
                vector_engine="sqlite-vec",
                vector_engine_version="fixture",
                status="READY",
                preprocessing_status="COMPLETED",
                chunking_status="COMPLETED",
                embedding_status="COMPLETED",
                fts_status="COMPLETED",
                input_count=1,
                prepared_count=1,
                skipped_count=0,
                failed_count=0,
                created_at=now,
            )
        )
        session.flush()
        knowledge = session.get(KnowledgeBase, knowledge_base_id)
        assert knowledge is not None
        knowledge.active_index_version_id = version_id
        session.commit()
    return version_id


def test_restore_replaces_dataset_keeps_recovery_point_and_blocks_outbound(tmp_path: Path) -> None:
    sentinel = tmp_path.parent / f"sentinel-{tmp_path.name}.txt"
    sentinel.write_text("outside-root", encoding="utf-8")
    calls: list[str] = []

    def _transport(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"ok": True}, request=request)

    client, store, settings = _make_app(tmp_path)
    client.app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model="deepseek-flash",
        transport=httpx.MockTransport(_transport),
    )
    store.set_secret(DEEPSEEK_SECRET_REFERENCE, SECRET)
    alpha = b"alpha-dataset-v1"
    beta = b"beta-dataset-v2"
    with client:
        with client.app.state.session_factory() as session:
            _seed_content_object(session, settings, alpha)
        version_id = _seed_ready_index(client)
        _download_id, archive = _download_archive(client)
        with client.app.state.session_factory() as session:
            _seed_content_object(session, settings, beta)
        marker = settings.vectors_dir / "old-generation.bin"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"old-vectors")
        uploaded = _upload(client, archive)
        precheck = _precheck(client, uploaded["upload_id"])
        assert precheck.status_code == 200, precheck.text
        summary = precheck.json()["summary"]
        assert summary["executable"] is True
        assert summary["includes"]["secrets"] is False
        assert summary["includes"]["vectors"] is False
        assert "整份" in summary["overwrite_scope"]
        assert str(tmp_path) not in precheck.text
        refused = _execute(client, precheck.json()["precheck_id"], phrase="不确认", confirm=False)
        assert refused.status_code == 400
        assert refused.json()["code"] == "RESTORE_CONFIRMATION_REQUIRED"
        confirm_key = str(uuid4())
        confirmed = _execute(client, precheck.json()["precheck_id"], idempotency=confirm_key)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["restart_required"] is True
        repeated = _execute(client, precheck.json()["precheck_id"], idempotency=confirm_key)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["execution_id"] == confirmed.json()["execution_id"]
        blocked = client.post("/api/v1/backups", headers=_session_headers(client), json={})
        assert blocked.status_code == 423
        assert blocked.json()["code"] == "RESTORE_WRITES_FROZEN"
        recovery_id = confirmed.json()["recovery_point_id"]

    _assert_test_app_released(client)
    client2, store2, settings2 = _make_app(tmp_path)
    store2.set_secret(DEEPSEEK_SECRET_REFERENCE, SECRET)
    client2.app.state.credential_store = store2
    client2.app.state.deepseek_provider = client.app.state.deepseek_provider
    with client2:
        status = client2.get("/api/v1/backups/restore/status", headers={"Origin": ORIGIN})
        assert status.status_code == 401
        headers = _session_headers(client2)
        status = client2.get("/api/v1/backups/restore/status", headers={"Origin": ORIGIN})
        assert status.status_code == 200, status.text
        body = status.json()
        assert body["phase"] == "SUCCEEDED"
        assert body["index_outcome"] == "NEEDS_REBUILD"
        assert body["provider_reconfirm_required"] is True
        assert str(tmp_path) not in status.text
        with client2.app.state.session_factory() as session:
            rows = session.execute(
                __import__("sqlalchemy").text("SELECT storage_relative_path FROM content_objects")
            ).all()
            payloads = [
                (settings2.resolved_data_dir / row[0]).read_bytes()
                for row in rows
                if (settings2.resolved_data_dir / row[0]).is_file()
            ]
            version = session.get(IndexVersion, version_id)
            knowledge = session.get(KnowledgeBase, version.scope_id if version else "")
            creating = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT COUNT(*) FROM backups WHERE status IN ('CREATING', 'RUNNING', 'QUEUED')"
                )
            ).scalar_one()
        assert alpha in payloads
        assert beta not in payloads
        assert version is not None
        assert version.status == "NEEDS_REBUILD"
        assert version.activation_error_code == "RESTORE_INDEX_NOT_REUSABLE"
        assert knowledge is not None
        assert knowledge.active_index_version_id is None
        assert creating == 0
        assert not (settings2.vectors_dir / "old-generation.bin").exists()
        aside_marker = list((settings2.runtime_dir / "restore-control" / "aside").rglob("old-generation.bin"))
        assert aside_marker
        recovery_db = settings2.resolved_data_dir / "recovery-points" / recovery_id / "database" / "mindmate.db"
        assert recovery_db.is_file()
        probe = client2.post(
            "/api/v1/ai/provider/test",
            headers=headers,
            json={"confirm_external_transfer": True},
        )
        assert probe.status_code == 409
        assert probe.json()["code"] == "RESTORE_PROVIDER_RECONFIRM_REQUIRED"
        assert calls == []
        assert store2.get_secret(DEEPSEEK_SECRET_REFERENCE) == SECRET
        mode = client2.post(
            "/api/v1/ai/provider/generation-mode",
            headers=_session_headers(client2),
            json={"mode": "deepseek"},
        )
        assert mode.status_code == 409
    _assert_test_app_released(client2)
    assert sentinel.read_text(encoding="utf-8") == "outside-root"


def test_cancel_and_bad_archives_do_not_change_live_data(tmp_path: Path) -> None:
    client, _, settings = _make_app(tmp_path)
    payload = b"keep-me"
    with client:
        with client.app.state.session_factory() as session:
            row = _seed_content_object(session, settings, payload)
        _, archive = _download_archive(client)
        uploaded = _upload(client, archive)
        precheck = _precheck(client, uploaded["upload_id"])
        assert precheck.status_code == 200, precheck.text
        cancelled = client.post("/api/v1/backups/restore/cancel", headers=_session_headers(client))
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["phase"] == "CANCELLED"
        assert (settings.resolved_data_dir / row.storage_relative_path).read_bytes() == payload

        def reject(name: str, blob: bytes) -> str:
            uploaded_bad = client.post(
                "/api/v1/backups/restore/uploads",
                headers=_session_headers(client),
                files={"archive": (name, blob, "application/zip")},
            )
            assert uploaded_bad.status_code == 200, uploaded_bad.text
            checked = _precheck(client, uploaded_bad.json()["upload_id"])
            assert checked.status_code >= 400, checked.text
            assert str(tmp_path) not in checked.text
            return checked.json()["code"]

        assert reject("slip.mindmate-backup", _zip({"../outside.txt": b"pwn"})) == "BACKUP_PATH_INVALID"
        assert reject("case.mindmate-backup", _zip({"objects/A.txt": b"a", "objects/a.txt": b"b"})) == "BACKUP_CASE_COLLISION"
        bomb = _zip_bytes(_compressible_bomb())
        assert reject("bomb.mindmate-backup", bomb) == "BACKUP_COMPRESSION_SUSPECT"
        link = _symlink_zip()
        assert reject("link.mindmate-backup", link) == "BACKUP_SYMLINK_REJECTED"
        assert (settings.resolved_data_dir / row.storage_relative_path).read_bytes() == payload
        outside = tmp_path.parent / "outside.txt"
        assert not outside.exists()


def test_schema_space_permission_lock_migration_and_interrupt(tmp_path: Path, monkeypatch) -> None:
    client, _, settings = _make_app(tmp_path)
    payload = b"original-live"
    with client:
        with client.app.state.session_factory() as session:
            row = _seed_content_object(session, settings, payload)
        relative = row.storage_relative_path
        _, archive = _download_archive(client)
        with sqlite3.connect(settings.database_path.as_posix()) as conn:
            conn.execute("UPDATE alembic_version SET version_num = 'ffffffffffffffff'")
            conn.commit()
        _, newer = _download_archive(client)
        uploaded = _upload(client, newer)
        newer_check = _precheck(client, uploaded["upload_id"])
        assert newer_check.status_code == 400, newer_check.text
        assert newer_check.json()["code"] == "BACKUP_SCHEMA_NEWER"
        monkeypatch.setattr("mindmate.application.local_restore.free_bytes", lambda _path: 1)
        uploaded_space = _upload(client, archive)
        space = _precheck(client, uploaded_space["upload_id"])
        assert space.status_code == 409
        assert space.json()["code"] == "RESTORE_DISK_SPACE"
        monkeypatch.undo()

        def _deny(_directory: Path) -> None:
            raise BackupBuildError("RESTORE_NOT_WRITABLE", "数据目录不可写，已停止恢复。")

        monkeypatch.setattr("mindmate.application.local_restore.assert_writable", _deny)
        uploaded_perm = _upload(client, archive)
        denied = _precheck(client, uploaded_perm["upload_id"])
        assert denied.status_code == 400
        assert denied.json()["code"] == "RESTORE_NOT_WRITABLE"
        monkeypatch.undo()
        assert (settings.resolved_data_dir / relative).read_bytes() == payload

        uploaded_ok = _upload(client, archive)
        ready = _precheck(client, uploaded_ok["upload_id"])
        assert ready.status_code == 200, ready.text
        with client.app.state.session_factory() as session:
            _seed_content_object(session, settings, b"changed-after-precheck")
        changed = _execute(client, ready.json()["precheck_id"])
        assert changed.status_code == 409
        assert changed.json()["code"] == "RESTORE_DATA_CHANGED"
        assert (settings.resolved_data_dir / relative).read_bytes() == payload


def test_locked_database_and_interrupted_switch_keep_original(tmp_path: Path, monkeypatch) -> None:
    sentinel = tmp_path.parent / f"sentinel-{tmp_path.name}.txt"
    sentinel.write_text("outside-root", encoding="utf-8")
    client, _, settings = _make_app(tmp_path)
    payload = b"locked-original"
    original_hash = _sha(payload)
    with client:
        with client.app.state.session_factory() as session:
            row = _seed_content_object(session, settings, payload)
        relative = row.storage_relative_path
        _, archive = _download_archive(client)
        with client.app.state.session_factory() as session:
            _seed_content_object(session, settings, b"after-backup")
        uploaded = _upload(client, archive)
        precheck = _precheck(client, uploaded["upload_id"])
        assert precheck.status_code == 200, precheck.text
        confirmed = _execute(client, precheck.json()["precheck_id"])
        assert confirmed.status_code == 200, confirmed.text

    _assert_test_app_released(client)
    holder = sqlite3.connect(settings.database_path.as_posix())
    holder.execute("BEGIN IMMEDIATE")
    try:
        apply_pending_restore(settings)
    finally:
        holder.rollback()
        holder.close()
    status = __import__("json").loads((settings.runtime_dir / "restore-control" / "state.json").read_text(encoding="utf-8"))
    assert status["phase"] == "ROLLED_BACK"
    assert status["error_code"] == "RESTORE_DATABASE_LOCKED"
    assert _sha((settings.resolved_data_dir / relative).read_bytes()) == original_hash

    # A fresh confirmation is required after the locked attempt.
    client2, _, settings2 = _make_app(tmp_path)
    with client2:
        _, archive2 = _download_archive(client2)
        with client2.app.state.session_factory() as session:
            _seed_content_object(session, settings2, b"second-live")
        uploaded2 = _upload(client2, archive2)
        precheck2 = _precheck(client2, uploaded2["upload_id"])
        assert precheck2.status_code == 200, precheck2.text
        confirmed2 = _execute(client2, precheck2.json()["precheck_id"])
        assert confirmed2.status_code == 200, confirmed2.text
        recovery_id = confirmed2.json()["recovery_point_id"]

    _assert_test_app_released(client2)
    calls = {"n": 0}
    original = swap_tree
    rename_failures: list[tuple[str, str, int | None]] = []
    original_rename = local_restore_module._rename_released

    def observe_rename(source: Path, destination: Path) -> None:
        try:
            original_rename(source, destination)
        except BackupBuildError as exc:
            cause = exc.__cause__
            source_role = "live" if source.parent == settings2.resolved_data_dir else "staged"
            destination_role = "aside" if "aside" in destination.parts else "live"
            rename_failures.append(
                (source_role, destination_role, getattr(cause, "winerror", None))
            )
            raise

    monkeypatch.setattr(local_restore_module, "_rename_released", observe_rename)

    def boom(live: Path, staged: Path, aside: Path) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise BackupBuildError("RESTORE_SWITCH_CONFLICT", "注入切换中断。")
        original(live, staged, aside)

    monkeypatch.setattr(local_restore_module, "swap_tree", boom)
    interrupted = apply_pending_restore(settings2)
    assert interrupted is not None
    diagnostic = {
        "swap_calls": calls["n"],
        "phase": interrupted.get("phase"),
        "error_code": interrupted.get("error_code"),
        "rename_failures": rename_failures,
    }
    assert calls["n"] == 2, f"第二次 swap 注入未到达：{diagnostic}"
    assert interrupted["phase"] == "ROLLED_BACK"
    assert interrupted["error_code"] == "RESTORE_SWITCH_CONFLICT"
    live_object = settings2.resolved_data_dir / relative
    assert _sha(live_object.read_bytes()) == original_hash
    quick = sqlite3.connect(settings2.database_path.as_posix())
    try:
        assert quick.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert quick.execute(
            "SELECT 1 FROM content_objects WHERE sha256 = ?", (original_hash,)
        ).fetchone() is not None
    finally:
        quick.close()

    recovery_root = settings2.resolved_data_dir / "recovery-points" / recovery_id
    recovery_db = recovery_root / "database" / "mindmate.db"
    assert recovery_db.is_file()
    snapshot = sqlite3.connect(recovery_db.as_posix())
    try:
        assert snapshot.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        second_live_hash = _sha(b"second-live")
        recovery_object = snapshot.execute(
            "SELECT storage_relative_path FROM content_objects WHERE sha256 = ?",
            (second_live_hash,),
        ).fetchone()
        assert recovery_object is not None
    finally:
        snapshot.close()
    assert _sha((recovery_root / recovery_object[0]).read_bytes()) == second_live_hash

    replayed = apply_pending_restore(settings2)
    assert replayed == interrupted
    assert calls["n"] == 2
    assert _sha(live_object.read_bytes()) == original_hash
    assert sentinel.read_text(encoding="utf-8") == "outside-root"


def test_migration_failure_rolls_back_before_publish(tmp_path: Path, monkeypatch) -> None:
    client, _, settings = _make_app(tmp_path)
    payload = b"migration-original"
    with client:
        with client.app.state.session_factory() as session:
            row = _seed_content_object(session, settings, payload)
        relative = row.storage_relative_path
        _, archive = _download_archive(client)
        uploaded = _upload(client, archive)
        precheck = _precheck(client, uploaded["upload_id"])
        assert precheck.status_code == 200, precheck.text
        confirmed = _execute(client, precheck.json()["precheck_id"])
        assert confirmed.status_code == 200, confirmed.text

    def _fail(*_args, **_kwargs) -> None:
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr("mindmate.application.local_restore.command.upgrade", _fail)
    apply_pending_restore(settings)
    state_path = settings.runtime_dir / "restore-control" / "state.json"
    state = __import__("json").loads(state_path.read_text(encoding="utf-8"))
    assert state["phase"] == "ROLLED_BACK"
    assert state["error_code"] == "RESTORE_MIGRATION_FAILED"
    assert (settings.resolved_data_dir / relative).read_bytes() == payload


def test_missing_content_object_is_rejected(tmp_path: Path) -> None:
    client, _, settings = _make_app(tmp_path)
    with client:
        with client.app.state.session_factory() as session:
            _seed_content_object(session, settings, b"present")
        _, archive = _download_archive(client)
    tampered = _drop_content_entry(archive)
    pytest_raises_code(settings, tampered, "BACKUP_CONTENT_MISSING")


def pytest_raises_code(settings: Settings, payload: bytes, code: str) -> None:
    archive = settings.runtime_dir / "tampered.mindmate-backup"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(payload)
    try:
        inspect_restore_archive(archive, settings)
    except BackupBuildError as exc:
        assert exc.code == code
        assert str(settings.resolved_data_dir) not in exc.detail
        return
    raise AssertionError(code)


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _zip_bytes(buffer: io.BytesIO) -> bytes:
    return buffer.getvalue()


def _compressible_bomb() -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("database/mindmate.db", b"\0" * (2 * 1024 * 1024))
    return buffer


def _symlink_zip() -> bytes:
    buffer = io.BytesIO()
    info = zipfile.ZipInfo("objects/link.txt")
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (0o120000 << 16) | (0o644 << 16)
    info.file_size = 1
    info.CRC = zipfile.crc32(b"x") & 0xFFFFFFFF
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(info, b"x")
    # writestr may recompute attributes; force the unix symlink mode afterwards if needed.
    raw = buffer.getvalue()
    return raw


def _drop_content_entry(archive: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(archive))
    kept: list[tuple[str, bytes]] = []
    for info in source.infolist():
        if info.filename.startswith("objects/"):
            continue
        kept.append((info.filename, source.read(info.filename)))
    source.close()
    manifest = __import__("json").loads(dict(kept)["manifest.json"])
    manifest["entries"] = [entry for entry in manifest["entries"] if not str(entry["path"]).startswith("objects/")]
    manifest["file_count"] = len(manifest["entries"])
    manifest["total_size"] = sum(int(entry["byte_size"]) for entry in manifest["entries"])
    manifest_bytes = __import__("json").dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive_out:
        for name, payload in kept:
            if name == "manifest.json":
                archive_out.writestr(name, manifest_bytes)
            else:
                archive_out.writestr(name, payload)
    return buffer.getvalue()
