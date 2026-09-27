from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from mindmate.ai.providers.base import ChatRequest
from mindmate.ai.providers.deepseek import DeepSeekChatProvider
from mindmate.ai.providers.openai import OPENAI_BASE_URL, OPENAI_MODEL, OpenAIChatProvider
from mindmate.application.evidence_gate import assess_evidence
from mindmate.application.hybrid_search import HybridAssessmentResult, HybridSearchResult
from mindmate.application.provider_configuration import (
    OPENAI_PROVIDER_ID,
    read_generation_mode,
    write_setting,
)
from mindmate.application.usage_budget import set_budget, summarize_usage
from mindmate.config import Settings
from mindmate.infrastructure.models import AppSetting
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore
from test_stage5_source_snapshots import _seed_active_index, _supported_result
from test_stage8_settings_usage_budget import _seed_operation

ORIGIN = "http://127.0.0.1:5173"
OPENAI_KEY = "openai-fixture-secret"
DEEPSEEK_KEY = "deepseek-fixture-secret"


def _sse(*events: dict[str, Any], done: bool = True) -> bytes:
    lines = [f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode() for event in events]
    if done:
        lines.append(b"data: [DONE]\n\n")
    return b"".join(lines)


def _chat_request() -> ChatRequest:
    return ChatRequest(
        request_id="req-1",
        task_type="GENERAL_CHAT",
        model_profile="client-supplied-model",
        system_instructions="只回答问题",
        messages=({"role": "user", "content": "连接测试 你好"},),
        max_output_tokens=64,
        temperature=0.2,
    )


def test_openai_stream_uses_official_contract_and_ignores_reasoning() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                {
                    "id": "resp-1",
                    "model": "gpt-6-sol-2026-09-01",
                    "choices": [{"delta": {"reasoning": "不要写入正文"}, "finish_reason": None}],
                },
                {
                    "id": "resp-1",
                    "model": "gpt-6-sol-2026-09-01",
                    "choices": [{"delta": {"content": "可见"}, "finish_reason": None}],
                },
                {
                    "id": "resp-1",
                    "model": "gpt-6-sol-2026-09-01",
                    "choices": [{"delta": {"content": "文本"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
                },
            ),
            request=request,
        )

    provider = OpenAIChatProvider(timeout_seconds=2, transport=httpx.MockTransport(handler))
    chunks = list(provider.generate_stream(_chat_request(), OPENAI_KEY))
    assert "".join(chunk.delta for chunk in chunks) == "可见文本"
    assert chunks[-1].done is True
    assert chunks[-1].requested_model == OPENAI_MODEL
    assert chunks[-1].resolved_model == "gpt-6-sol-2026-09-01"
    assert chunks[-1].usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    body = json.loads(calls[0].content)
    assert calls[0].url == httpx.URL(f"{OPENAI_BASE_URL}/chat/completions")
    assert body["model"] == OPENAI_MODEL
    assert body["reasoning_effort"] == "none"
    assert body["max_completion_tokens"] == 64
    assert body["stream_options"] == {"include_usage": True}
    assert "temperature" not in body
    assert "max_tokens" not in body
    assert "tools" not in body
    assert "不要写入正文" not in "".join(chunk.delta for chunk in chunks)


def test_openai_errors_do_not_invent_success_and_missing_usage_stays_unknown() -> None:
    provider = OpenAIChatProvider(
        timeout_seconds=2,
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "no"}, request=request)),
    )
    try:
        provider.generate(_chat_request(), OPENAI_KEY)
    except Exception as exc:
        assert getattr(exc, "code", "") == "PROVIDER_AUTHENTICATION_FAILED"
    else:
        raise AssertionError("401 should fail")

    limited = OpenAIChatProvider(
        timeout_seconds=2,
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={"error": "slow"}, request=request)),
    )
    try:
        limited.test_connection(OPENAI_KEY)
    except Exception as exc:
        assert getattr(exc, "code", "") == "PROVIDER_RATE_LIMITED"
    else:
        raise AssertionError("429 should fail")

    redirected = OpenAIChatProvider(
        timeout_seconds=2,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "https://evil.example"}, request=request)
        ),
    )
    try:
        list(redirected.generate_stream(_chat_request(), OPENAI_KEY))
    except Exception as exc:
        assert getattr(exc, "code", "") == "PROVIDER_REDIRECT_REJECTED"
        assert "evil.example" not in str(exc)
    else:
        raise AssertionError("redirect should fail")

    missing_usage = OpenAIChatProvider(
        timeout_seconds=2,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "id": "resp-2",
                    "model": "gpt-6-sol",
                    "choices": [{"message": {"role": "assistant", "content": "只有正文"}, "finish_reason": "stop"}],
                },
                request=request,
            )
        ),
    )
    response = missing_usage.generate(_chat_request(), OPENAI_KEY)
    assert response.usage is None
    assert response.requested_model == OPENAI_MODEL
    assert response.content == "只有正文"


