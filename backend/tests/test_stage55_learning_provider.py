from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient

from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.ai.providers.openai import OPENAI_MODEL, OpenAIChatProvider
from mindmate.application.learning_model_generation import recover_dispatched_learning_operations
from mindmate.application.provider_configuration import OPENAI_PROVIDER_ID, write_setting
from mindmate.application.usage_budget import set_budget, summarize_usage
from mindmate.config import Settings
from mindmate.infrastructure.models import LearningProviderOperation, LearningSession
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore
from test_stage5_source_snapshots import _seed_active_index
from test_stage7_learning_session import (
    ORIGIN,
    PUBLIC_FILE,
    TOPIC,
    _Encoder,
    _headers,
    _Query,
    _supported_public,
)

QUESTION = {
    "prompt_text": "根据资料，单次请求超时对应的数值是多少？",
    "options": ["13 秒", "35 秒", "30 秒", "47 秒"],
    "correct_index": 2,
    "knowledge_point": "超时时间",
    "difficulty": "BASIC",
    "evidence_numbers": [1],
}
FEEDBACK = {
    "explanation": "你的选择需要对照资料里的 30 秒。",
    "strengths": "作答已经提交",
    "missing_points": "请核对原文中的 30 秒",
    "next_step": "再读一次出处",
    "evidence_numbers": [1],
}


def _completion(content: str, model: str) -> dict[str, Any]:
    return {
        "id": "resp-learning-1",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 12, "total_tokens": 32},
    }


def _client(tmp_path: Path, plan: dict[str, Any]) -> tuple[TestClient, list[httpx.Request], list[httpx.Request], InMemoryCredentialStore]:
    deepseek_calls: list[httpx.Request] = []
    openai_calls: list[httpx.Request] = []

    def deepseek_handler(request: httpx.Request) -> httpx.Response:
        deepseek_calls.append(request)
        if plan.get("deepseek") == "down":
            return httpx.Response(503, json={"error": "down"}, request=request)
        if plan.get("deepseek") == "bad":
            content = "不是 JSON"
        else:
            body = json.loads(request.content)
            user = body["messages"][-1]["content"]
            content = json.dumps(FEEDBACK if "用户选择" in user else QUESTION, ensure_ascii=False)
        return httpx.Response(200, json=_completion(content, "deepseek-flash-alias"), request=request)

    def openai_handler(request: httpx.Request) -> httpx.Response:
        openai_calls.append(request)
        body = json.loads(request.content)
        user = body["messages"][-1]["content"]
        content = json.dumps(FEEDBACK if "用户选择" in user else QUESTION, ensure_ascii=False)
        return httpx.Response(200, json=_completion(content, "gpt-6-sol-alias"), request=request)

    settings = Settings(
        data_dir=tmp_path,
        env="test",
        chat_worker_poll_seconds=60,
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
        index_activation_worker_poll_seconds=60,
    )
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://api.deepseek.com",
        transport=httpx.MockTransport(deepseek_handler),
    )
    app.state.openai_provider = OpenAIChatProvider(timeout_seconds=2, transport=httpx.MockTransport(openai_handler))
    return TestClient(app, base_url="http://127.0.0.1"), deepseek_calls, openai_calls, store


def _ready(client: TestClient) -> Any:
    client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    factory = cast(Any, client.app).state.session_factory
    settings = cast(Any, client.app).state.settings
    data = _seed_active_index(factory, settings, content=PUBLIC_FILE.read_text(encoding="utf-8"), display_name="服务超时策略.txt")
    result = _supported_public(data, PUBLIC_FILE.read_text(encoding="utf-8"))
    cast(Any, client.app).state.learning_encoder_getter = lambda: _Encoder()
    cast(Any, client.app).state.learning_query_getter = lambda _settings: _Query(result)
    return data


def _select(client: TestClient, mode: str) -> None:
    selected = client.post(
        "/api/v1/ai/provider/generation-mode",
        headers=_headers(f"mode-{mode}"),
        json={"mode": mode},
    )
    assert selected.status_code == 200, selected.text


def _consent(client: TestClient, mode: str) -> None:
    if mode == OPENAI_PROVIDER_ID:
        path = "/api/v1/ai/provider/openai/consent"
        version = "openai-external-ai-v1"
    else:
        path = "/api/v1/ai/consent"
        version = "deepseek-external-ai-v1"
    accepted = client.post(path, headers=_headers(f"consent-{mode}"), json={"version": version})
    assert accepted.status_code == 200, accepted.text


