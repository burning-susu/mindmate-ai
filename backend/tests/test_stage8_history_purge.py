"""Stage 8: expired history trash permanent purge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from mindmate.application.history_purge import purge_expired_history
from mindmate.application.history_search_index import collect_hits
from mindmate.infrastructure.db import quick_check
from mindmate.infrastructure.models import (
    AiOperation,
    Conversation,
    FileRecord,
    KnowledgeBase,
    KnowledgePoint,
    LearningAttempt,
    LearningFeedback,
    LearningQuestion,
    LearningSession,
    Message,
    SourceSnapshot,
)
from test_stage8_conversation_history import _client as _chat_client
from test_stage8_conversation_history import _message_count, _send
from test_stage8_learning_history import _client as _learning_client
from test_stage8_learning_history import _counts, _create, _submit_first_option


def _origin(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def _trash_conversation(client: TestClient, conversation_id: str, key: str) -> int:
    listed = client.get("/api/v1/history/conversations").json()
    version = next(
        item["row_version"]
        for item in listed["items"]
        if item["conversation_id"] == conversation_id
    )
    deleted = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        params={"expected_version": version},
        headers=_origin(key),
    )
    assert deleted.status_code == 200, deleted.text
    return int(deleted.json()["row_version"])


def _trash_learning(client: TestClient, learning_session_id: str, key: str) -> int:
    detail = client.get(f"/api/v1/learning-sessions/{learning_session_id}")
    assert detail.status_code == 200, detail.text
    deleted = client.delete(
        f"/api/v1/learning-sessions/{learning_session_id}",
        params={"expected_version": detail.json()["row_version"]},
        headers=_origin(key),
    )
    assert deleted.status_code == 200, deleted.text
    return int(deleted.json()["row_version"])


def _mark_due(factory: Any, model: type[Any], object_id: str, *, days_ago: int = 31) -> int:
    now = datetime.now(UTC)
    with factory() as session:
        record = session.get(model, object_id)
        assert record is not None
        assert record.deleted_at is not None
        record.deleted_at = now - timedelta(days=days_ago)
        # Soft-delete retention is 30 days from deleted_at.
        record.purge_after = record.deleted_at + timedelta(days=30)
        session.commit()
        return int(record.row_version)


def test_expired_conversation_purge_keeps_shared_sources_and_other_chat(
    tmp_path: Path,
) -> None:
    client = _chat_client(tmp_path)
    try:
        keep = _send(client, "purge-keep", "保留对话中的公开词甲乙丙")
        gone = _send(client, "purge-gone", "待清理对话中的公开词甲乙丙")
        _trash_conversation(client, gone, "purge-gone-trash")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            before_messages = int(session.scalar(select(func.count()).select_from(Message)) or 0)
            before_ops = int(
                session.scalar(select(func.count()).select_from(AiOperation)) or 0
            )
            before_snapshots = int(
                session.scalar(select(func.count()).select_from(SourceSnapshot)) or 0
            )
            before_files = int(session.scalar(select(func.count()).select_from(FileRecord)) or 0)
            before_kb = int(
                session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
            )
        _mark_due(factory, Conversation, gone, days_ago=31)

        preview = client.get("/api/v1/history/trash/purge-preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["eligible_conversations"] >= 1

        clock = datetime.now(UTC)
        with factory() as session:
            stats = purge_expired_history(session, now=clock, limit=10)
        assert stats["purged_conversations"] >= 1
        assert stats["errors"] == 0

        assert client.get(f"/api/v1/conversations/{gone}").status_code == 404
        trash = client.get(
            "/api/v1/history/trash", params={"object_type": "conversation"}
        )
        assert trash.status_code == 200
        assert gone not in {item["object_id"] for item in trash.json()["items"]}
        live = client.get("/api/v1/history/conversations", params={"q": "甲乙丙"})
        assert live.status_code == 200
        ids = {item["conversation_id"] for item in live.json()["items"]}
        assert keep in ids
        assert gone not in ids

        with factory() as session:
            assert session.get(Conversation, gone) is None
            assert session.get(Conversation, keep) is not None
            after_messages = int(
                session.scalar(select(func.count()).select_from(Message)) or 0
            )
            after_ops = int(
                session.scalar(select(func.count()).select_from(AiOperation)) or 0
            )
            assert after_messages < before_messages
            assert after_ops < before_ops
            assert int(session.scalar(select(func.count()).select_from(SourceSnapshot)) or 0) == before_snapshots
            assert int(session.scalar(select(func.count()).select_from(FileRecord)) or 0) == before_files
            assert int(session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0) == before_kb
            assert session.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == keep))
            hits, _ = collect_hits(session, "conversation", "甲乙丙")
            assert gone not in hits
            assert keep in hits
            assert quick_check(cast(Any, client.app).state.engine) == "ok"
    finally:
        client.__exit__(None, None, None)


def test_purge_boundaries_restore_race_and_idempotency(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        early = _send(client, "bound-early", "边界未到期对话")
        exact = _send(client, "bound-exact", "边界刚好到期对话")
        missing = _send(client, "bound-missing", "缺少到期时间对话")
        raced = _send(client, "bound-race", "恢复竞态对话")
        factory = cast(Any, client.app).state.session_factory
        early_ver = _trash_conversation(client, early, "bound-early-trash")
        exact_ver = _trash_conversation(client, exact, "bound-exact-trash")
        missing_ver = _trash_conversation(client, missing, "bound-missing-trash")
        raced_ver = _trash_conversation(client, raced, "bound-race-trash")
        assert early_ver and exact_ver and missing_ver and raced_ver
        now = datetime.now(UTC)
        with factory() as session:
            early_row = session.get(Conversation, early)
            exact_row = session.get(Conversation, exact)
            missing_row = session.get(Conversation, missing)
            raced_row = session.get(Conversation, raced)
            assert early_row and exact_row and missing_row and raced_row
            early_row.purge_after = now + timedelta(seconds=30)
            exact_row.purge_after = now
            missing_row.purge_after = None
            raced_row.purge_after = now - timedelta(days=1)
            session.commit()
            _raced_version = raced_row.row_version

        with factory() as session:
            first = purge_expired_history(session, now=now, limit=20)
        assert first["purged_conversations"] == 2
        with factory() as session:
            assert session.get(Conversation, exact) is None
            assert session.get(Conversation, raced) is None
            assert session.get(Conversation, early) is not None
            assert session.get(Conversation, missing) is not None

        # Restore is only valid for still-trashed rows; re-trash a fresh due row for race.
        live = _send(client, "bound-race-2", "第二次恢复竞态对话")
        raced2_ver = _trash_conversation(client, live, "bound-race-2-trash")
        with factory() as session:
            row = session.get(Conversation, live)
            assert row is not None
            row.purge_after = now - timedelta(days=1)
            session.commit()
            raced2_ver = row.row_version
        restored = client.post(
            f"/api/v1/conversations/{live}/restore",
            params={"expected_version": raced2_ver},
            headers=_origin("bound-race-2-restore"),
        )
        assert restored.status_code == 200, restored.text
        with factory() as session:
            second = purge_expired_history(session, now=now, limit=20)
            assert second["purged_conversations"] == 0
            assert session.get(Conversation, live) is not None
            third = purge_expired_history(session, now=now, limit=20)
            assert third["purged_conversations"] == 0
            assert third["errors"] == 0
    finally:
        client.__exit__(None, None, None)


def test_learning_purge_removes_owned_rows_keeps_shared_point(
    tmp_path: Path,
) -> None:
    client, data = _learning_client(tmp_path)
    try:
        kb_id = data.knowledge_base_id
        first_payload = _create(client, kb_id, "learn-purge-a")
        second_payload = _create(client, kb_id, "learn-purge-b")
        first = first_payload["learning_session_id"]
        second = second_payload["learning_session_id"]
        _submit_first_option(client, first_payload, "learn-purge-a-ans")
        _submit_first_option(client, second_payload, "learn-purge-b-ans")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            point_a = session.scalar(
                select(LearningQuestion.knowledge_point_id).where(
                    LearningQuestion.learning_session_id == first
                )
            )
            point_b = session.scalar(
                select(LearningQuestion.knowledge_point_id).where(
                    LearningQuestion.learning_session_id == second
                )
            )
            assert point_a and point_b and point_a != point_b
            # Point A becomes shared: second session also references it.
            session.execute(
                text(
                    "UPDATE learning_questions SET knowledge_point_id = :shared "
                    "WHERE learning_session_id = :sid"
                ),
                {"shared": point_a, "sid": second},
            )
            session.execute(
                text(
                    "UPDATE learning_plan_items SET knowledge_point_id = :shared "
                    "WHERE learning_plan_id IN ("
                    "SELECT learning_plan_id FROM learning_plans "
                    "WHERE learning_session_id = :sid)"
                ),
                {"shared": point_a, "sid": second},
            )
            session.commit()
            before_attempts = int(
                session.scalar(select(func.count()).select_from(LearningAttempt)) or 0
            )
            before_feedback = int(
                session.scalar(select(func.count()).select_from(LearningFeedback)) or 0
            )
            before_files = int(session.scalar(select(func.count()).select_from(FileRecord)) or 0)
            before_kb = int(
                session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
            )
            before_snapshots = int(
                session.scalar(select(func.count()).select_from(SourceSnapshot)) or 0
            )

        _trash_learning(client, first, "learn-purge-a-trash")
        _mark_due(factory, LearningSession, first, days_ago=40)

        run = client.post(
            "/api/v1/history/trash/purge-expired",
            params={"limit": 10},
            headers=_origin("learn-purge-run"),
        )
        assert run.status_code == 200, run.text
        body = run.json()
        assert body["purged_learning_sessions"] >= 1
        assert body["errors"] == 0

        assert client.get(f"/api/v1/learning-sessions/{first}").status_code == 404
        assert client.get(f"/api/v1/learning-sessions/{second}").status_code == 200
        with factory() as session:
            assert session.get(LearningSession, first) is None
            # Shared point stays; exclusive former point of second is already unreferenced.
            assert session.get(KnowledgePoint, point_a) is not None
            assert int(session.scalar(select(func.count()).select_from(LearningAttempt)) or 0) < before_attempts
            assert int(session.scalar(select(func.count()).select_from(LearningFeedback)) or 0) < before_feedback
            assert int(session.scalar(select(func.count()).select_from(FileRecord)) or 0) == before_files
            assert int(session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0) == before_kb
            assert int(session.scalar(select(func.count()).select_from(SourceSnapshot)) or 0) == before_snapshots
            topic = first_payload["topic"]
            hits, _ = collect_hits(session, "learning", topic[:8] or topic)
            assert first not in hits
            assert second in hits
            _attempts, questions = _counts(client)
            assert questions >= 1
            assert quick_check(cast(Any, client.app).state.engine) == "ok"
    finally:
        client.__exit__(None, None, None)


def test_manual_permanent_delete_requires_confirmation(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        conversation_id = _send(client, "manual-purge", "手动永久删除对话")
        version = _trash_conversation(client, conversation_id, "manual-purge-trash")
        denied = client.delete(
            f"/api/v1/conversations/{conversation_id}/permanent",
            params={"expected_version": version, "confirmed": False},
            headers=_origin("manual-purge-denied"),
        )
        assert denied.status_code == 400
        assert denied.json()["code"] == "PURGE_CONFIRMATION_REQUIRED"
        before = _message_count(client)
        ok = client.delete(
            f"/api/v1/conversations/{conversation_id}/permanent",
            params={"expected_version": version, "confirmed": True},
            headers=_origin("manual-purge-ok"),
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["status"] == "PURGED"
        assert _message_count(client) < before
        assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_manual_learning_permanent_delete_requires_confirmation_and_keeps_sources(
    tmp_path: Path,
) -> None:
    client, data = _learning_client(tmp_path)
    try:
        created = _create(client, data.knowledge_base_id, "manual-learning-purge")
        _submit_first_option(client, created, "manual-learning-purge-answer")
        learning_session_id = created["learning_session_id"]
        question_id = created["question"]["question_id"]
        version = _trash_learning(client, learning_session_id, "manual-learning-purge-trash")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            before_files = int(session.scalar(select(func.count()).select_from(FileRecord)) or 0)
            before_knowledge_bases = int(
                session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
            )
            before_points = int(session.scalar(select(func.count()).select_from(KnowledgePoint)) or 0)
        denied = client.delete(
            f"/api/v1/learning-sessions/{learning_session_id}/permanent",
            params={"expected_version": version, "confirmed": False},
            headers=_origin("manual-learning-purge-denied"),
        )
        assert denied.status_code == 400
        assert denied.json()["code"] == "PURGE_CONFIRMATION_REQUIRED"
        ok = client.delete(
            f"/api/v1/learning-sessions/{learning_session_id}/permanent",
            params={"expected_version": version, "confirmed": True},
            headers=_origin("manual-learning-purge-ok"),
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["status"] == "PURGED"
        assert client.get(f"/api/v1/learning-sessions/{learning_session_id}").status_code == 404
        assert client.get(
            "/api/v1/history/learning-sessions", params={"q": "超时时间"}
        ).json()["items"] == []
        with factory() as session:
            assert session.get(LearningSession, learning_session_id) is None
            assert session.get(LearningQuestion, question_id) is None
            assert int(session.scalar(select(func.count()).select_from(FileRecord)) or 0) == before_files
            assert int(session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0) == before_knowledge_bases
            assert int(session.scalar(select(func.count()).select_from(KnowledgePoint)) or 0) == before_points
    finally:
        client.__exit__(None, None, None)


def test_history_list_does_not_trigger_purge(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        conversation_id = _send(client, "list-no-purge", "列表不触发清理")
        _trash_conversation(client, conversation_id, "list-no-purge-trash")
        factory = cast(Any, client.app).state.session_factory
        _mark_due(factory, Conversation, conversation_id, days_ago=40)
        listed = client.get("/api/v1/history/conversations")
        trash = client.get(
            "/api/v1/history/trash", params={"object_type": "conversation"}
        )
        assert listed.status_code == 200
        assert trash.status_code == 200
        with factory() as session:
            assert session.get(Conversation, conversation_id) is not None
    finally:
        client.__exit__(None, None, None)