def _headers(key: str | None = None) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key or str(uuid4())}


def _app(tmp_path: Path) -> tuple[TestClient, InMemoryCredentialStore, list[httpx.Request], list[httpx.Request]]:
    openai_calls: list[httpx.Request] = []
    deepseek_calls: list[httpx.Request] = []

    def openai_handler(request: httpx.Request) -> httpx.Response:
        openai_calls.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                {"id": "oa-1", "model": "gpt-6-sol-live-alias", "choices": [{"delta": {"content": "OpenAI 回答"}, "finish_reason": "stop"}]},
                {"id": "oa-1", "model": "gpt-6-sol-live-alias", "choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
            ),
            request=request,
        )

    def deepseek_handler(request: httpx.Request) -> httpx.Response:
        deepseek_calls.append(request)
        return httpx.Response(401, json={"error": "should-not-run"}, request=request)

    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.openai_provider = OpenAIChatProvider(timeout_seconds=2, transport=httpx.MockTransport(openai_handler))
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://api.deepseek.com",
        transport=httpx.MockTransport(deepseek_handler),
    )
    return TestClient(app, base_url="http://127.0.0.1"), store, openai_calls, deepseek_calls


def _wait(client: TestClient, operation_id: str) -> dict[str, Any]:
    for _ in range(200):
        payload = client.get(f"/api/v1/ai-operations/{operation_id}").json()
        if payload["status"] not in {"QUEUED", "RUNNING", "STOPPING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("operation did not finish")


def test_selection_persists_and_keys_stay_separate(tmp_path: Path) -> None:
    client, store, openai_calls, deepseek_calls = _app(tmp_path)
    with client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        initial = client.get("/api/v1/ai/provider")
        assert initial.json()["generation_mode"] == "mock"
        assert "模型选择目前适用于 AI 对话" in initial.json()["learning_notice"]
        assert openai_calls == [] and deepseek_calls == []

        selected = client.post(
            "/api/v1/ai/provider/generation-mode",
            headers=_headers(),
            json={"mode": OPENAI_PROVIDER_ID},
        )
        assert selected.status_code == 200
        assert selected.json()["generation_mode"] == OPENAI_PROVIDER_ID
        assert openai_calls == []

        saved = client.post(
            "/api/v1/ai/provider/openai/key",
            headers=_headers(),
            json={"api_key": OPENAI_KEY},
        )
        assert saved.status_code == 200
        openai_card = next(item for item in saved.json()["providers"] if item["provider_id"] == OPENAI_PROVIDER_ID)
        deepseek_card = next(item for item in saved.json()["providers"] if item["provider_id"] == "deepseek")
        assert openai_card["configured"] is True
        assert deepseek_card["configured"] is False
        assert OPENAI_KEY not in saved.text
        store.set_secret("provider/deepseek/api-key", DEEPSEEK_KEY)
        client.delete("/api/v1/ai/provider/openai/key", headers=_headers())
        assert store.get_secret("provider/openai/api-key") is None
        assert store.get_secret("provider/deepseek/api-key") == DEEPSEEK_KEY

        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            raw = " ".join(
                json.dumps(row.setting_value_json, ensure_ascii=False)
                for row in session.scalars(select(AppSetting))
            )
            assert OPENAI_KEY not in raw
            assert DEEPSEEK_KEY not in raw
            write_setting(session, "ai.chat.generation_mode", {"mode": "not-a-provider"})
            session.commit()
            assert read_generation_mode(session) == "mock"
        again = client.get("/api/v1/ai/provider")
        assert again.json()["generation_mode"] == "mock"


def test_openai_chat_requires_its_own_consent_key_and_charge(tmp_path: Path) -> None:
    client, store, openai_calls, deepseek_calls = _app(tmp_path)
    with client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        client.post("/api/v1/ai/provider/generation-mode", headers=_headers(), json={"mode": OPENAI_PROVIDER_ID})
        client.post(
            "/api/v1/ai/consent",
            headers=_headers(),
            json={"version": "deepseek-external-ai-v1"},
        )
        blocked = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-no-confirm"),
            json={"first_message": "你好", "client_request_id": "openai-no-confirm"},
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "PROVIDER_CHARGE_CONFIRMATION_REQUIRED"
        assert openai_calls == []

        store.set_secret("provider/openai/api-key", OPENAI_KEY)
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-no-consent"),
            json={
                "first_message": "你好",
                "client_request_id": "openai-no-consent",
                "confirm_provider_charge": True,
            },
        )
        assert created.status_code == 202
        failed = _wait(client, created.json()["operation_id"])
        assert failed["error_code"] == "EXTERNAL_AI_CONSENT_REQUIRED"
        assert failed["provider"] == "OPENAI"
        assert openai_calls == [] and deepseek_calls == []

        client.post(
            "/api/v1/ai/provider/openai/consent",
            headers=_headers(),
            json={"version": "openai-external-ai-v1"},
        )
        sent = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-ok"),
            json={
                "first_message": "你好",
                "client_request_id": "openai-ok",
                "confirm_provider_charge": True,
            },
        )
        completed = _wait(client, sent.json()["operation_id"])
        assert completed["status"] == "COMPLETED"
        assert completed["provider"] == "OPENAI"
        assert completed["requested_model"] == OPENAI_MODEL
        assert completed["resolved_model"] == "gpt-6-sol-live-alias"
        assert "OpenAI 回答" in completed["assistant_message"]["content"]
        assert len(openai_calls) == 1
        assert deepseek_calls == []
        assert OPENAI_KEY.encode() in openai_calls[0].headers["authorization"].encode()
        assert "api.deepseek.com" not in str(openai_calls[0].url)