def _create(client: TestClient, knowledge_base_id: str, key: str, *, confirm: bool) -> httpx.Response:
    return client.post(
        "/api/v1/learning-sessions",
        headers=_headers(key),
        json={
            "knowledge_base_id": knowledge_base_id,
            "topic": TOPIC,
            "goal_text": "记住请求超时上限",
            "target_question_count": 1,
            "client_request_id": key,
            "confirm_provider_charge": confirm,
        },
    )


def test_online_gates_send_nothing_and_mock_stays_local(tmp_path: Path) -> None:
    client, deepseek_calls, openai_calls, store = _client(tmp_path, {})
    with client:
        data = _ready(client)
        plan = client.get("/api/v1/learning/provider-plan")
        assert plan.status_code == 200
        assert plan.json()["requires_charge_confirmation"] is False
        mock_created = _create(client, data.knowledge_base_id, "mock-session", confirm=False)
        assert mock_created.status_code == 200, mock_created.text
        assert mock_created.json()["provider"] == "mock"
        assert mock_created.json()["live_model_called"] is False
        assert deepseek_calls == [] and openai_calls == []

        _select(client, "deepseek")
        unchanged = client.get(f"/api/v1/learning-sessions/{mock_created.json()['learning_session_id']}")
        assert unchanged.json()["provider"] == "mock"
        refused = _create(client, data.knowledge_base_id, "needs-confirm", confirm=False)
        assert refused.status_code == 409
        assert refused.json()["code"] == "PROVIDER_CHARGE_CONFIRMATION_REQUIRED"
        _consent(client, "deepseek")
        missing_key = _create(client, data.knowledge_base_id, "needs-key", confirm=True)
        assert missing_key.status_code == 409
        assert missing_key.json()["code"] == "PROVIDER_NOT_CONFIGURED"
        store.set_secret("provider/deepseek/api-key", "deepseek-fixture")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            set_budget(session, enabled=True, hard_stop_usd="0.0001", soft_remind_usd="0.0001", unknown_usage_policy="deny")
        blocked = _create(client, data.knowledge_base_id, "needs-budget", confirm=True)
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "BUDGET_HARD_STOP_REACHED"
        with factory() as session:
            set_budget(session, enabled=False, hard_stop_usd=None, soft_remind_usd=None, unknown_usage_policy="deny")
            write_setting(session, "restore.provider_reconfirm_required", {"required": True})
            session.commit()
        restored = _create(client, data.knowledge_base_id, "needs-restore", confirm=True)
        assert restored.status_code == 409
        assert restored.json()["code"] == "RESTORE_PROVIDER_RECONFIRM_REQUIRED"
        assert deepseek_calls == [] and openai_calls == []


