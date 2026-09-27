from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.infrastructure.models import (
    Conversation,
    FileRecord,
    KnowledgeBase,
    LearningAttempt,
    LearningQuestion,
    LearningSession,
    Message,
)
from test_stage8_conversation_history import _client as _chat_client
from test_stage8_conversation_history import _message_count, _send
from test_stage8_learning_history import _client as _learning_client
from test_stage8_learning_history import _counts, _create, _submit_first_option


def _write(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def _ids(payload: dict[str, Any], key: str) -> list[str]:
    return [item[key] for item in payload["items"]]


def _walk(client: TestClient, path: str, params: dict[str, Any], key: str) -> list[str]:
    found: list[str] = []
    cursor = None
    for _ in range(10):
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        page = client.get(path, params=page_params)
        assert page.status_code == 200, page.text
        body = page.json()
        found.extend(_ids(body, key))
        cursor = body["next_cursor"]
        if not cursor:
            break
    return found


def test_conversation_filters_apply_before_pagination(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        first = _send(client, "filter-a", "甲筛选甲一的问题")
        second = _send(client, "filter-b", "甲筛选甲二的问题")
        third = _send(client, "filter-c", "甲筛选甲三的问题")
        other = _send(client, "filter-d", "乙其他对话问题")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            knowledge = session.get(Conversation, third)
            assert knowledge is not None
            knowledge.current_mode = "KNOWLEDGE_CHAT"
            outside = session.get(Conversation, first)
            assert outside is not None
            outside.last_active_at = datetime.now(UTC) - timedelta(days=40)
            interrupted = session.scalar(
                select(Message).where(
                    Message.conversation_id == second,
                    Message.role == "ASSISTANT",
                )
            )
            assert interrupted is not None
            interrupted.status = "INTERRUPTED"
            session.commit()
        today = datetime.now(UTC).date().isoformat()
        matched = _walk(
            client,
            "/api/v1/history/conversations",
            {
                "limit": 1,
                "q": "甲筛选",
                "mode": "GENERAL_CHAT",
                "date_from": today,
                "date_to": today,
            },
            "conversation_id",
        )
        assert matched == [second]
        assert other not in matched
        assert third not in matched
        assert first not in matched
        blank = client.get("/api/v1/history/conversations", params={"q": "   "})
        assert blank.status_code == 200
        assert set(_ids(blank.json(), "conversation_id")) == {first, second, third, other}
        wildcard = client.get("/api/v1/history/conversations", params={"q": "%"})
        assert wildcard.status_code == 200
        assert wildcard.json()["items"] == []
        too_long = client.get("/api/v1/history/conversations", params={"q": "甲" * 81})
        assert too_long.status_code == 400
        assert too_long.json()["code"] == "HISTORY_QUERY_INVALID"
        bad_status = client.get("/api/v1/history/conversations", params={"status": "TODAY_REVIEW"})
        assert bad_status.status_code == 400
        interrupted_page = client.get(
            "/api/v1/history/conversations", params={"status": "INTERRUPTED", "q": "甲筛选"}
        )
        assert _ids(interrupted_page.json(), "conversation_id") == [second]
        assert "resolved_model" not in interrupted_page.text
    finally:
        client.__exit__(None, None, None)


def test_conversation_trash_and_restore_keep_the_same_messages(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        kept = _send(client, "trash-keep", "保留的对话")
        target = _send(client, "trash-target", "准备移入回收站的对话")
        messages = client.get(f"/api/v1/conversations/{target}/messages").json()
        listed = client.get("/api/v1/history/conversations").json()
        version = next(item["row_version"] for item in listed["items"] if item["conversation_id"] == target)
        before_messages = _message_count(client)
        before_home = client.get("/api/v1/home/overview").json()
        stale = client.delete(
            f"/api/v1/conversations/{target}",
            params={"expected_version": version + 9},
            headers=_write("trash-stale"),
        )
        assert stale.status_code == 412
        assert stale.json()["code"] == "CONVERSATION_VERSION_CONFLICT"
        deleted = client.delete(
            f"/api/v1/conversations/{target}",
            params={"expected_version": version},
            headers=_write("trash-delete"),
        )
        assert deleted.status_code == 200, deleted.text
        deleted_at = deleted.json()["deleted_at"]
        assert deleted.json()["conversation_id"] == target
        again = client.delete(
            f"/api/v1/conversations/{target}",
            params={"expected_version": version},
            headers=_write("trash-delete-again"),
        )
        assert again.status_code == 200
        assert again.json()["deleted_at"] == deleted_at
        assert again.json()["row_version"] == deleted.json()["row_version"]
        hidden = client.get("/api/v1/history/conversations")
        assert target not in _ids(hidden.json(), "conversation_id")
        assert kept in _ids(hidden.json(), "conversation_id")
        missing = client.get(f"/api/v1/conversations/{target}")
        assert missing.status_code == 404
        trash = client.get("/api/v1/history/trash", params={"object_type": "conversation"})
        assert trash.status_code == 200
        assert _ids(trash.json(), "object_id") == [target]
        assert "准备移入回收站的对话" not in "".join(
            item["summary"] for item in hidden.json()["items"]
        )
        home = client.get("/api/v1/home/overview").json()
        assert home["conversations"] == before_home["conversations"] - 1
        assert _message_count(client) == before_messages
        restored = client.post(
            f"/api/v1/conversations/{target}/restore",
            params={"expected_version": deleted.json()["row_version"]},
            headers=_write("trash-restore"),
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["conversation_id"] == target
        assert restored.json()["deleted_at"] is None
        repeat = client.post(
            f"/api/v1/conversations/{target}/restore",
            params={"expected_version": restored.json()["row_version"]},
            headers=_write("trash-restore-again"),
        )
        assert repeat.status_code == 200
        assert repeat.json()["deleted_at"] is None
        assert repeat.json()["row_version"] == restored.json()["row_version"]
        after = client.get(f"/api/v1/conversations/{target}/messages").json()
        assert [item["message_id"] for item in after["items"]] == [
            item["message_id"] for item in messages["items"]
        ]
        visible = client.get("/api/v1/history/conversations").json()
        assert target in _ids(visible, "conversation_id")
        assert client.get("/api/v1/home/overview").json()["conversations"] == before_home["conversations"]
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            assert session.get(Conversation, kept) is not None
            assert session.scalar(select(func.count()).select_from(FileRecord)) == 0
            assert session.scalar(select(func.count()).select_from(KnowledgeBase)) == 0
    finally:
        client.__exit__(None, None, None)


def test_learning_query_trash_restore_and_source_block(tmp_path: Path) -> None:
    client, data = _learning_client(tmp_path)
    try:
        pending = _create(client, data.knowledge_base_id, "query-pending")
        answered = _create(client, data.knowledge_base_id, "query-answered")
        feedback = _submit_first_option(client, answered, "query-answered-submit")
        other = _create(client, data.knowledge_base_id, "query-other")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            target = session.get(LearningSession, other["learning_session_id"])
            assert target is not None
            target.topic = "乙学习主题"
            target.goal_text = "乙学习目标"
            session.commit()
        matched = _walk(
            client,
            "/api/v1/history/learning-sessions",
            {"limit": 1, "q": "超时", "goal_type": "CUSTOM", "status": "IN_PROGRESS"},
            "learning_session_id",
        )
        assert pending["learning_session_id"] in matched
        assert answered["learning_session_id"] in matched
        assert other["learning_session_id"] not in matched
        hidden_answer = client.get("/api/v1/history/learning-sessions", params={"q": "30"})
        assert hidden_answer.status_code == 200
        assert hidden_answer.json()["items"] == []
        assert "answer_key" not in hidden_answer.text
        assert feedback["explanation"] not in hidden_answer.text
        bad_goal = client.get("/api/v1/history/learning-sessions", params={"goal_type": "今日需复习"})
        assert bad_goal.status_code == 400
        listed = client.get("/api/v1/history/learning-sessions").json()
        version = next(
            item["row_version"]
            for item in listed["items"]
            if item["learning_session_id"] == pending["learning_session_id"]
        )
        before_counts = _counts(client)
        before_home = client.get("/api/v1/home/overview").json()
        question_id = pending["question"]["question_id"]
        deleted = client.delete(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}",
            params={"expected_version": version},
            headers=_write("learn-trash"),
        )
        assert deleted.status_code == 200, deleted.text
        duplicate = client.delete(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}",
            params={"expected_version": deleted.json()["row_version"]},
            headers=_write("learn-trash-again"),
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["row_version"] == deleted.json()["row_version"]
        assert client.get(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}"
        ).status_code == 404
        assert pending["learning_session_id"] not in _ids(
            client.get("/api/v1/history/learning-sessions").json(), "learning_session_id"
        )
        assert client.get("/api/v1/home/overview").json()["learning_sessions"] == (
            before_home["learning_sessions"] - 1
        )
        restored = client.post(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}/restore",
            params={"expected_version": deleted.json()["row_version"]},
            headers=_write("learn-restore"),
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["learning_session_id"] == pending["learning_session_id"]
        repeat = client.post(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}/restore",
            params={"expected_version": restored.json()["row_version"]},
            headers=_write("learn-restore-again"),
        )
        assert repeat.status_code == 200
        assert repeat.json()["deleted_at"] is None
        opened = client.get(f"/api/v1/learning-sessions/{pending['learning_session_id']}")
        assert opened.status_code == 200
        assert opened.json()["question"]["question_id"] == question_id
        assert _counts(client) == before_counts
        file_deleted = client.delete(
            f"/api/v1/files/{data.file_id}", headers=_write("learn-file-trash")
        )
        assert file_deleted.status_code == 200, file_deleted.text
        blocked = client.get(f"/api/v1/learning-sessions/{pending['learning_session_id']}")
        assert blocked.status_code == 200
        assert blocked.json()["status"] == "SOURCE_INVALID"
        attempt = client.post(
            f"/api/v1/learning-questions/{question_id}/attempts",
            headers={"Origin": "http://127.0.0.1:5173", "Idempotency-Key": "blocked-answer"},
            json={
                "selected_option": pending["question"]["options"][0]["option_id"],
                "client_request_id": "blocked-answer",
                "expected_question_version": pending["question"]["row_version"],
            },
        )
        assert attempt.status_code == 409
        assert attempt.json()["code"] == "SOURCE_INVALID"
        history = client.get("/api/v1/history/learning-sessions", params={"status": "SOURCE_INVALID"})
        assert pending["learning_session_id"] in _ids(history.json(), "learning_session_id")
        assert "answer_key" not in history.text
        still_answered = client.get(
            f"/api/v1/learning-sessions/{answered['learning_session_id']}"
        ).json()
        assert still_answered["question"]["feedback"]["explanation"] == feedback["explanation"]
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            assert session.get(KnowledgeBase, data.knowledge_base_id) is not None
            assert session.get(FileRecord, data.file_id) is not None
            assert session.scalar(select(func.count()).select_from(LearningQuestion)) == before_counts[1]
            assert session.scalar(select(func.count()).select_from(LearningAttempt)) == before_counts[0]
    finally:
        client.__exit__(None, None, None)
