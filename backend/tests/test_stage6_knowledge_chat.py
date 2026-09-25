from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from mindmate.ai.providers.mock import MockChatProvider
from mindmate.application.evidence_gate import assess_evidence, unavailable_assessment
from mindmate.application.hybrid_search import HybridAssessmentResult, HybridSearchResult
from mindmate.application.source_snapshots import purge_source_snapshots_for_files
from mindmate.config import Settings
from mindmate.main import create_app
from test_stage5_source_snapshots import _seed_active_index, _supported_result

ORIGIN = "http://127.0.0.1:5173"


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


def _headers(key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key}


def _wait(client: TestClient, operation_id: str) -> dict[str, Any]:
    for _ in range(200):
        payload = client.get(f"/api/v1/ai-operations/{operation_id}").json()
        if payload["status"] not in {"QUEUED", "RUNNING", "STOPPING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("knowledge chat operation did not finish")


def _runtime(tmp_path: Path, provider: MockChatProvider, result: HybridAssessmentResult):
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    client = TestClient(app, base_url="http://127.0.0.1")
    client.__enter__()
    client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    worker = cast(Any, client.app).state.chat_worker
    worker._retrieval_query_encoder_getter = lambda: _Encoder()
    worker._retrieval_query_getter = lambda _settings: _Query(result)
    return client, cast(Any, client.app).state.session_factory


def test_supported_knowledge_chat_binds_real_citation_and_survives_refresh(tmp_path: Path) -> None:
    provider = MockChatProvider(response_factory=lambda _request: "资料结论 [1]")
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        result = _supported_result(data)
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _Encoder()
        worker._retrieval_query_getter = lambda _settings: _Query(result)
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-supported-001"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": "什么是向量数据库？",
                "client_request_id": "knowledge-supported-client-001",
            },
        )
        assert created.status_code == 202, created.text
        operation = _wait(client, created.json()["operation_id"])
        assert operation["status"] == "COMPLETED"
        assert operation["answer_version"]["citations"][0]["file_name"] == "vector-notes.txt"
        assert operation["assistant_message"]["citations"][0]["source_status"] == "AVAILABLE"
        conversation_id = created.json()["conversation_id"]
        refreshed = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert refreshed.status_code == 200
        assert refreshed.json()["items"][1]["citations"][0]["display_number"] == 1
        assert provider.calls and provider.calls[0].task_type == "RAG_ANSWER"
        assert provider.calls[0].evidence_blocks[0]["file_name"] == "vector-notes.txt"
        citation_id = operation["answer_version"]["citations"][0]["citation_id"]
        with factory() as session:
            purge_source_snapshots_for_files(session, [data.file_id])
            session.commit()
        purged = client.get(f"/api/v1/citations/{citation_id}")
        assert purged.status_code == 200
        assert purged.json()["source_status"] == "SOURCE_DELETED"
        assert purged.json()["excerpt"] is None


def test_insufficient_knowledge_chat_refuses_without_provider_or_citation(tmp_path: Path) -> None:
    provider = MockChatProvider(response_factory=lambda _request: "不应调用")
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        assessment = assess_evidence([], query_text="资料里没有这个答案")
        result = HybridAssessmentResult(
            retrieval=HybridSearchResult(()), assessment=assessment
        )
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _Encoder()
        worker._retrieval_query_getter = lambda _settings: _Query(result)
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-insufficient-001"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": "资料里没有这个答案",
            },
        )
        operation = _wait(client, created.json()["operation_id"])
        assert operation["status"] == "COMPLETED"
        assert operation["error_code"] == "EVIDENCE_INSUFFICIENT"
        assert operation["answer_version"]["citations"] == []
        assert "资料不足" in operation["assistant_message"]["content"]
        assert provider.calls == []


def test_unavailable_knowledge_chat_is_distinct_and_does_not_call_provider(tmp_path: Path) -> None:
    provider = MockChatProvider()
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        result = HybridAssessmentResult(
            retrieval=None,
            assessment=unavailable_assessment(
                "MODEL_MISSING_OFFLINE", query_text="知识库问题", route="embedding"
            ),
            retrieval_error_code="MODEL_MISSING_OFFLINE",
            retrieval_error_route="embedding",
        )
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _Encoder()
        worker._retrieval_query_getter = lambda _settings: _Query(result)
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-unavailable-001"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": "知识库问题",
            },
        )
        operation = _wait(client, created.json()["operation_id"])
        assert operation["status"] == "FAILED"
        assert operation["error_code"] == "MODEL_MISSING_OFFLINE"
        assert provider.calls == []