def test_deepseek_and_openai_publish_one_verified_question_and_review(tmp_path: Path) -> None:
    client, deepseek_calls, openai_calls, store = _client(tmp_path, {})
    with client:
        data = _ready(client)
        store.set_secret("provider/deepseek/api-key", "deepseek-fixture")
        store.set_secret("provider/openai/api-key", "openai-fixture")
        _select(client, "deepseek")
        _consent(client, "deepseek")
        created = _create(client, data.knowledge_base_id, "deepseek-question", confirm=True)
        assert created.status_code == 200, created.text
        payload = created.json()
        assert payload["status"] == "IN_PROGRESS"
        assert payload["provider"] == "DEEPSEEK"
        assert payload["requested_model"] == DEEPSEEK_MODEL
        assert payload["resolved_model"] == "deepseek-flash-alias"
        assert payload["live_model_called"] is True
        assert payload["question_operation_status"] == "COMPLETED"
        question = payload["question"]
        assert question["feedback"] is None
        assert "30" not in question["prompt_text"]
        assert "answer_key" not in created.text
        assert "excerpt" not in created.text
        labels = [item["label"] for item in question["options"]]
        assert labels.count("30 秒") == 1
        replay = _create(client, data.knowledge_base_id, "deepseek-question", confirm=True)
        assert replay.json()["learning_session_id"] == payload["learning_session_id"]
        assert len(deepseek_calls) == 1

        wrong_id = next(item["option_id"] for item in question["options"] if item["label"] != "30 秒")
        wrong = client.post(
            f"/api/v1/learning-questions/{question['question_id']}/attempts",
            headers=_headers("deepseek-answer"),
            json={
                "selected_option": wrong_id,
                "client_request_id": "deepseek-answer",
                "expected_question_version": question["row_version"],
                "confirm_provider_charge": True,
            },
        )
        assert wrong.status_code == 200, wrong.text
        body = wrong.json()
        assert body["result"] == "INCORRECT"
        assert body["explanation_origin"] == "model_verified"
        assert body["live_model_called"] is True
        assert body["provider"] == "DEEPSEEK"
        assert "30 秒" in body["explanation"]
        assert body["citations"][0]["file_name"] == "服务超时策略.txt"
        again = client.post(
            f"/api/v1/learning-questions/{question['question_id']}/attempts",
            headers=_headers("deepseek-answer"),
            json={
                "selected_option": wrong_id,
                "client_request_id": "deepseek-answer",
                "expected_question_version": question["row_version"],
                "confirm_provider_charge": True,
            },
        )
        assert again.json()["result"] == "INCORRECT"
        assert len(deepseek_calls) == 2
        sent = json.loads(deepseek_calls[0].content)
        assert sent["model"] == DEEPSEEK_MODEL
        assert "tools" not in sent
        assert openai_calls == []

        _select(client, OPENAI_PROVIDER_ID)
        frozen = client.get(f"/api/v1/learning-sessions/{payload['learning_session_id']}")
        assert frozen.json()["provider"] == "DEEPSEEK"
        _consent(client, OPENAI_PROVIDER_ID)
        openai_created = _create(client, data.knowledge_base_id, "openai-question", confirm=True)
        assert openai_created.status_code == 200, openai_created.text
        assert openai_created.json()["provider"] == "OPENAI"
        assert openai_created.json()["requested_model"] == OPENAI_MODEL
        assert len(openai_calls) == 1
        assert json.loads(openai_calls[0].content)["model"] == OPENAI_MODEL
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            usage = summarize_usage(session)
        providers = {item["provider"] for item in usage["by_provider"]}
        assert "DEEPSEEK" in providers
        assert "OPENAI" in providers


def test_invalid_output_and_unknown_result_are_not_retried(tmp_path: Path) -> None:
    plan = {"deepseek": "bad"}
    client, deepseek_calls, _openai_calls, store = _client(tmp_path, plan)
    with client:
        data = _ready(client)
        store.set_secret("provider/deepseek/api-key", "deepseek-fixture")
        _select(client, "deepseek")
        _consent(client, "deepseek")
        rejected = _create(client, data.knowledge_base_id, "bad-question", confirm=True)
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "FAILED"
        assert rejected.json()["failure_code"] == "MODEL_OUTPUT_REJECTED"
        assert rejected.json()["question"] is None
        replay = _create(client, data.knowledge_base_id, "bad-question", confirm=True)
        assert replay.json()["learning_session_id"] == rejected.json()["learning_session_id"]
        assert len(deepseek_calls) == 1

    plan["deepseek"] = "down"
    client, deepseek_calls, _openai_calls, store = _client(tmp_path / "down", plan)
    with client:
        data = _ready(client)
        store.set_secret("provider/deepseek/api-key", "deepseek-fixture")
        _select(client, "deepseek")
        _consent(client, "deepseek")
        interrupted = _create(client, data.knowledge_base_id, "down-question", confirm=True)
        assert interrupted.json()["status"] == "FAILED"
        assert interrupted.json()["failure_code"] == "LEARNING_PROVIDER_INTERRUPTED"
        assert len(deepseek_calls) == 1
        replay = _create(client, data.knowledge_base_id, "down-question", confirm=True)
        assert len(deepseek_calls) == 1
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            operation = session.query(LearningProviderOperation).one()
            operation.status = "DISPATCHED"
            operation.completed_at = None
            record = session.get(LearningSession, interrupted.json()["learning_session_id"])
            assert record is not None
            record.status = "PREPARING"
            record.current_question_id = None
            session.commit()
            assert recover_dispatched_learning_operations(session) == 1
            reloaded = session.get(LearningProviderOperation, operation.operation_id)
            assert reloaded is not None
            assert reloaded.status == "INTERRUPTED"
        assert len(deepseek_calls) == 1
