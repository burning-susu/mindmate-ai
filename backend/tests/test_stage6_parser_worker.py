from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from mindmate.application import parse_worker_service
from mindmate.application.files import FileValidationError
from mindmate.application.resource_limits import ManagedJobObject, resource_limit_capabilities
from mindmate.application.tasks import claim_task, create_task, recover_expired_tasks
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask, Base, TaskAttempt, TaskEvent
from mindmate.main import create_app


def _headers(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def _wait_import(client: TestClient, import_id: str) -> dict:
    for _ in range(300):
        payload = client.get(f"/api/v1/file-imports/{import_id}").json()
        if payload["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"任务未完成: {import_id}")


def _wait_file(client: TestClient, file_id: str, expected: set[str]) -> dict:
    for _ in range(300):
        payload = client.get(f"/api/v1/files/{file_id}").json()
        if payload.get("status") in expected:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"文件状态未达到 {expected}: {file_id}")


@pytest.fixture
def worker_client(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        parse_worker_poll_seconds=0.02,
        parse_worker_max_retries=2,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.post(
            "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
        ).status_code == 200
        yield client, tmp_path


def test_claim_is_atomic_and_expired_lease_can_be_recovered(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'claim.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine,
        tables=cast(Any, [BackgroundTask.__table__, TaskAttempt.__table__, TaskEvent.__table__]),
    )
    with Session(engine) as session:
        task = create_task(session, "FILE_REPROCESS", "claim-atomic", {"file_id": "f1"})
        session.commit()
        task_id = task.task_id

    with Session(engine) as first, Session(engine) as second:
        claimed = claim_task(first, task_id, "worker-1")
        assert claimed is not None
        first.commit()
        assert claimed.started_at is not None
        assert claim_task(second, task_id, "worker-2") is None
        second.rollback()
        second.execute(
            update(BackgroundTask)
            .where(BackgroundTask.task_id == task_id)
            .values(lease_until=datetime(2000, 1, 1, tzinfo=UTC))
        )
        second.commit()
        recovered = claim_task(second, task_id, "worker-2")
        assert recovered is not None
        assert recovered.lease_owner == "worker-2"
        second.commit()

    with Session(engine) as session:
        assert recover_expired_tasks(session) == 0


def test_import_returns_before_slow_parse_and_worker_finishes(worker_client, monkeypatch) -> None:
    client, _ = worker_client
    started = threading.Event()
    release = threading.Event()

    def slow_parse(_path: Path):
        started.set()
        assert release.wait(3)
        return "slow text", {"line_count": 1}

    monkeypatch.setattr(parse_worker_service, "parse_local_text", slow_parse)
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers("slow-import-1"),
        files={"files": ("slow.txt", b"slow", "text/plain")},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "QUEUED"
    assert started.wait(2)
    assert client.get("/api/v1/health").status_code == 200
    release.set()
    completed = _wait_import(client, payload["import_id"])
    assert completed["status"] == "COMPLETED"
    assert completed["items"][0]["parse_status"] == "PARSED"


def test_retry_count_accumulates_and_success_clears_error(worker_client, monkeypatch) -> None:
    client, _ = worker_client
    calls = 0

    def fail_once(_path: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FileValidationError("PARSER_FAILED", "internal parser detail")
        return "retry success", {"line_count": 1}

    monkeypatch.setattr(parse_worker_service, "parse_local_text", fail_once)
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers("retry-import-1"),
        files={"files": ("retry.txt", b"retry", "text/plain")},
    )
    payload = response.json()
    completed = _wait_import(client, payload["import_id"])
    file_id = payload["items"][0]["file_id"]
    file_payload = _wait_file(client, file_id, {"PARSED"})
    assert completed["status"] == "COMPLETED"
    assert calls == 2
    assert file_payload["parse_retry_count"] == 1
    assert file_payload["parse_error_id"] is None


def test_max_retries_and_non_retryable_failure_are_bounded(worker_client, monkeypatch) -> None:
    client, _ = worker_client
    client.app.state.settings.parse_worker_max_retries = 1
    calls = 0

    def always_fail(_path: Path):
        nonlocal calls
        calls += 1
        raise FileValidationError("PARSER_FAILED", "private parser detail")

    monkeypatch.setattr(parse_worker_service, "parse_local_text", always_fail)
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers("retry-limit-1"),
        files={"files": ("limit.txt", b"limit", "text/plain")},
    )
    payload = response.json()
    failed = _wait_import(client, payload["import_id"])
    file_payload = _wait_file(client, payload["items"][0]["file_id"], {"PARSE_FAILED"})
    assert failed["status"] == "FAILED"
    assert calls == 2
    assert file_payload["parse_retry_count"] == 1

    client.app.state.settings.parse_worker_max_retries = 2
    non_retry_calls = 0

    def invalid_text(_path: Path):
        nonlocal non_retry_calls
        non_retry_calls += 1
        raise FileValidationError("TEXT_ENCODING_UNSUPPORTED", "private parser detail")

    monkeypatch.setattr(parse_worker_service, "parse_local_text", invalid_text)
    second = client.post(
        "/api/v1/file-imports",
        headers=_headers("non-retryable-1"),
        files={"files": ("invalid.txt", b"invalid", "text/plain")},
    )
    second_failed = _wait_import(client, second.json()["import_id"])
    second_file = _wait_file(client, second.json()["items"][0]["file_id"], {"PARSE_FAILED"})
    assert second_failed["status"] == "FAILED"
    assert non_retry_calls == 1
    assert second_file["parse_retry_count"] == 0


def test_deleted_file_does_not_receive_old_parse_result(worker_client, monkeypatch) -> None:
    client, data_dir = worker_client
    started = threading.Event()
    release = threading.Event()

    def slow_parse(_path: Path):
        started.set()
        assert release.wait(3)
        return "must not publish", {"line_count": 1}

    monkeypatch.setattr(parse_worker_service, "parse_local_text", slow_parse)
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers("delete-during-parse"),
        files={"files": ("deleted.txt", b"deleted", "text/plain")},
    )
    payload = response.json()
    file_id = payload["items"][0]["file_id"]
    assert started.wait(2)
    detail = client.get(f"/api/v1/files/{file_id}").json()
    deleted = client.delete(
        f"/api/v1/files/{file_id}?expected_version={detail['row_version']}",
        headers=_headers("delete-during-parse-request"),
    )
    assert deleted.status_code == 200
    release.set()
    failed = _wait_import(client, payload["import_id"])
    assert failed["status"] == "FAILED"
    assert client.get(f"/api/v1/files/{file_id}").json()["status"] == "IN_TRASH"
    assert not (data_dir / "parsed" / f"{file_id}.json").exists()


def test_windows_job_object_smoke_does_not_exhaust_memory() -> None:
    capabilities = resource_limit_capabilities(512 * 1024 * 1024)
    assert capabilities.memory_limit_bytes == 512 * 1024 * 1024
    if os.name != "nt":
        assert capabilities.job_object_supported is False
        return
    job = ManagedJobObject.create(capabilities.memory_limit_bytes)
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert job.supported is True
        job.assign(process)
        job.close()
        process.wait(timeout=3)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        job.close()


def test_job_object_creation_failure_maps_to_stable_parser_error(monkeypatch, tmp_path: Path) -> None:
    from mindmate.application import files as file_service
    from mindmate.application.resource_limits import JobObjectError

    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-1.7")

    def fail_create(_memory_limit: int):
        raise JobObjectError("JOB_OBJECT_CREATE_FAILED")

    monkeypatch.setattr(file_service.ManagedJobObject, "create", fail_create)
    with pytest.raises(FileValidationError) as error:
        file_service.parse_document_in_subprocess(source, "PDF")
    assert error.value.code == "PARSER_RESOURCE_LIMIT"
