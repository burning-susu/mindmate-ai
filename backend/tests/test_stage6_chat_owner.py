from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.ai.providers.base import ChatResponse, ProviderRequestError
from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.ai.providers.mock import MockChatProvider
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    AiOperation,
    AnswerVersion,
    BackgroundTask,
    Conversation,
    ConversationScope,
    Message,
)
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore

ORIGIN = "http://127.0.0.1:5173"


def _headers(key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key}


def _wait_for_terminal(client: TestClient, operation_id: str) -> dict:
    for _ in range(150):
        response = client.get(f"/api/v1/ai-operations/{operation_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in {"QUEUED", "RUNNING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("AI Operation did not reach a terminal state")


def _start_client(tmp_path: Path, provider=None):
    app = create_app(
        Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    )
    app.state.chat_provider = provider or MockChatProvider()
    app.state.credential_store = InMemoryCredentialStore()
    client = TestClient(app, base_url="http://127.0.0.1")
    return app, client


def _open_session(client: TestClient) -> None:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200


def test_blank_page_does_not_create_conversation(tmp_path: Path) -> None:
    _app, client = _start_client(tmp_path)
    with client:
        _open_session(client)
        response = client.get("/api/v1/conversations")
        assert response.status_code == 200
        assert response.json()["items"] == []


def test_first_message_is_atomic_idempotent_and_generates_with_mock(tmp_path: Path) -> None:
    provider = MockChatProvider(response_factory=lambda request: "fixture answer")
    app, client = _start_client(tmp_path, provider)
    with client:
        _open_session(client)
        first = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-first-001"),
            json={"first_message": "第一条问题", "client_request_id": "client-first-001"},
        )
        assert first.status_code == 202
        payload = first.json()
        assert payload["conversation_id"]
        assert payload["user_message_id"]
        assert payload["assistant_message_id"]
        assert payload["operation_id"]
        assert payload["operation"]["status"] == "QUEUED"

        completed = _wait_for_terminal(client, payload["operation_id"])
        assert completed["status"] == "COMPLETED"
        assert completed["assistant_message"]["content"] == "fixture answer"
        assert completed["answer_version"]["status"] == "COMPLETED"
        assert len(provider.calls) == 1

        with app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(Conversation)) == 1
            assert session.scalar(select(func.count()).select_from(ConversationScope)) == 1
            assert session.scalar(select(func.count()).select_from(Message)) == 2
            assert session.scalar(select(func.count()).select_from(AiOperation)) == 1
            assert session.scalar(select(func.count()).select_from(AnswerVersion)) == 1
            assert session.scalar(select(func.count()).select_from(BackgroundTask)) == 1

        duplicate = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-first-001"),
            json={"first_message": "第一条问题", "client_request_id": "client-first-001"},
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["operation_id"] == payload["operation_id"]
        assert len(provider.calls) == 1

        conflict = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-first-001"),
            json={"first_message": "另一条问题", "client_request_id": "client-first-001"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_follow_up_preserves_order_and_duplicate_does_not_generate_twice(tmp_path: Path) -> None:
    provider = MockChatProvider(response_factory=lambda request: f"answer-{len(provider.calls)}")
    app, client = _start_client(tmp_path, provider)
    with client:
        _open_session(client)
        first = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-order-001"),
            json={"first_message": "第一问", "client_request_id": "client-order-001"},
        )
        assert first.status_code == 202
        first_payload = first.json()
        _wait_for_terminal(client, first_payload["operation_id"])
        follow_up = client.post(
            f"/api/v1/conversations/{first_payload['conversation_id']}/messages",
            headers=_headers("chat-order-002"),
            json={
                "content": "第二问",
                "client_request_id": "client-order-002",
                "expected_conversation_version": 1,
            },
        )
        assert follow_up.status_code == 202
        follow_payload = follow_up.json()
        assert follow_payload["conversation_id"] == first_payload["conversation_id"]
        _wait_for_terminal(client, follow_payload["operation_id"])

        duplicate = client.post(
            f"/api/v1/conversations/{first_payload['conversation_id']}/messages",
            headers=_headers("chat-order-002"),
            json={
                "content": "第二问",
                "client_request_id": "client-order-002",
                "expected_conversation_version": 1,
            },
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["operation_id"] == follow_payload["operation_id"]
        assert len(provider.calls) == 2

        messages = client.get(
            f"/api/v1/conversations/{first_payload['conversation_id']}/messages"
        )
        assert messages.status_code == 200
        assert [item["sequence_number"] for item in messages.json()["items"]] == [1, 2, 3, 4]
        assert [item["role"] for item in messages.json()["items"]] == [
            "USER",
            "ASSISTANT",
            "USER",
            "ASSISTANT",
        ]
        assert app.state.chat_worker.is_running


def test_external_gate_rejects_without_consent_or_key_before_provider_call(tmp_path: Path) -> None:
    provider = MockChatProvider()
    provider.requires_external_transfer = True
    app, client = _start_client(tmp_path, provider)
    with client:
        _open_session(client)
        first = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-gate-001"),
            json={"first_message": "需要外发门禁", "client_request_id": "client-gate-001"},
        )
        assert first.status_code == 202
        operation = _wait_for_terminal(client, first.json()["operation_id"])
        assert operation["status"] == "FAILED"
        assert operation["error_code"] == "EXTERNAL_AI_CONSENT_REQUIRED"
        assert provider.calls == []

        consent = client.post(
            "/api/v1/ai/consent",
            headers=_headers("chat-gate-002"),
            json={"version": "deepseek-external-ai-v1"},
        )
        assert consent.status_code == 200
        second = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-gate-003"),
            json={"first_message": "仍然没有 Key", "client_request_id": "client-gate-003"},
        )
        assert second.status_code == 202
        failed = _wait_for_terminal(client, second.json()["operation_id"])
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == "PROVIDER_NOT_CONFIGURED"
        assert provider.calls == []

        oversized = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-gate-004"),
            json={"first_message": "x" * 10_001, "client_request_id": "client-gate-004"},
        )
        assert oversized.status_code == 422
        assert provider.calls == []