def test_inflight_operation_keeps_openai_after_switching_to_deepseek(tmp_path: Path) -> None:
    client, store, openai_calls, deepseek_calls = _app(tmp_path)
    with client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        store.set_secret("provider/openai/api-key", OPENAI_KEY)
        client.post("/api/v1/ai/provider/generation-mode", headers=_headers(), json={"mode": OPENAI_PROVIDER_ID})
        client.post(
            "/api/v1/ai/provider/openai/consent",
            headers=_headers(),
            json={"version": "openai-external-ai-v1"},
        )
        worker = cast(Any, client.app).state.chat_worker
        worker.stop()
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-frozen"),
            json={
                "first_message": "冻结服务",
                "client_request_id": "openai-frozen",
                "confirm_provider_charge": True,
            },
        )
        assert created.status_code == 202
        switched = client.post(
            "/api/v1/ai/provider/generation-mode",
            headers=_headers(),
            json={"mode": "deepseek"},
        )
        assert switched.json()["generation_mode"] == "deepseek"
        worker.start()
        completed = _wait(client, created.json()["operation_id"])
        assert completed["status"] == "COMPLETED"
        assert completed["provider"] == "OPENAI"
        assert len(openai_calls) == 1
        assert deepseek_calls == []


def test_openai_auth_failure_does_not_call_deepseek(tmp_path: Path) -> None:
    client, store, _openai_calls, deepseek_calls = _app(tmp_path)

    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad"}, request=request)

    cast(Any, client.app).state.openai_provider = OpenAIChatProvider(
        timeout_seconds=2, transport=httpx.MockTransport(reject)
    )
    with client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        store.set_secret("provider/openai/api-key", OPENAI_KEY)
        store.set_secret("provider/deepseek/api-key", DEEPSEEK_KEY)
        client.post("/api/v1/ai/provider/generation-mode", headers=_headers(), json={"mode": OPENAI_PROVIDER_ID})
        client.post(
            "/api/v1/ai/provider/openai/consent",
            headers=_headers(),
            json={"version": "openai-external-ai-v1"},
        )
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-401"),
            json={"first_message": "失败", "client_request_id": "openai-401", "confirm_provider_charge": True},
        )
        failed = _wait(client, created.json()["operation_id"])
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == "PROVIDER_AUTHENTICATION_FAILED"
        assert failed["provider"] == "OPENAI"
        assert deepseek_calls == []


