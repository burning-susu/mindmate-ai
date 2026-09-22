from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from mindmate.config import Settings
from mindmate.main import create_app
from mindmate.security.instance import SingleInstanceLock


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, env="test")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_health_readiness_and_openapi(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    ready = client.get("/api/v1/system/readiness")
    schema = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["x-request-id"] == health.json()["request_id"]
    assert ready.json()["status"] == "ready"
    assert schema.json()["openapi"] == "3.1.0"
    assert schema.json()["paths"]["/api/v1/system/session"]["post"]


def test_startup_runs_migration_and_sets_sqlite_pragmas(client: TestClient) -> None:
    state = cast(Any, client.app).state
    with state.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        assert (
            connection.execute(
                text("SELECT value FROM app_meta WHERE key='schema_version'")
            ).scalar_one()
            == "0001_stage0_app_meta"
        )


def test_non_loopback_host_is_rejected(tmp_path: Path) -> None:
    with TestClient(
        create_app(Settings(data_dir=tmp_path)), base_url="http://attacker.example"
    ) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "LOCAL_HOST_REQUIRED"


def test_mutating_request_requires_allowed_origin_and_session(client: TestClient) -> None:
    missing_session = client.post(
        "/api/v1/not-implemented",
        headers={"Origin": "http://127.0.0.1:5173", "Idempotency-Key": "request-1234"},
    )
    assert missing_session.status_code == 401
    assert missing_session.headers["content-type"].startswith("application/problem+json")
    assert missing_session.json()["code"] == "LOCAL_SESSION_REQUIRED"

    denied_origin = client.post(
        "/api/v1/not-implemented",
        headers={"Origin": "https://evil.example", "Idempotency-Key": "request-1234"},
    )
    assert denied_origin.status_code == 403
    assert denied_origin.json()["code"] == "ORIGIN_NOT_ALLOWED"


def test_session_cookie_is_http_only_and_allows_local_write(client: TestClient) -> None:
    established = client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"})
    assert established.status_code == 200
    cookie = established.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie

    response = client.post(
        "/api/v1/not-implemented",
        headers={"Origin": "http://127.0.0.1:5173", "Idempotency-Key": "request-5678"},
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_idempotency_key_shape_is_validated(client: TestClient) -> None:
    established = client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"})
    assert established.status_code == 200
    response = client.post(
        "/api/v1/not-implemented",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Idempotency-Key": "bad key",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_INVALID"


def test_single_instance_lock_rejects_second_writer(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "instance.lock"
    first = SingleInstanceLock(path)
    second = SingleInstanceLock(path)
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()