def test_provider_failure_is_persisted_without_leaking_raw_error(tmp_path: Path) -> None:
    provider = MockChatProvider(
        failure=ProviderRequestError("PROVIDER_RATE_LIMITED", "稍后重试", 429, True)
    )
    _app, client = _start_client(tmp_path, provider)
    with client:
        _open_session(client)
        response = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-fail-001"),
            json={"first_message": "失败问题", "client_request_id": "client-fail-001"},
        )
        operation = _wait_for_terminal(client, response.json()["operation_id"])
        assert operation["status"] == "FAILED"
        assert operation["error_code"] == "PROVIDER_RATE_LIMITED"
        assert operation["assistant_message"]["status"] == "FAILED"
        assert operation["user_message"]["status"] == "SENT"


def test_restart_converges_running_operation_to_interrupted_without_resend(tmp_path: Path) -> None:
    first_provider = MockChatProvider()
    app, client = _start_client(tmp_path, first_provider)
    with client:
        _open_session(client)
        response = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-restart-001"),
            json={"first_message": "重启恢复", "client_request_id": "client-restart-001"},
        )
        payload = response.json()
        app.state.chat_worker.stop()
        with app.state.session_factory() as session:
            operation = session.get(AiOperation, payload["operation_id"])
            task = session.get(BackgroundTask, operation.task_id)
            assistant = session.get(Message, operation.assistant_message_id)
            operation.status = "RUNNING"
            assistant.status = "STREAMING"
            task.status = "RUNNING"
            task.lease_owner = "crashed-process"
            session.commit()

    second_provider = MockChatProvider()
    _app2, client2 = _start_client(tmp_path, second_provider)
    with client2:
        _open_session(client2)
        recovered = client2.get(f"/api/v1/ai-operations/{payload['operation_id']}")
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "INTERRUPTED"
        assert recovered.json()["assistant_message"]["status"] == "INTERRUPTED"
        assert second_provider.calls == []


def test_chat_provider_response_contract_can_be_injected(tmp_path: Path) -> None:
    class Provider:
        requires_external_transfer = False
        provider_name = "FIXTURE"
        model = "fixture-model"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request, api_key=None) -> ChatResponse:
            self.calls += 1
            return ChatResponse(
                request_id=request.request_id,
                status="completed",
                content="injected",
                finish_reason="stop",
                provider=self.provider_name,
                requested_model=self.model,
                resolved_model=self.model,
                usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            )

    provider = Provider()
    _app, client = _start_client(tmp_path, provider)
    with client:
        _open_session(client)
        response = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-inject-001"),
            json={"first_message": "可注入 Provider", "client_request_id": "client-inject-001"},
        )
        operation = _wait_for_terminal(client, response.json()["operation_id"])
        assert operation["status"] == "COMPLETED"
        assert operation["usage_total_tokens"] == 5
        assert provider.calls == 1


def test_deepseek_fixture_generation_sends_only_general_chat_context(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fixture",
                "model": "deepseek-v4.1-flash",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "fixture deepseek answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
            },
            request=request,
        )

    provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model=DEEPSEEK_MODEL,
        transport=httpx.MockTransport(handler),
    )
    app, client = _start_client(tmp_path, provider)
    with client:
        _open_session(client)
        saved = client.post(
            "/api/v1/ai/provider/key",
            headers=_headers("chat-deepseek-key"),
            json={"api_key": "fixture-key-not-persisted"},
        )
        assert saved.status_code == 200
        consent = client.post(
            "/api/v1/ai/consent",
            headers=_headers("chat-deepseek-consent"),
            json={"version": "deepseek-external-ai-v1"},
        )
        assert consent.status_code == 200
        response = client.post(
            "/api/v1/conversations",
            headers=_headers("chat-deepseek-submit"),
            json={"first_message": "只发送必要上下文", "client_request_id": "client-deepseek"},
        )
        assert response.status_code == 202
        operation = _wait_for_terminal(client, response.json()["operation_id"])
        assert operation["status"] == "COMPLETED"
        assert operation["resolved_model"] == "deepseek-v4.1-flash"
        assert operation["usage_total_tokens"] == 16
        assert len(calls) == 1
        body = json.loads(calls[0].content)
        assert body["model"] == DEEPSEEK_MODEL
        assert body["stream"] is False
        assert body["max_tokens"] == 2048
        assert body["messages"][-1] == {"role": "user", "content": "只发送必要上下文"}
        assert "fixture-key-not-persisted" not in calls[0].content.decode()
        assert "storage_relative_path" not in calls[0].content.decode()
        database_bytes = (tmp_path / "database" / "mindmate.db").read_bytes()
        assert b"fixture-key-not-persisted" not in database_bytes