def test_budget_and_missing_key_make_zero_openai_calls(tmp_path: Path) -> None:
    client, _store, openai_calls, _deepseek_calls = _app(tmp_path)
    with client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        client.post("/api/v1/ai/provider/generation-mode", headers=_headers(), json={"mode": OPENAI_PROVIDER_ID})
        client.post(
            "/api/v1/ai/provider/openai/consent",
            headers=_headers(),
            json={"version": "openai-external-ai-v1"},
        )
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-no-key"),
            json={"first_message": "没钥匙", "client_request_id": "openai-no-key", "confirm_provider_charge": True},
        )
        failed = _wait(client, created.json()["operation_id"])
        assert failed["error_code"] == "PROVIDER_NOT_CONFIGURED"
        assert openai_calls == []

        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(session, provider="OPENAI", input_tokens=None, output_tokens=None)
            _seed_operation(session, provider="DEEPSEEK", input_tokens=1_000_000, output_tokens=1_000_000)
            set_budget(session, enabled=True, hard_stop_usd="0.01", period="30d", unknown_usage_policy="deny")
            summary = summarize_usage(session)
        openai_bucket = next(item for item in summary["by_provider"] if item["provider"] == "OPENAI")
        deepseek_bucket = next(item for item in summary["by_provider"] if item["provider"] == "DEEPSEEK")
        assert openai_bucket["unknown_usage_operations"] == 2
        assert openai_bucket["input_tokens"] == 0
        assert Decimal_from(deepseek_bucket["estimated_usd"]) > 0
        blocked = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-budget"),
            json={"first_message": "超预算", "client_request_id": "openai-budget", "confirm_provider_charge": True},
        )
        budget_failed = _wait(client, blocked.json()["operation_id"])
        assert budget_failed["error_code"] in {"BUDGET_HARD_STOP_REACHED", "BUDGET_USAGE_UNTRUSTED"}
        assert openai_calls == []


def Decimal_from(value: str) -> Any:
    from decimal import Decimal

    return Decimal(value)


class _Encoder:
    def embed_query(self, _text: str) -> list[float]:
        vector = [0.0] * 512
        vector[0] = 1.0
        return vector


class _Query:
    def __init__(self, result: HybridAssessmentResult) -> None:
        self.result = result

    def capture_scope_signature(self, *_args: Any, **_kwargs: Any) -> tuple[str]:
        return ("fixed",)

    def search_and_assess_with_status(self, *_args: Any, **_kwargs: Any) -> HybridAssessmentResult:
        return self.result


def test_openai_knowledge_citation_failure_and_insufficient_are_not_false_success(tmp_path: Path) -> None:
    client, store, openai_calls, deepseek_calls = _app(tmp_path)
    settings = cast(Any, client.app).state.settings

    def answer(request: httpx.Request) -> httpx.Response:
        openai_calls.append(request)
        text = "没有编号"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                {"id": "oa-k", "model": "gpt-6-sol", "choices": [{"delta": {"content": text}, "finish_reason": "stop"}]},
                {"id": "oa-k", "model": "gpt-6-sol", "choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}},
            ),
            request=request,
        )

    cast(Any, client.app).state.openai_provider = OpenAIChatProvider(
        timeout_seconds=2, transport=httpx.MockTransport(answer)
    )
    with client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        store.set_secret("provider/openai/api-key", OPENAI_KEY)
        client.post("/api/v1/ai/provider/generation-mode", headers=_headers(), json={"mode": OPENAI_PROVIDER_ID})
        client.post(
            "/api/v1/ai/provider/openai/consent",
            headers=_headers(),
            json={"version": "openai-external-ai-v1"},
        )
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _Encoder()
        worker._retrieval_query_getter = lambda _settings: _Query(_supported_result(data))
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-cite"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {"scope_type": "KNOWLEDGE_BASE", "knowledge_base_id": data.knowledge_base_id},
                "first_message": "什么是向量数据库？",
                "client_request_id": "openai-cite",
                "confirm_provider_charge": True,
            },
        )
        failed = _wait(client, created.json()["operation_id"])
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == "CITATION_CONSTRAINT_FAILED"
        assert len(openai_calls) == 1
        assert deepseek_calls == []

        calls_before = len(openai_calls)
        assessment = assess_evidence([], query_text="资料里没有这个答案")
        worker._retrieval_query_getter = lambda _settings: _Query(
            HybridAssessmentResult(retrieval=HybridSearchResult(()), assessment=assessment)
        )
        refused = client.post(
            "/api/v1/conversations",
            headers=_headers("openai-insufficient"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {"scope_type": "KNOWLEDGE_BASE", "knowledge_base_id": data.knowledge_base_id},
                "first_message": "资料里没有这个答案",
                "client_request_id": "openai-insufficient",
                "confirm_provider_charge": True,
            },
        )
        operation = _wait(client, refused.json()["operation_id"])
        assert operation["error_code"] == "EVIDENCE_INSUFFICIENT"
        assert len(openai_calls) == calls_before
