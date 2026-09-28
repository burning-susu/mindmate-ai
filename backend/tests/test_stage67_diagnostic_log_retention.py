from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import mindmate.api.system_settings as system_settings
import mindmate.application.diagnostic_log_retention as retention
import mindmate.main as main_module
from mindmate.application.diagnostic_log_retention import (
    DiagnosticLogError,
    LogRetentionStatus,
    clear_diagnostic_logs,
    inspect_log_retention,
    record_diagnostic_event,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask
from mindmate.main import create_app

ORIGIN = "http://127.0.0.1:5173"


def _diagnostic_dir(data_dir: Path) -> Path:
    return data_dir / "logs" / "diagnostic-events"


def _filename(created_at: datetime, sequence: int = 0) -> str:
    stamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"mindmate-safe-{stamp}-{sequence:04d}.jsonl"


def test_runtime_log_is_structured_and_rejects_unapproved_values(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    secret = "TOKEN=fixture-secret C:\\private\\notes.txt question body"

    assert record_diagnostic_event(settings, "APPLICATION_STARTED") is True
    assert record_diagnostic_event(settings, f"APPLICATION_STARTED {secret}") is False
    assert (
        record_diagnostic_event(
            settings,
            "APPLICATION_STARTED",
            task_id=secret,
            task_type="RAG_ANSWER",
            task_status="FAILED",
        )
        is False
    )

    log_files = list(_diagnostic_dir(tmp_path).glob("mindmate-safe-*.jsonl"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    document = json.loads(content)
    assert set(document) == {"timestamp_utc", "level", "module", "event_code"}
    assert document["event_code"] == "APPLICATION_STARTED"
    assert "fixture-secret" not in content
    assert "private" not in content
    assert "question body" not in content


def test_age_retention_boundary_and_repeated_maintenance_are_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(retention, "_now", lambda: now)
    directory = _diagnostic_dir(tmp_path)
    directory.mkdir(parents=True)
    within = now - timedelta(days=30)
    expired = now - timedelta(days=30, seconds=1)
    within_path = directory / _filename(within)
    expired_path = directory / _filename(expired)
    within_path.write_text('{"event_code":"APPLICATION_STARTED"}\n', encoding="utf-8")
    expired_path.write_text('{"event_code":"APPLICATION_STOPPED"}\n', encoding="utf-8")

    first = inspect_log_retention(Settings(data_dir=tmp_path, env="test"))
    second = inspect_log_retention(Settings(data_dir=tmp_path, env="test"))

    assert first.available and first.cleanup_complete
    assert second.file_count == first.file_count == 1
    assert second.bytes_used == first.bytes_used == within_path.stat().st_size
    assert within_path.exists()
    assert not expired_path.exists()


def test_capacity_retention_rotates_and_stays_within_configured_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retention, "MAX_TOTAL_BYTES", 1024)
    monkeypatch.setattr(retention, "MAX_SEGMENT_BYTES", 1)
    settings = Settings(data_dir=tmp_path, env="test")

    for _ in range(20):
        assert record_diagnostic_event(settings, "APPLICATION_STARTED")

    status = inspect_log_retention(settings)
    files = list(_diagnostic_dir(tmp_path).glob("mindmate-safe-*.jsonl"))
    assert retention.MAX_TOTAL_BYTES == 1024
    assert status.available and status.cleanup_complete
    assert status.bytes_used <= 1024
    assert sum(path.stat().st_size for path in files) <= 1024
    assert len(files) < 20
    assert retention.MAX_TOTAL_BYTES != 100 * 1024 * 1024


def test_default_capacity_is_100_mib() -> None:
    assert retention.MAX_TOTAL_BYTES == 100 * 1024 * 1024
    assert retention.RETENTION_DAYS == 30


def test_clear_only_deletes_owned_logs_and_keeps_application_data(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        headers = {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}
        session = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        assert session.status_code == 200

        now = datetime.now(UTC)
        with cast(Any, client).app.state.session_factory() as db:
            db.add(
                BackgroundTask(
                    task_id="11111111-1111-7111-8111-111111111111",
                    task_type="INDEX_PREPROCESS",
                    status="FAILED",
                    created_at=now,
                    updated_at=now,
                    completed_at=now,
                )
            )
            db.commit()

        app_log = tmp_path / "logs" / "app.log"
        app_log.write_text("externally managed log", encoding="utf-8")
        backup = tmp_path / "backups" / "keep.mindmate-backup"
        backup.write_bytes(b"backup")
        model = tmp_path / "models" / "keep.onnx"
        model.write_bytes(b"model")
        object_file = tmp_path / "objects" / "keep.txt"
        object_file.write_text("business data", encoding="utf-8")

        privacy = client.get("/api/v1/system/privacy", headers={"Origin": ORIGIN})
        assert privacy.status_code == 200
        log_status = privacy.json()["log_retention"]
        assert log_status["available"] is True
        assert log_status["retention_days"] == 30
        assert log_status["max_bytes"] == 100 * 1024 * 1024
        assert log_status["file_count"] >= 1

        export = client.get("/api/v1/system/diagnostics/export", headers=headers)
        assert export.status_code == 200
        assert "APPLICATION_STARTED" not in export.text
        assert "externally managed log" not in export.text

        clear = client.post("/api/v1/system/diagnostics/logs/clear", headers=headers, json={})
        assert clear.status_code == 200
        assert clear.json()["complete"] is True
        assert clear.json()["files_removed"] >= 1
        assert clear.json()["remaining_files"] == 0
        assert not list(_diagnostic_dir(tmp_path).glob("mindmate-safe-*.jsonl"))
        assert app_log.read_text(encoding="utf-8") == "externally managed log"
        assert backup.read_bytes() == b"backup"
        assert model.read_bytes() == b"model"
        assert object_file.read_text(encoding="utf-8") == "business data"
        with cast(Any, client).app.state.session_factory() as db:
            assert db.get(BackgroundTask, "11111111-1111-7111-8111-111111111111") is not None


def test_clear_requires_the_existing_session_and_origin_guards(tmp_path: Path) -> None:
    with TestClient(
        create_app(Settings(data_dir=tmp_path, env="test")), base_url="http://127.0.0.1"
    ) as client:
        headers = {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}
        missing_session = client.post("/api/v1/system/diagnostics/logs/clear", headers=headers)
        assert missing_session.status_code == 401

        assert client.post("/api/v1/system/session", headers={"Origin": ORIGIN}).status_code == 200
        forbidden = client.post(
            "/api/v1/system/diagnostics/logs/clear",
            headers={**headers, "Origin": "http://evil.invalid"},
        )
        assert forbidden.status_code == 403


def test_api_cleanup_failure_returns_only_a_safe_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(
        create_app(Settings(data_dir=tmp_path, env="test")), base_url="http://127.0.0.1"
    ) as client:
        headers = {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}
        assert client.post("/api/v1/system/session", headers={"Origin": ORIGIN}).status_code == 200

        def fail(_settings: Settings) -> retention.LogClearResult:
            raise OSError("C:\\private\\secret.log TOKEN=never-return")

        monkeypatch.setattr(system_settings, "clear_diagnostic_logs", fail)
        response = client.post(
            "/api/v1/system/diagnostics/logs/clear", headers=headers, json={}
        )
        assert response.status_code == 503
        assert response.json()["code"] == "LOG_CLEANUP_FAILED"
        assert "private" not in response.text
        assert "never-return" not in response.text


def test_unavailable_log_storage_does_not_block_application_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unavailable = LogRetentionStatus(
        available=False,
        file_count=0,
        bytes_used=0,
        cleanup_complete=False,
        error_code="LOG_DIRECTORY_UNAVAILABLE",
    )
    monkeypatch.setattr(main_module, "inspect_log_retention", lambda _settings: unavailable)
    monkeypatch.setattr(main_module, "record_diagnostic_event", lambda *_args, **_kwargs: False)

    with TestClient(
        create_app(Settings(data_dir=tmp_path, env="test")), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/api/v1/health").status_code == 200


def test_occupied_file_is_reported_and_can_be_cleared_after_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    assert record_diagnostic_event(settings, "APPLICATION_STARTED")
    log_file = next(_diagnostic_dir(tmp_path).glob("mindmate-safe-*.jsonl"))

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.CreateFileW(str(log_file), 0x80000000, 0, None, 3, 0, None)
        invalid_handle = wintypes.HANDLE(-1).value
        if handle == invalid_handle:
            pytest.skip("Windows did not grant an exclusive test handle")
        try:
            blocked = clear_diagnostic_logs(settings)
            assert blocked.complete is False
            assert blocked.remaining_files == 1
        finally:
            kernel32.CloseHandle(handle)
        cleared = clear_diagnostic_logs(settings)
        assert cleared.complete is True
        return

    monkeypatch.setattr(retention, "_delete_oldest", lambda _files, _index: False)
    blocked = clear_diagnostic_logs(settings)
    assert blocked.complete is False
    assert blocked.remaining_files == 1
    monkeypatch.undo()
    assert clear_diagnostic_logs(settings).complete is True


def test_reparse_point_is_never_followed_or_deleted(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.jsonl"
    sentinel.write_text("outside data", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    link = logs / "diagnostic-events"
    if os.name == "nt":
        junction = subprocess.run(
            ["cmd.exe", "/c", f'mklink /J "{link}" "{outside}"'],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            pytest.skip("directory junction creation is unavailable in this Windows environment")
    else:
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks are not available in this environment")

    status = inspect_log_retention(Settings(data_dir=tmp_path, env="test"))
    assert status.available is False
    assert status.error_code == "LOG_DIRECTORY_UNSAFE"
    with pytest.raises(DiagnosticLogError, match="LOG_DIRECTORY_UNSAFE"):
        clear_diagnostic_logs(Settings(data_dir=tmp_path, env="test"))
    assert sentinel.read_text(encoding="utf-8") == "outside data"


def test_concurrent_rotation_and_manual_cleanup_leave_valid_bounded_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retention, "MAX_TOTAL_BYTES", 4096)
    monkeypatch.setattr(retention, "MAX_SEGMENT_BYTES", 1)
    settings = Settings(data_dir=tmp_path, env="test")

    def write_events() -> None:
        for _ in range(25):
            record_diagnostic_event(settings, "APPLICATION_STARTED")

    def clear_periodically() -> None:
        for _ in range(8):
            clear_diagnostic_logs(settings)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(write_events) for _ in range(4)]
        futures.extend(pool.submit(clear_periodically) for _ in range(1))
        for future in futures:
            future.result()

    status = inspect_log_retention(settings)
    files = list(_diagnostic_dir(tmp_path).glob("mindmate-safe-*.jsonl"))
    assert status.available and status.cleanup_complete
    assert status.bytes_used <= 4096
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["event_code"] == "APPLICATION_STARTED"


def test_repeated_application_startup_preserves_a_bounded_log_store(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    for _ in range(3):
        with TestClient(create_app(settings), base_url="http://127.0.0.1"):
            pass

    status = inspect_log_retention(settings)
    assert status.available and status.cleanup_complete
    assert status.file_count <= 6
    records = [
        json.loads(line)
        for path in _diagnostic_dir(tmp_path).glob("mindmate-safe-*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [item["event_code"] for item in records].count("APPLICATION_STARTED") == 3
    assert [item["event_code"] for item in records].count("APPLICATION_STOPPED") == 3
