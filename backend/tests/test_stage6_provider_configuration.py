from __future__ import annotations

import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.ai.providers.base import ProviderRequestError
from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, PROBE_TEXT, DeepSeekChatProvider
from mindmate.application.backups import create_backup, verify_backup
from mindmate.config import Settings
from mindmate.infrastructure.models import ProviderProfile
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore, WindowsCredentialStore

ORIGIN = "http://127.0.0.1:5173"
API_KEY = "fixture-secret-do-not-persist"


def _stream_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(
            'data: {"id":"probe-123","model":"deepseek-v4.1-flash",'
            '"choices":[{"delta":{"content":"连接测试成功"},"finish_reason":null}]}\n\n'
            'data: {"id":"probe-123","model":"deepseek-v4.1-flash",'
            '"choices":[{"delta":{},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":8,"completion_tokens":3,"total_tokens":11}}\n\n'
            "data: [DONE]\n\n"
        ).encode(),
        request=request,
    )


def _make_app(tmp_path: Path, handler) -> tuple[TestClient, InMemoryCredentialStore, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    settings = Settings(data_dir=tmp_path, env="test", provider_base_url="https://fixture.invalid")
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model=DEEPSEEK_MODEL,
        transport=httpx.MockTransport(recording_handler),
    )
    return TestClient(app, base_url="http://127.0.0.1"), store, calls


def _session(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}


def test_status_and_key_lifecycle_never_persist_secret(tmp_path: Path) -> None:
    client, store, calls = _make_app(tmp_path, _stream_response)
    with client:
        headers = _session(client)
        initial = client.get("/api/v1/ai/provider")
        assert initial.status_code == 200
        assert initial.json()["configured"] is False
        assert calls == []

        saved = client.post(
            "/api/v1/ai/provider/key",
            headers=headers,
            json={"api_key": API_KEY},
        )
        assert saved.status_code == 200
        assert saved.json()["configured"] is True
        assert API_KEY not in saved.text
        assert store.get_secret("provider/deepseek/api-key") == API_KEY
        assert calls == []

        deleted = client.delete(
            "/api/v1/ai/provider/key",
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert deleted.status_code == 200
        assert deleted.json()["configured"] is False
        assert store.get_secret("provider/deepseek/api-key") is None

    database_bytes = (tmp_path / "database" / "mindmate.db").read_bytes()
    assert API_KEY.encode() not in database_bytes


def test_probe_requires_explicit_external_transfer_and_sends_only_fixed_request(
    tmp_path: Path,
) -> None:
    client, _, calls = _make_app(tmp_path, _stream_response)
    with client:
        headers = _session(client)
        assert (
            client.post("/api/v1/ai/provider/key", headers=headers, json={"api_key": API_KEY}).status_code
            == 200
        )

        denied = client.post(
            "/api/v1/ai/provider/test",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"confirm_external_transfer": False},
        )
        assert denied.status_code == 400
        assert denied.json()["code"] == "EXTERNAL_TRANSFER_CONFIRMATION_REQUIRED"
        assert calls == []

        tested = client.post(
            "/api/v1/ai/provider/test",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"confirm_external_transfer": True},
        )
        assert tested.status_code == 200
        payload = tested.json()
        assert payload["probe"]["status"] == "success"
        assert payload["probe"]["requested_model"] == DEEPSEEK_MODEL
        assert payload["probe"]["resolved_model"] == "deepseek-v4.1-flash"
        assert payload["probe"]["stream_supported"] == "supported"
        assert payload["probe"]["usage_supported"] == "supported"
        assert len(calls) == 1
        request = calls[0]
        body = json.loads(request.content)
        assert body == {
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": PROBE_TEXT}],
            "max_tokens": 8,
            "temperature": 0,
            "stream": True,
        }
        assert API_KEY not in request.content.decode()
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert PROBE_TEXT in request.content.decode()


