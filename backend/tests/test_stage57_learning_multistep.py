from __future__ import annotations

import hashlib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from mindmate.application.evidence_gate import assess_evidence
from mindmate.application.hybrid_search import HybridAssessmentResult, HybridSearchResult
from mindmate.application.provider_configuration import (
    EXTERNAL_AI_CONSENT_VERSION,
    OPENAI_CONSENT_VERSION,
    OPENAI_PROVIDER_ID,
)
from mindmate.application.source_snapshots import create_source_snapshots
from mindmate.config import Settings
from mindmate.infrastructure.db import create_sqlite_engine
from mindmate.infrastructure.models import (
    Chunk,
    EmbeddingConfig,
    EmbeddingRecord,
    FtsChunkMap,
    LearningAttempt,
    LearningFeedback,
    LearningProviderOperation,
    LearningQuestion,
    new_id,
)
from mindmate.main import create_app
from test_stage5_source_snapshots import SnapshotData, _seed_active_index
from test_stage7_learning_session import (
    ORIGIN,
    _Encoder,
    _forced_supported,
)

FACTS = (
    "API请求超时为30 秒。",
    "Worker租约时长为45 秒。",
    "任务重试冷却间隔为12 秒。",
)


class _SequenceQuery:
    def __init__(self, data: Sequence[SnapshotData | None]) -> None:
        self._data = tuple(data)
        self._position = 0

    def capture_scope_signature(self, *_args: Any, **_kwargs: Any) -> tuple[str]:
        return ("fixed",)

    def search_and_assess_with_status(self, *_args: Any, **_kwargs: Any) -> HybridAssessmentResult:
        current = self._data[min(self._position, len(self._data) - 1)]
        self._position += 1
        if current is None:
            insufficient = assess_evidence([], query_text="学习资料")
            return HybridAssessmentResult(
                retrieval=HybridSearchResult(()),
                assessment=insufficient,
            )
        return _forced_supported(current, current.content)


