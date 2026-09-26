from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from mindmate.ai.embeddings.manifest import MODEL_ARTIFACT_FINGERPRINT
from mindmate.ai.providers.mock import MockChatProvider
from mindmate.application.evidence_gate import assess_evidence, unavailable_assessment
from mindmate.application.hybrid_search import HybridAssessmentResult, HybridSearchResult
from mindmate.application.retrieval_test_queries import RetrievalQueryEncoderError
from mindmate.application.source_snapshots import purge_source_snapshots_for_files
from mindmate.config import Settings
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore
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


def test_external_knowledge_request_is_bounded_and_citation_constraint_blocks_success(
    tmp_path: Path,
) -> None:
    provider = MockChatProvider(response_factory=lambda _request: "没有引用编号")
    provider.requires_external_transfer = True
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    app.state.credential_store = InMemoryCredentialStore()
    app.state.credential_store.set_secret(
        "provider/deepseek/api-key", "fixture-secret-do-not-persist"
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        consent = client.post(
            "/api/v1/ai/consent",
            headers=_headers("knowledge-external-consent"),
            json={"version": "deepseek-external-ai-v1"},
        )
        assert consent.status_code == 200
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        result = _supported_result(data)
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _Encoder()
        worker._retrieval_query_getter = lambda _settings: _Query(result)
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-external-001"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": "什么是向量数据库？",
                "client_request_id": "knowledge-external-client-001",
            },
        )
        assert created.status_code == 202, created.text
        failed = _wait(client, created.json()["operation_id"])
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == "CITATION_CONSTRAINT_FAILED"
        assert len(provider.calls) == 1
        sent = provider.calls[0]
        assert sent.max_output_tokens == 256
        assert sent.evidence_blocks
        assert len(sent.evidence_blocks[0]["excerpt"]) <= 480
        outbound = "\n".join(
            [
                sent.system_instructions,
                *(block["excerpt"] for block in sent.evidence_blocks),
                sent.messages[-1]["content"],
            ]
        )
        assert len(outbound) <= 2048

        provider.response_factory = lambda _request: "资料结论 [1]"
        created_ok = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-external-002"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": "什么是向量数据库？",
                "client_request_id": "knowledge-external-client-002",
            },
        )
        completed = _wait(client, created_ok.json()["operation_id"])
        assert completed["status"] == "COMPLETED"
        assert completed["answer_version"]["citations"][0]["file_name"] == "vector-notes.txt"
        assert len(provider.calls) == 2


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


def test_query_encoding_failure_logs_safe_diagnostics_only(tmp_path: Path, capsys) -> None:
    provider = MockChatProvider()
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    question = "私人问题不应出现在日志 UNIQUE-QUESTION-36"
    leaked_path = r"C:\Users\secret\mindmate\model.onnx"

    class _FailingEncoder:
        def embed_query(self, text: str) -> list[float]:
            raise RetrievalQueryEncoderError(
                "MODEL_UNAVAILABLE",
                phase="status_precheck",
                model_state="INSTALLING",
            ) from RuntimeError(f"{text} {leaked_path}")

    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _FailingEncoder()
        worker._retrieval_query_getter = lambda _settings: _Query(
            HybridAssessmentResult(
                retrieval=HybridSearchResult(()),
                assessment=assess_evidence([], query_text="unused"),
            )
        )
        capsys.readouterr()
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-model-unavailable-log-001"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": question,
                "client_request_id": "knowledge-model-unavailable-client-001",
            },
        )
        assert created.status_code == 202, created.text
        operation = _wait(client, created.json()["operation_id"])
        captured = capsys.readouterr()
    assert operation["status"] == "FAILED"
    assert operation["error_code"] == "MODEL_UNAVAILABLE"
    assert provider.calls == []
    message = captured.err
    assert "[uvicorn.error]" in message
    assert "knowledge_chat_query_encoding_failed" in message
    assert f"operation_id={operation['operation_id']}" in message
    assert "request_id=" in message
    assert f"index_version_id={data.index_version_id}" in message
    assert f"model_fingerprint={MODEL_ARTIFACT_FINGERPRINT}" in message
    assert "exception_type=RetrievalQueryEncoderError" in message
    assert "encoder_phase=status_precheck" in message
    assert "model_state=INSTALLING" in message
    assert "error_code=MODEL_UNAVAILABLE" in message
    assert question not in message
    assert leaked_path not in message
    assert "secret" not in message


def test_unexpected_query_encoder_exception_does_not_log_the_question(
    tmp_path: Path, capsys
) -> None:
    provider = MockChatProvider()
    settings = Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01)
    app = create_app(settings)
    app.state.chat_provider = provider
    question = "另一条私人问题 UNIQUE-QUESTION-36B"

    class _UnexpectedEncoder:
        def embed_query(self, text: str) -> list[float]:
            raise RuntimeError(f"{text} at C:\\private\\cache\\model.onnx")

    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _UnexpectedEncoder()
        worker._retrieval_query_getter = lambda _settings: _Query(
            HybridAssessmentResult(
                retrieval=HybridSearchResult(()),
                assessment=assess_evidence([], query_text="unused"),
            )
        )
        capsys.readouterr()
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("knowledge-model-unexpected-log-001"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": question,
            },
        )
        operation = _wait(client, created.json()["operation_id"])
        captured = capsys.readouterr()
    assert operation["status"] == "FAILED"
    assert operation["error_code"] == "MODEL_UNAVAILABLE"
    assert provider.calls == []
    message = captured.err
    assert "[uvicorn.error]" in message
    assert "exception_type=RuntimeError" in message
    assert "encoder_phase=embed_query" in message
    assert "error_code=MODEL_UNAVAILABLE" in message
    assert question not in message
    assert "private" not in message
    assert "model.onnx" not in message