def test_failed_probe_keeps_key_and_stores_safe_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret details"}}, request=request)

    client, store, _ = _make_app(tmp_path, unauthorized)
    with client:
        headers = _session(client)
        assert (
            client.post("/api/v1/ai/provider/key", headers=headers, json={"api_key": API_KEY}).status_code
            == 200
        )
        response = client.post(
            "/api/v1/ai/provider/test",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"confirm_external_transfer": True},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "PROVIDER_AUTHENTICATION_FAILED"
        assert API_KEY not in response.text
        assert "secret details" not in response.text
        assert store.get_secret("provider/deepseek/api-key") == API_KEY

        status = client.get("/api/v1/ai/provider")
        assert status.json()["configured"] is True
        assert status.json()["probe"]["status"] == "failed"
        assert status.json()["probe"]["error_code"] == "PROVIDER_AUTHENTICATION_FAILED"
        assert API_KEY not in caplog.text
        assert "secret details" not in caplog.text


def test_backup_excludes_key_and_runtime_logs(tmp_path: Path) -> None:
    client, _, _ = _make_app(tmp_path, _stream_response)
    with client:
        headers = _session(client)
        response = client.post(
            "/api/v1/ai/provider/key", headers=headers, json={"api_key": API_KEY}
        )
        assert response.status_code == 200
    log_path = tmp_path / "logs" / "fixture.log"
    log_path.write_text(API_KEY, encoding="utf-8")
    archive = tmp_path.parent / f"{tmp_path.name}-stage6-test.mindmate-backup"
    manifest = create_backup(tmp_path, archive, "stage6-test")
    assert manifest["includes_secrets"] is False
    assert API_KEY not in archive.read_bytes().decode("latin-1")
    with zipfile.ZipFile(archive) as handle:
        assert "logs/fixture.log" not in handle.namelist()
    assert verify_backup(archive)["includes_secrets"] is False


def test_repeated_concurrent_configuration_is_idempotent(tmp_path: Path) -> None:
    client, store, _ = _make_app(tmp_path, _stream_response)
    with client:
        factory = cast(Any, client.app).state.session_factory

        def save_same_key(_: int) -> None:
            with factory() as session:
                from mindmate.application.provider_configuration import save_api_key

                save_api_key(session, store, API_KEY)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(save_same_key, range(16)))
        with factory() as session:
            count = session.scalar(
                select(func.count()).select_from(ProviderProfile).where(
                    ProviderProfile.provider_type == "DEEPSEEK"
                )
            )
        assert count == 1
        assert store.get_secret("provider/deepseek/api-key") == API_KEY
        status = client.get("/api/v1/ai/provider")
        assert status.json()["configured"] is True


def test_external_ai_consent_is_versioned_and_separate_from_probe(tmp_path: Path) -> None:
    client, _, calls = _make_app(tmp_path, _stream_response)
    with client:
        headers = _session(client)
        initial = client.get("/api/v1/ai/consent")
        assert initial.json()["accepted"] is False
        wrong = client.post(
            "/api/v1/ai/consent",
            headers=headers,
            json={"version": "old-version"},
        )
        assert wrong.status_code == 400
        assert wrong.json()["code"] == "CONSENT_VERSION_UNSUPPORTED"
        accepted = client.post(
            "/api/v1/ai/consent",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"version": "deepseek-external-ai-v1"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["accepted"] is True
        assert calls == []


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (403, "PROVIDER_FORBIDDEN"),
        (402, "PROVIDER_QUOTA_EXCEEDED"),
        (429, "PROVIDER_RATE_LIMITED"),
        (500, "PROVIDER_SERVER_ERROR"),
    ],
)
def test_provider_error_mapping(status_code: int, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "do not expose"}}, request=request)

    provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderRequestError) as caught:
        provider.test_connection(API_KEY)
    assert caught.value.code == expected
    assert "do not expose" not in str(caught.value)


def test_provider_timeout_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture timeout", request=request)

    provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderRequestError) as caught:
        provider.test_connection(API_KEY)
    assert caught.value.code == "PROVIDER_READ_TIMEOUT"
    assert caught.value.retryable is True


@pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager is Windows-only")
def test_windows_credential_manager_round_trip() -> None:
    store = WindowsCredentialStore()
    reference = f"stage6-fixture/{uuid4()}"
    try:
        store.set_secret(reference, "ephemeral-stage6-fixture")
        assert store.has_secret(reference) is True
        assert store.get_secret(reference) == "ephemeral-stage6-fixture"
    finally:
        store.delete_secret(reference)
    assert store.has_secret(reference) is False
