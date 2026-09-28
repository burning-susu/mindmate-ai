from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.application.usage_budget import (
    BudgetRejected,
    assert_external_budget_allows,
    set_budget,
    summarize_usage,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import AiOperation, Conversation, Message
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore

ORIGIN = "http://127.0.0.1:5173"


def _stream_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(
            b'data: {"id":"probe","model":"deepseek-flash",'
            b'"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
            b'data: {"id":"probe","model":"deepseek-flash",'
            b'"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":8,"completion_tokens":3,"total_tokens":11}}\n\n'
            b"data: [DONE]\n\n"
        ),
        request=request,
    )


def _make_app(tmp_path: Path) -> tuple[TestClient, InMemoryCredentialStore]:
    settings = Settings(data_dir=tmp_path, env="test", provider_base_url="https://fixture.invalid")
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model=DEEPSEEK_MODEL,
        transport=httpx.MockTransport(_stream_response),
    )
    return TestClient(app, base_url="http://127.0.0.1"), store


def _session_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}


def _seed_operation(
    session: Session,
    *,
    provider: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    now = datetime.now(UTC)
    conversation = Conversation(
        title="fixture",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
        last_active_at=now,
    )
    session.add(conversation)
    session.flush()
    user = Message(
        conversation_id=conversation.conversation_id,
        role="user",
        content="q",
        status="COMPLETED",
        sequence_number=1,
        mode_snapshot="GENERAL_CHAT",
        created_at=now,
        updated_at=now,
    )
    assistant = Message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content="a",
        status="COMPLETED",
        sequence_number=2,
        mode_snapshot="GENERAL_CHAT",
        created_at=now,
        updated_at=now,
    )
    session.add_all([user, assistant])
    session.flush()
    session.add(
        AiOperation(
            conversation_id=conversation.conversation_id,
            user_message_id=user.message_id,
            assistant_message_id=assistant.message_id,
            idempotency_key=str(uuid4()),
            client_request_id=str(uuid4()),
            request_hash="a" * 64,
            status="SUCCEEDED",
            provider=provider,
            requested_model=DEEPSEEK_MODEL,
            resolved_model=DEEPSEEK_MODEL,
            prompt_template_version="fixture-v1",
            usage_input_tokens=input_tokens,
            usage_output_tokens=output_tokens,
            usage_total_tokens=(
                None
                if input_tokens is None or output_tokens is None
                else input_tokens + output_tokens
            ),
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
    )
    session.commit()


def test_storage_usage_budget_and_privacy_endpoints(tmp_path: Path) -> None:
    (tmp_path / "objects").mkdir(parents=True, exist_ok=True)
    (tmp_path / "objects" / "a.bin").write_bytes(b"12345")
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "app.log").write_text("no-secret", encoding="utf-8")
    client, _ = _make_app(tmp_path)
    with client:
        headers = _session_headers(client)
        storage = client.get("/api/v1/system/storage")
        assert storage.status_code == 200
        body = storage.json()
        assert body["database"] == "sqlite"
        assert body["writable"] is True
        assert "MindMateAI" in body["data_dir_display"] or body["data_dir_display"]
        objects = next(item for item in body["categories"] if item["key"] == "objects")
        assert objects["byte_size"] == 5
        assert "api_key" not in storage.text.lower() or "api_key" not in body

        usage = client.get("/api/v1/system/ai-usage")
        assert usage.status_code == 200
        usage_body = usage.json()
        assert usage_body["totals"]["online"]["operations"] == 0
        assert "在线实际用量暂无记录" in (usage_body["online_actual_usage_message"] or "")

        privacy = client.get("/api/v1/system/privacy")
        assert privacy.status_code == 200
        assert privacy.json()["log_retention"]["available"] is True
        assert privacy.json()["log_retention"]["retention_days"] == 30
        assert privacy.json()["log_retention"]["max_bytes"] == 100 * 1024 * 1024
        assert "Key" in privacy.json()["secrets_policy"]["message"]

        budget = client.put(
            "/api/v1/system/ai-budget",
            headers=headers,
            json={
                "enabled": True,
                "hard_stop_usd": "1.00",
                "soft_remind_usd": "0.50",
                "period": "30d",
                "unknown_usage_policy": "deny",
            },
        )
        assert budget.status_code == 200
        assert budget.json()["budget"]["enabled"] is True
        assert budget.json()["budget"]["hard_stop_usd"] == "1.00"

        bad = client.put(
            "/api/v1/system/ai-budget",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"enabled": True, "hard_stop_usd": None},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "BUDGET_HARD_STOP_REQUIRED"


def test_usage_isolates_mock_and_online_and_unknown_tokens(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(session, provider="MOCK", input_tokens=10, output_tokens=5)
            _seed_operation(session, provider="DEEPSEEK", input_tokens=100, output_tokens=20)
            _seed_operation(session, provider="DEEPSEEK", input_tokens=None, output_tokens=None)
            summary = summarize_usage(session, days=30)
        assert summary["totals"]["mock"]["operations"] == 1
        assert summary["totals"]["mock"]["input_tokens"] == 10
        assert summary["totals"]["online"]["operations"] == 2
        assert summary["totals"]["online"]["input_tokens"] == 100
        assert summary["totals"]["online"]["unknown_usage_operations"] == 1
        assert summary["unknown_usage_operations"] == 1
        assert Decimal(summary["estimated_online_usd"]) > 0


def test_budget_hard_stop_blocks_external_and_serializes_concurrency(tmp_path: Path) -> None:
    client, store = _make_app(tmp_path)
    with client:
        headers = _session_headers(client)
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            # Large online usage so estimated spend exceeds $0.01 hard stop.
            _seed_operation(session, provider="DEEPSEEK", input_tokens=1_000_000, output_tokens=1_000_000)
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="0.01",
                soft_remind_usd=None,
                period="30d",
                unknown_usage_policy="deny",
            )

        store.set_secret("provider/deepseek/api-key", "fixture-key")
        consent = client.post(
            "/api/v1/ai/consent",
            headers=headers,
            json={"version": "deepseek-external-ai-v1"},
        )
        assert consent.status_code == 200
        probe = client.post(
            "/api/v1/ai/provider/test",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"confirm_external_transfer": True},
        )
        assert probe.status_code == 409
        assert probe.json()["code"] == "BUDGET_HARD_STOP_REACHED"
        assert "fixture-key" not in probe.text

        results: list[str] = []

        def attempt(_: int) -> None:
            with factory() as session:
                try:
                    assert_external_budget_allows(session)
                    results.append("allow")
                except BudgetRejected as exc:
                    results.append(exc.code)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(attempt, range(12)))
        assert results
        assert all(code == "BUDGET_HARD_STOP_REACHED" for code in results)


def test_budget_unknown_usage_denies_conservatively(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(session, provider="DEEPSEEK", input_tokens=None, output_tokens=None)
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="10.00",
                unknown_usage_policy="deny",
            )
            with pytest.raises(BudgetRejected) as caught:
                assert_external_budget_allows(session)
            assert caught.value.code == "BUDGET_USAGE_UNTRUSTED"
