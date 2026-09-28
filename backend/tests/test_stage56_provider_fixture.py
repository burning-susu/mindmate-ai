from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from mindmate.application.provider_configuration import (
    EXTERNAL_AI_CONSENT_VERSION,
    OPENAI_CONSENT_VERSION,
    OPENAI_PROVIDER_ID,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import LearningProviderOperation
from mindmate.main import create_app
from test_stage5_source_snapshots import _seed_active_index
from test_stage7_learning_session import (
    ORIGIN,
    PUBLIC_FILE,
    _Encoder,
    _Query,
    _supported_public,
)


def test_learning_provider_fixture_is_test_only_and_reports_safe_call_metadata(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only available in test environments"):
        create_app(Settings(data_dir=tmp_path, env="development", learning_provider_fixture=True))

    app = create_app(Settings(data_dir=tmp_path, env="test", learning_provider_fixture=True))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        calls = client.get("/api/v1/testing/provider-fixture/calls")
        assert calls.status_code == 200
        assert calls.json() == {"calls": []}

        fixture = app.state.provider_fixture
        response = fixture.transport("DEEPSEEK").handle_request(
            httpx.Request(
                "POST",
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": "Bearer fixture-only"},
                json={
                    "model": "deepseek-flash",
                    "messages": [{"role": "user", "content": "学习主题：超时"}],
                },
            )
        )
        assert response.status_code == 200

        calls = client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]
        assert calls == [
            {
                "provider": "DEEPSEEK",
                "host": "api.deepseek.com",
                "requested_model": "deepseek-flash",
                "request_kind": "question",
                "authorization_present": True,
            }
        ]


def test_test_fixture_route_is_not_registered_for_normal_runtime(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, env="test", learning_provider_fixture=False))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        response = client.get("/api/v1/testing/provider-fixture/calls")
        assert response.status_code == 404
        fail_next = client.post(
            "/api/v1/testing/provider-fixture/fail-next-question",
            headers={"Origin": ORIGIN, "Idempotency-Key": "fixture-fail-disabled"},
            json={"provider": "OPENAI"},
        )
        assert fail_next.status_code == 404


def test_failure_switch_is_one_provider_only_and_never_falls_back(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, env="test", learning_provider_fixture=True))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        scheduled = client.post(
            "/api/v1/testing/provider-fixture/fail-next-question",
            headers={"Origin": ORIGIN, "Idempotency-Key": "fixture-fail-only"},
            json={"provider": "OPENAI"},
        )
        assert scheduled.status_code == 200
        assert scheduled.json() == {"provider": "OPENAI", "scheduled": True}

        fixture = app.state.provider_fixture
        with pytest.raises(httpx.ReadTimeout):
            fixture.transport("OPENAI").handle_request(
                httpx.Request(
                    "POST",
                    "https://api.openai.com/v1/chat/completions",
                    json={
                        "model": "gpt-6-sol",
                        "messages": [{"role": "user", "content": "synthetic question"}],
                    },
                )
            )
        calls = client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]
        assert calls == [
            {
                "provider": "OPENAI",
                "host": "api.openai.com",
                "requested_model": "gpt-6-sol",
                "request_kind": "question",
                "authorization_present": False,
            }
        ]


