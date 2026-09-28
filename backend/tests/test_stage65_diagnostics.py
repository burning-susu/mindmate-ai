from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mindmate.api import system_settings
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask
from mindmate.main import create_app

ORIGIN = "http://127.0.0.1:5173"


def _make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path, env="test")), base_url="http://127.0.0.1")


def _session_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN}


def test_diagnostics_preview_and_export_share_one_redacted_projection(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    with client:
        factory = client.app.state.session_factory
        created_at = datetime.now(UTC) - timedelta(minutes=3)
        with factory() as session:
            session.add(
                BackgroundTask(
                    task_id="11111111-1111-7111-8111-111111111111",
                    task_type="INDEX_PREPROCESS",
                    status="FAILED",
                    phase="EMBEDDING",
                    progress=42,
                    error_summary=(
                        "SECRET_TOKEN=fixture-key C:\\Users\\private\\question-body "
                        "checkpoint-secret"
                    ),
                    created_at=created_at,
                    updated_at=created_at,
                    completed_at=created_at,
                )
            )
            session.commit()

        headers = _session_headers(client)
        preview_response = client.get("/api/v1/system/diagnostics/preview", headers=headers)
        export_response = client.get("/api/v1/system/diagnostics/export", headers=headers)

        assert preview_response.status_code == 200
        assert export_response.status_code == 200
        preview = preview_response.json()
        document = export_response.json()
        assert preview["projection"] == document["projection"]
        assert preview["estimated_size_bytes"] == len(export_response.content)
        assert preview["task_summary"]["total_count"] == 1
        assert preview["projection"]["tasks"]["items"][0] == {
            "diagnostic_id": "11111111-1111-7111-8111-111111111111",
            "task_type": "INDEX_PREPROCESS",
            "status": "FAILED",
            "phase": "EMBEDDING",
            "progress": 42,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "started_at": None,
            "completed_at": created_at.isoformat().replace("+00:00", "Z"),
            "error_code": "TASK_FAILED",
        }
        assert "SECRET_TOKEN" not in export_response.text
        assert "fixture-key" not in export_response.text
        assert "question-body" not in export_response.text
        assert "checkpoint-secret" not in export_response.text
        assert "C:\\Users\\private" not in export_response.text
        assert export_response.headers["content-type"].startswith("application/json")
        assert "attachment" in export_response.headers["content-disposition"]


def test_diagnostics_requires_session_and_allowed_origin(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    with client:
        missing = client.get("/api/v1/system/diagnostics/preview")
        assert missing.status_code == 401

        _session_headers(client)
        forbidden = client.get(
            "/api/v1/system/diagnostics/preview",
            headers={"Origin": "http://evil.invalid"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "ORIGIN_NOT_ALLOWED"


def test_privacy_status_exposes_verified_log_retention_and_diagnostics_export(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    with client:
        _session_headers(client)
        response = client.get("/api/v1/system/privacy", headers={"Origin": ORIGIN})
        assert response.status_code == 200
        body = response.json()
        assert body["diagnostics_export"]["available"] is True
        assert body["log_retention"]["available"] is True
        assert body["log_retention"]["retention_days"] == 30
        assert body["log_retention"]["max_bytes"] == 100 * 1024 * 1024
        assert body["storage_migration"]["available"] is False

        # The JSON download must remain valid and contain no hidden raw fields.
        json.loads(response.text)


def test_diagnostics_export_failure_returns_safe_problem_without_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path)
    with client:
        headers = _session_headers(client)

        def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise OSError("C:\\private\\diagnostics\\secret.log")

        monkeypatch.setattr(system_settings, "build_diagnostics_document", fail)
        response = client.get("/api/v1/system/diagnostics/export", headers=headers)
        assert response.status_code == 503
        assert response.json()["code"] == "DIAGNOSTICS_BUILD_FAILED"
        assert "private" not in response.text
        assert not list(tmp_path.rglob("mindmate-diagnostics-*.json"))