def _settings(tmp_path: Path, *, fixture: bool = False) -> Settings:
    return Settings(
        data_dir=tmp_path,
        env="test",
        learning_provider_fixture=fixture,
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


def _install_query(client: TestClient, query: _SequenceQuery) -> None:
    app_state = cast(Any, client.app).state
    app_state.learning_encoder_getter = _Encoder
    app_state.learning_query_getter = lambda _settings: query


def _add_fact_chunks(factory: Any, data: SnapshotData, facts: tuple[str, ...]) -> list[SnapshotData]:
    seeded = [replace(data, content=facts[0])]
    with factory() as session:
        base = session.get(Chunk, data.chunk_id)
        assert base is not None
        embedding_config = session.get(EmbeddingConfig, data.embedding_config_id)
        assert embedding_config is not None
        now = datetime.now(UTC)
        for sequence_number, content in enumerate(facts[1:], start=1):
            chunk_id = new_id()
            session.add(
                Chunk(
                    chunk_id=chunk_id,
                    file_id=base.file_id,
                    parse_revision_id=base.parse_revision_id,
                    chunking_config_id=base.chunking_config_id,
                    sequence_number=sequence_number,
                    heading_path=["合成资料", f"事实 {sequence_number + 1}"],
                    page_start=None,
                    page_end=None,
                    slide_number=None,
                    line_start=sequence_number + 1,
                    line_end=sequence_number + 1,
                    source_kind="PARAGRAPH",
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    length_unit="UNICODE_CHARACTER",
                    length_value=len(content),
                    created_at=now,
                )
            )
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            session.add_all(
                [
                    FtsChunkMap(
                        index_version_id=data.index_version_id,
                        chunk_id=chunk_id,
                        file_id=base.file_id,
                        parse_revision_id=base.parse_revision_id,
                        chunking_config_id=base.chunking_config_id,
                        content_hash=content_hash,
                    ),
                    EmbeddingRecord(
                        embedding_record_id=new_id(),
                        chunk_id=chunk_id,
                        embedding_config_id=data.embedding_config_id,
                        vector_store_record_id=new_id(),
                        config_fingerprint=embedding_config.config_fingerprint,
                        vector_hash=hashlib.sha256(f"{chunk_id}:fixture".encode()).hexdigest(),
                        status="READY",
                        created_at=now,
                    ),
                ]
            )
            seeded.append(replace(data, chunk_id=chunk_id, content=content))
        session.commit()
    return seeded


def _headers(key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key}


def _create_session(
    client: TestClient,
    data: SnapshotData,
    *,
    key: str,
    target_count: int | None = 1,
    confirm_charge: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "knowledge_base_id": data.knowledge_base_id,
        "topic": "API 请求与 Worker 时长参数",
        "goal_text": "区分资料中的时长事实",
        "client_request_id": key,
        "confirm_provider_charge": confirm_charge,
    }
    if target_count is not None:
        body["target_question_count"] = target_count
    response = client.post("/api/v1/learning-sessions", headers=_headers(key), json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["question"] is not None, (
        payload["failure_code"], payload["failure_detail"], payload["status"]
    )
    return payload


def _answer_question(
    client: TestClient,
    factory: Any,
    question: dict[str, Any],
    *,
    key: str,
    confirm_charge: bool = False,
) -> dict[str, Any]:
    with factory() as session:
        stored = session.get(LearningQuestion, question["question_id"])
        assert stored is not None
        correct_id = str(stored.answer_key_json["option_id"])
    response = client.post(
        f"/api/v1/learning-questions/{question['question_id']}/attempts",
        headers=_headers(key),
        json={
            "selected_option": correct_id,
            "client_request_id": key,
            "expected_question_version": question["row_version"],
            "confirm_provider_charge": confirm_charge,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _next_question(
    client: TestClient,
    session_payload: dict[str, Any],
    *,
    key: str,
    confirm_charge: bool = False,
) -> Any:
    body = {
        "expected_session_version": session_payload["row_version"],
        "client_request_id": key,
        "confirm_provider_charge": confirm_charge,
    }
    return client.post(
        f"/api/v1/learning-sessions/{session_payload['learning_session_id']}/next-question",
        headers=_headers(key),
        json=body,
    )


def _enable_provider(client: TestClient, provider_id: str) -> None:
    is_openai = provider_id == OPENAI_PROVIDER_ID
    key_path = "/api/v1/ai/provider/openai/key" if is_openai else "/api/v1/ai/provider/key"
    consent_path = "/api/v1/ai/provider/openai/consent" if is_openai else "/api/v1/ai/consent"
    consent_version = OPENAI_CONSENT_VERSION if is_openai else EXTERNAL_AI_CONSENT_VERSION
    key = "fixture-openai-stage57" if is_openai else "fixture-deepseek-stage57"
    headers = _headers(f"stage57-{provider_id}-setup")
    assert client.post(key_path, headers=headers, json={"api_key": key}).status_code == 200
    assert client.post(
        consent_path, headers=headers, json={"version": consent_version}
    ).status_code == 200
    selected = client.post(
        "/api/v1/ai/provider/generation-mode",
        headers=headers,
        json={"mode": provider_id},
    )
    assert selected.status_code == 200, selected.text


def test_target_count_defaults_and_accepts_one_to_five(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        rows = _add_fact_chunks(factory, data, FACTS)
        query = _SequenceQuery([rows[0], rows[1]])
        _install_query(client, query)

        for count in (0, 6):
            key = f"stage57-invalid-count-{count}"
            response = client.post(
                "/api/v1/learning-sessions",
                headers=_headers(key),
                json={
                    "knowledge_base_id": data.knowledge_base_id,
                    "topic": "时长参数",
                    "goal_text": "区分时长",
                    "target_question_count": count,
                    "client_request_id": key,
                },
            )
            assert response.status_code == 422

        defaulted = _create_session(client, data, key="stage57-default-count", target_count=None)
        assert defaulted["target_question_count"] == 1
        assert defaulted["plan"]["target_question_count"] == 1
        candidate_check = _forced_supported(rows[1], rows[1].content)
        second_fact_snapshot = create_source_snapshots(
            factory,
            knowledge_base_id=data.knowledge_base_id,
            expected_index_version_id=data.index_version_id,
            result=candidate_check,
        )
        assert second_fact_snapshot[0].chunk_id == rows[1].chunk_id
        five = _create_session(client, data, key="stage57-five-count", target_count=5)
        assert five["target_question_count"] == 5
        assert five["plan"]["target_question_count"] == 5
        assert five["question"]["sequence_number"] == 1
        assert five["question"]["feedback"] is None


def test_synthetic_fact_chunks_keep_snapshot_and_index_evidence_valid(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        rows = _add_fact_chunks(factory, data, FACTS[:2])
        result = _forced_supported(rows[1], FACTS[1])
        snapshots = create_source_snapshots(
            factory,
            knowledge_base_id=data.knowledge_base_id,
            expected_index_version_id=data.index_version_id,
            result=result,
        )
        assert len(snapshots) == 1
        assert snapshots[0].chunk_id == rows[1].chunk_id


def test_mock_session_runs_three_distinct_questions_replays_and_restores(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        rows = _add_fact_chunks(factory, data, FACTS)
        query = _SequenceQuery(rows)
        _install_query(client, query)

        created = _create_session(client, data, key="stage57-mock-create", target_count=3)
        session_id = created["learning_session_id"]
        first = created["question"]
        assert first["sequence_number"] == 1
        assert first["feedback"] is None
        assert "answer_key" not in client.get(f"/api/v1/learning-sessions/{session_id}").text
        before_answer = _next_question(client, created, key="stage57-too-soon")
        assert before_answer.status_code == 409
        assert before_answer.json()["code"] == "ANSWER_REQUIRED"

        first_feedback = _answer_question(client, factory, first, key="stage57-answer-1")
        assert first_feedback["result"] == "CORRECT"
        after_first = client.get(f"/api/v1/learning-sessions/{session_id}").json()
        assert after_first["completed_question_count"] == 1
        assert after_first["status"] == "IN_PROGRESS"
        request_body = {
            "expected_session_version": after_first["row_version"],
            "client_request_id": "stage57-next-2",
            "confirm_provider_charge": False,
        }

        def request_same_next() -> Any:
            return client.post(
                f"/api/v1/learning-sessions/{session_id}/next-question",
                headers=_headers("stage57-next-2"),
                json=request_body,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            raced = list(pool.map(lambda _index: request_same_next(), range(2)))
        assert all(response.status_code == 200 for response in raced), [
            (response.status_code, response.text) for response in raced
        ]
        after_race = client.get(f"/api/v1/learning-sessions/{session_id}").json()
        assert len(after_race["questions"]) == 2, (
            after_race["status"], after_race["failure_code"], after_race["failure_detail"]
        )
        second = after_race["question"]
        assert second["sequence_number"] == 2
        assert "45" not in second["prompt_text"]
        replay = request_same_next()
        assert replay.status_code == 200
        assert len(replay.json()["questions"]) == 2

        second_feedback = _answer_question(client, factory, second, key="stage57-answer-2")
        assert second_feedback["citations"][0]["excerpt"] == FACTS[1]
        after_second = client.get(f"/api/v1/learning-sessions/{session_id}").json()
        third_response = _next_question(client, after_second, key="stage57-next-3")
        assert third_response.status_code == 200, third_response.text
        third = third_response.json()["question"]
        assert third["sequence_number"] == 3
        assert "12" not in third["prompt_text"]
        third_feedback = _answer_question(
            client, factory, third, key="stage57-answer-3"
        )
        assert third_feedback["citations"][0]["excerpt"] == FACTS[2]
        final = client.get(f"/api/v1/learning-sessions/{session_id}").json()
        assert final["status"] == "COMPLETED"
        assert final["completed_question_count"] == 3
        assert [item["sequence_number"] for item in final["questions"]] == [1, 2, 3]
        cited_chunks = {
            item["feedback"]["citations"][0]["chunk_id"] for item in final["questions"]
        }
        assert len(cited_chunks) == 3
        assert final["result"] == {
            "planned_question_count": 3,
            "completed_question_count": 3,
            "correct_count": 3,
            "incorrect_count": 0,
            "unjudged_count": 0,
            "end_reason": "PLAN_COMPLETED",
        }
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(LearningQuestion)) == 3
            assert session.scalar(select(func.count()).select_from(LearningAttempt)) == 3
            assert session.scalar(select(func.count()).select_from(LearningFeedback)) == 3
            saved = list(
                session.scalars(
                    select(LearningQuestion)
                    .where(LearningQuestion.learning_session_id == session_id)
                    .order_by(LearningQuestion.sequence_number)
                )
            )
            assert len({item.generated_request_id for item in saved}) == 3

    restarted = create_app(settings)
    with TestClient(restarted, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        restored = client.get(f"/api/v1/learning-sessions/{session_id}").json()
        assert restored["scope"]["index_version_id"] == data.index_version_id
        assert restored["current_question_id"] == third["question_id"]
        assert len(restored["questions"]) == 3
        assert restored["questions"][1]["feedback"]["citations"][0]["excerpt"] == FACTS[1]


def test_early_finish_and_insufficient_evidence_keep_saved_feedback(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        rows = _add_fact_chunks(factory, data, FACTS[:2])
        query = _SequenceQuery([rows[0], None])
        _install_query(client, query)
        created = _create_session(client, data, key="stage57-early-create", target_count=3)
        _answer_question(client, factory, created["question"], key="stage57-early-answer")
        after_answer = client.get(
            f"/api/v1/learning-sessions/{created['learning_session_id']}"
        ).json()
        ended = _next_question(client, after_answer, key="stage57-no-more-evidence")
        assert ended.status_code == 200, ended.text
        body = ended.json()
        assert body["status"] == "COMPLETED"
        assert body["completed_question_count"] == 1
        assert len(body["questions"]) == 1
        assert body["questions"][0]["feedback"]["result"] == "CORRECT"
        assert body["result"]["planned_question_count"] == 3
        assert body["result"]["completed_question_count"] == 1
        assert body["result"]["end_reason"] == "EVIDENCE_EXHAUSTED"


def test_duplicate_fact_ends_early_without_creating_or_scoring_a_duplicate(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        _install_query(client, _SequenceQuery([data, data]))
        created = _create_session(client, data, key="stage57-duplicate-create", target_count=2)
        _answer_question(client, factory, created["question"], key="stage57-duplicate-answer")
        answered = client.get(
            f"/api/v1/learning-sessions/{created['learning_session_id']}"
        ).json()
        response = _next_question(client, answered, key="stage57-duplicate-next")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "COMPLETED"
        assert result["result"]["end_reason"] == "EVIDENCE_EXHAUSTED"
        assert result["completed_question_count"] == 1
        assert len(result["questions"]) == 1
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(LearningQuestion)) == 1
            assert session.scalar(select(func.count()).select_from(LearningAttempt)) == 1


def test_next_question_rejects_evidence_from_another_knowledge_base(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        other_scope = _seed_active_index(
            factory, settings, content=FACTS[1], display_name="服务超时策略.txt"
        )
        query = _SequenceQuery([data, other_scope])
        _install_query(client, query)
        created = _create_session(client, data, key="stage57-cross-scope-create", target_count=2)
        _answer_question(client, factory, created["question"], key="stage57-cross-scope-answer")
        answered = client.get(
            f"/api/v1/learning-sessions/{created['learning_session_id']}"
        ).json()
        response = _next_question(client, answered, key="stage57-cross-scope-next")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "SOURCE_INVALID", (
            result["status"], result["failure_code"], result["failure_detail"]
        )
        assert result["failure_code"] == "RETRIEVAL_EVIDENCE_INVALID"
        assert result["completed_question_count"] == 1
        assert len(result["questions"]) == 1
        assert result["questions"][0]["feedback"]["citations"][0]["file_id"] == data.file_id


def test_explicit_finish_is_idempotent_and_reports_actual_count(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        _install_query(client, _SequenceQuery([data]))
        created = _create_session(client, data, key="stage57-finish-create", target_count=3)
        _answer_question(client, factory, created["question"], key="stage57-finish-answer")
        latest = client.get(
            f"/api/v1/learning-sessions/{created['learning_session_id']}"
        ).json()
        request = {
            "expected_session_version": latest["row_version"],
        }
        url = f"/api/v1/learning-sessions/{created['learning_session_id']}/finish"
        finished = client.post(url, headers=_headers("stage57-user-finish"), json=request)
        assert finished.status_code == 200, finished.text
        assert finished.json()["result"]["planned_question_count"] == 3
        assert finished.json()["result"]["completed_question_count"] == 1
        assert finished.json()["result"]["end_reason"] == "USER_ENDED"
        repeated = client.post(url, headers=_headers("stage57-user-finish"), json=request)
        assert repeated.status_code == 200
        assert repeated.json()["row_version"] == finished.json()["row_version"]


def test_online_deepseek_and_openai_generate_two_confirmed_questions_each(tmp_path: Path) -> None:
    settings = _settings(tmp_path, fixture=True)
    app = create_app(settings)
    content = FACTS[0]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=content, display_name="服务超时策略.txt"
        )
        rows = _add_fact_chunks(factory, data, FACTS[:2])
        query = _SequenceQuery(rows * 2)
        _install_query(client, query)

        for provider_id, expected_provider in (("deepseek", "DEEPSEEK"), (OPENAI_PROVIDER_ID, "OPENAI")):
            _enable_provider(client, provider_id)
            prefix = provider_id.replace("_", "-")
            created = _create_session(
                client,
                data,
                key=f"stage57-{prefix}-create",
                target_count=2,
                confirm_charge=True,
            )
            assert created["provider"] == expected_provider
            first = created["question"]
            _answer_question(
                client, factory, first, key=f"stage57-{prefix}-answer-1", confirm_charge=True
            )
            after_first = client.get(
                f"/api/v1/learning-sessions/{created['learning_session_id']}"
            ).json()
            calls_before = client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]
            refused = _next_question(
                client,
                after_first,
                key=f"stage57-{prefix}-next-2",
                confirm_charge=False,
            )
            assert refused.status_code == 409
            assert refused.json()["code"] == "PROVIDER_CHARGE_CONFIRMATION_REQUIRED"
            assert client.get("/api/v1/testing/provider-fixture/calls").json()["calls"] == calls_before

            await_other_provider = client.post(
                "/api/v1/ai/provider/generation-mode",
                headers=_headers(f"stage57-{prefix}-change-global-mode"),
                json={"mode": "mock"},
            )
            assert await_other_provider.status_code == 200
            next_response = _next_question(
                client,
                after_first,
                key=f"stage57-{prefix}-next-2",
                confirm_charge=True,
            )
            assert next_response.status_code == 200, next_response.text
            second = next_response.json()["question"]
            assert second["sequence_number"] == 2
            assert second["prompt_text"] != first["prompt_text"]
            _answer_question(
                client, factory, second, key=f"stage57-{prefix}-answer-2", confirm_charge=True
            )
            final = client.get(
                f"/api/v1/learning-sessions/{created['learning_session_id']}"
            ).json()
            assert final["provider"] == expected_provider
            assert final["status"] == "COMPLETED"
            assert len(final["questions"]) == 2

        calls = client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]
        for provider in ("DEEPSEEK", "OPENAI"):
            provider_calls = [item for item in calls if item["provider"] == provider]
            assert [item["request_kind"] for item in provider_calls] == [
                "question",
                "feedback",
                "question",
                "feedback",
            ]
            assert all(item["authorization_present"] for item in provider_calls)
        with factory() as session:
            operations = list(session.scalars(select(LearningProviderOperation)))
        assert sum(item.task_type == "LEARNING_QUESTION" for item in operations) == 4
        assert sum(item.task_type == "LEARNING_FEEDBACK" for item in operations) == 4
        assert {item.provider for item in operations} == {"DEEPSEEK", "OPENAI"}


def test_unknown_online_next_question_is_never_resent(tmp_path: Path) -> None:
    settings = _settings(tmp_path, fixture=True)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=FACTS[0], display_name="服务超时策略.txt"
        )
        rows = _add_fact_chunks(factory, data, FACTS[:2])
        query = _SequenceQuery(rows)
        _install_query(client, query)
        _enable_provider(client, "deepseek")
        created = _create_session(
            client,
            data,
            key="stage57-unknown-create",
            target_count=2,
            confirm_charge=True,
        )
        _answer_question(
            client, factory, created["question"], key="stage57-unknown-answer", confirm_charge=True
        )
        after_answer = client.get(
            f"/api/v1/learning-sessions/{created['learning_session_id']}"
        ).json()
        fixture = cast(Any, client.app).state.provider_fixture
        fixture.fail_next_question("DEEPSEEK")
        key = "stage57-unknown-next"
        unknown = _next_question(client, after_answer, key=key, confirm_charge=True)
        assert unknown.status_code == 200, unknown.text
        assert unknown.json()["status"] == "FAILED"
        assert unknown.json()["failure_code"] == "LEARNING_PROVIDER_INTERRUPTED"
        call_count = len(client.get("/api/v1/testing/provider-fixture/calls").json()["calls"])
        replay = _next_question(client, after_answer, key=key, confirm_charge=True)
        assert replay.status_code == 200
        assert replay.json()["completed_question_count"] == 1
        assert len(client.get("/api/v1/testing/provider-fixture/calls").json()["calls"]) == call_count
        with factory() as session:
            question_count = session.scalar(select(func.count()).select_from(LearningQuestion))
            operation = session.scalar(
                select(LearningProviderOperation).where(
                    LearningProviderOperation.task_type == "LEARNING_QUESTION",
                    LearningProviderOperation.client_request_id
                    == f"learning-question-client:{key}",
                )
            )
        assert question_count == 1
        assert operation is not None and operation.status == "INTERRUPTED"


def test_stage57_migration_preserves_legacy_learning_session_row(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.ensure_data_dirs()
    config = Config(str(settings.alembic_ini))
    config.attributes["settings"] = settings
    command.upgrade(config, "b55c0e1a8d27")
    engine = create_sqlite_engine(settings.database_path)
    session_id = new_id()
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(learning_sessions)")
        }
        values: dict[str, Any] = {
            "learning_session_id": session_id,
            "topic": "旧单题会话",
            "goal_type": "CUSTOM",
            "goal_text": "继续查看原题",
            "knowledge_base_id": "legacy-kb",
            "target_question_count": 1,
            "initial_difficulty": "BASIC",
            "current_difficulty": "BASIC",
            "status": "IN_PROGRESS",
            "completed_question_count": 0,
            "idempotency_key": "legacy-idempotency",
            "client_request_id": "legacy-client",
            "request_hash": "a" * 64,
            "provider": "mock",
            "live_model_called": False,
            "created_at": "2026-09-27T00:00:00+00:00",
            "updated_at": "2026-09-27T00:00:00+00:00",
            "row_version": 1,
        }
        required = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(learning_sessions)")
            if row[3] and row[4] is None and not row[5]
        }
        assert required <= values.keys()
        insert_columns = sorted(columns.intersection(values))
        bind = ", ".join(f":{name}" for name in insert_columns)
        names = ", ".join(insert_columns)
        connection.execute(
            text(f"INSERT INTO learning_sessions ({names}) VALUES ({bind})"),
            {name: values[name] for name in insert_columns},
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT topic, target_question_count, status, pending_question_request_id, "
                "pending_question_request_hash FROM learning_sessions WHERE learning_session_id=:id"
            ),
            {"id": session_id},
        ).one()
        question_columns = {
            item[1]
            for item in connection.exec_driver_sql("PRAGMA table_info(learning_questions)")
        }
        indexes = {
            item[1]: item[2]
            for item in connection.exec_driver_sql("PRAGMA index_list(learning_questions)")
        }
    engine.dispose()
    assert row[0:3] == ("旧单题会话", 1, "IN_PROGRESS")
    assert row[3:] == (None, None)
    assert "generated_request_hash" in question_columns
    assert indexes["uq_learning_question_generated_request"] == 1