def test_fixed_provider_fixture_runs_real_learning_business_path_for_both_providers(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        learning_provider_fixture=True,
        allowed_origins=(ORIGIN,),
        chat_worker_poll_seconds=60,
        parse_worker_poll_seconds=60,
        knowledge_worker_poll_seconds=60,
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
        index_activation_worker_poll_seconds=60,
        history_purge_poll_seconds=60,
        task_retention_poll_seconds=60,
    )
    app = create_app(settings)
    content = PUBLIC_FILE.read_text(encoding="utf-8")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = app.state.session_factory
        data = _seed_active_index(
            factory,
            settings,
            content=content,
            display_name="服务超时策略.txt",
        )
        app.state.learning_encoder_getter = _Encoder
        app.state.learning_query_getter = lambda _settings: _Query(_supported_public(data, content))

        for provider_id, key_path, consent_path, consent_version, name in (
            (
                "deepseek",
                "/api/v1/ai/provider/key",
                "/api/v1/ai/consent",
                EXTERNAL_AI_CONSENT_VERSION,
                "DEEPSEEK",
            ),
            (
                OPENAI_PROVIDER_ID,
                "/api/v1/ai/provider/openai/key",
                "/api/v1/ai/provider/openai/consent",
                OPENAI_CONSENT_VERSION,
                "OPENAI",
            ),
        ):
            prefix = name.lower()
            headers = {"Origin": ORIGIN, "Idempotency-Key": f"stage56-{prefix}-setup"}
            saved = client.post(key_path, headers=headers, json={"api_key": f"fixture-{prefix}-key"})
            assert saved.status_code == 200, saved.text
            consent = client.post(consent_path, headers=headers, json={"version": consent_version})
            assert consent.status_code == 200, consent.text
            selected = client.post(
                "/api/v1/ai/provider/generation-mode",
                headers=headers,
                json={"mode": provider_id},
            )
            assert selected.status_code == 200, selected.text

            request_id = f"stage56-{prefix}-question"
            created_response = client.post(
                "/api/v1/learning-sessions",
                headers={"Origin": ORIGIN, "Idempotency-Key": request_id},
                json={
                    "knowledge_base_id": data.knowledge_base_id,
                    "topic": "API 单次请求超时时间",
                    "goal_text": "记住资料中的请求超时值",
                    "target_question_count": 1,
                    "client_request_id": request_id,
                    "confirm_provider_charge": True,
                },
            )
            assert created_response.status_code == 200, created_response.text
            created = created_response.json()
            assert created["provider"] == name
            assert created["live_model_called"] is True
            assert created["question"]["feedback"] is None
            assert "answer_key" not in created_response.text

            question = created["question"]
            wrong_option = question["options"][0]["option_id"]
            feedback_key = f"stage56-{prefix}-feedback"
            feedback_response = client.post(
                f"/api/v1/learning-questions/{question['question_id']}/attempts",
                headers={"Origin": ORIGIN, "Idempotency-Key": feedback_key},
                json={
                    "selected_option": wrong_option,
                    "expected_question_version": question["row_version"],
                    "client_request_id": feedback_key,
                    "confirm_provider_charge": True,
                },
            )
            assert feedback_response.status_code == 200, feedback_response.text
            feedback = feedback_response.json()
            assert feedback["provider"] == name
            assert feedback["result"] == "INCORRECT"
            assert feedback["live_model_called"] is True
            assert feedback["citations"][0]["file_name"] == "服务超时策略.txt"

        calls = client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]
        assert [item["provider"] for item in calls] == [
            "DEEPSEEK",
            "DEEPSEEK",
            "OPENAI",
            "OPENAI",
        ]
        assert [item["request_kind"] for item in calls] == [
            "question",
            "feedback",
            "question",
            "feedback",
        ]
        assert [item["host"] for item in calls] == [
            "api.deepseek.com",
            "api.deepseek.com",
            "api.openai.com",
            "api.openai.com",
        ]
        assert all(item["authorization_present"] for item in calls)
        with factory() as session:
            operations = list(session.query(LearningProviderOperation).order_by(LearningProviderOperation.created_at))
        assert sorted(item.provider for item in operations) == [
            "DEEPSEEK",
            "DEEPSEEK",
            "OPENAI",
            "OPENAI",
        ]

        scheduled = client.post(
            "/api/v1/testing/provider-fixture/fail-next-question",
            headers={"Origin": ORIGIN, "Idempotency-Key": "stage56-failure-setup"},
            json={"provider": "OPENAI"},
        )
        assert scheduled.status_code == 200
        failed_request_id = "stage56-openai-failed-question"
        failed_response = client.post(
            "/api/v1/learning-sessions",
            headers={"Origin": ORIGIN, "Idempotency-Key": failed_request_id},
            json={
                "knowledge_base_id": data.knowledge_base_id,
                "topic": "API 请求失败时的服务边界",
                "goal_text": "保持用户选定的服务",
                "target_question_count": 1,
                "client_request_id": failed_request_id,
                "confirm_provider_charge": True,
            },
        )
        assert failed_response.status_code == 200, failed_response.text
        assert failed_response.json()["failure_code"] == "LEARNING_PROVIDER_INTERRUPTED"
        calls_after_failure = client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]
        assert len(calls_after_failure) == 5
        assert calls_after_failure[-1]["provider"] == "OPENAI"
        assert [item["provider"] for item in calls_after_failure].count("DEEPSEEK") == 2
