"""History body search stays inside the local projection."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from mindmate.application.history_search_index import (
    backfill_history_search,
    verify_history_search_projection,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    AiOperation,
    AnswerVersion,
    Conversation,
    HistorySearchDocument,
    HistorySearchState,
    LearningAttempt,
    LearningQuestion,
    Message,
)
from mindmate.main import create_app
from test_stage5_source_snapshots import _seed_active_index
from test_stage8_conversation_history import _client as _chat_client
from test_stage8_conversation_history import _headers, _message_count, _send, _wait
from test_stage8_learning_history import _client as _learning_client
from test_stage8_learning_history import _counts, _create
from test_stage57_learning_multistep import (
    FACTS as MULTI_FACTS,
)
from test_stage57_learning_multistep import (
    _add_fact_chunks,
    _answer_question,
    _create_session,
    _install_query,
    _next_question,
    _SequenceQuery,
)
from test_stage57_learning_multistep import (
    _settings as _multi_settings,
)


def _search(client: TestClient, path: str, query: str) -> dict[str, Any]:
    response = client.get(path, params={"q": query, "limit": 20})
    assert response.status_code == 200, response.text
    return response.json()


def test_conversation_body_hits_are_bounded_and_secrets_stay_out(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        first = _send(client, "body-alpha", "早期用户问题里有木星环")
        second = _send(client, "body-beta", "另一段完全不同的正文")
        created = client.post(
            f"/api/v1/conversations/{first}/messages",
            headers=_headers("body-alpha-2"),
            json={"content": "同一会话再次提到木星环", "client_request_id": "body-alpha-2"},
        )
        assert created.status_code == 202, created.text
        assert _wait(client, created.json()["operation_id"])["status"] == "COMPLETED"
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            stopped = session.scalar(
                select(Message).where(Message.conversation_id == second, Message.role == "ASSISTANT")
            )
            assert stopped is not None
            stopped.status = "STOPPED"
            stopped.content = "停止中的分片不应被检索 STOPPED-FRAGMENT"
            draft = session.scalar(
                select(AnswerVersion).where(
                    AnswerVersion.assistant_message_id == stopped.message_id
                )
            )
            assert draft is not None
            draft.content = "旧分支隐藏正文 HIDDEN-BRANCH"
            draft.status = "STOPPED"
            operation = session.scalar(
                select(AiOperation).where(AiOperation.conversation_id == second)
            )
            assert operation is not None
            operation.error_detail = r"C:\secret\stack.txt sk-live-key"
            user = session.scalar(
                select(Message).where(
                    Message.conversation_id == first,
                    Message.role == "USER",
                    Message.content.contains("早期用户问题"),
                )
            )
            assert user is not None
            user_id = user.message_id
            archived = Message(
                conversation_id=first,
                role="USER",
                content="归档旧问题 ARCHIVED-BRANCH",
                status="SENT",
                sequence_number=99,
                mode_snapshot="GENERAL_CHAT",
                revision_number=1,
                archived_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(archived)
            same_time = datetime(2026, 9, 27, tzinfo=UTC)
            for conversation_id in (first, second):
                record = session.get(Conversation, conversation_id)
                assert record is not None
                record.last_active_at = same_time
            session.commit()
        page = _search(client, "/api/v1/history/conversations", "木星环")
        assert [item["conversation_id"] for item in page["items"]] == [first]
        sections = {item["section"] for item in page["items"][0]["locations"]}
        assert "user_message" in sections
        assert len(page["items"][0]["locations"]) <= 3
        assert any(item["record_id"] == user_id for item in page["items"][0]["locations"])
        assert "STOPPED-FRAGMENT" not in str(page)
        hidden = _search(client, "/api/v1/history/conversations", "STOPPED-FRAGMENT")
        assert hidden["items"] == []
        assert _search(client, "/api/v1/history/conversations", "HIDDEN-BRANCH")["items"] == []
        assert _search(client, "/api/v1/history/conversations", "ARCHIVED-BRANCH")["items"] == []
        secret = _search(client, "/api/v1/history/conversations", "sk-live-key")
        assert secret["items"] == []
        assert "sk-live-key" not in client.get(
            "/api/v1/history/conversations", params={"q": "sk-live-key"}
        ).text
        special = _search(client, "/api/v1/history/conversations", "木星环??")
        assert special["items"] == []
        english = _send(client, "body-english", "alpha-orbit token")
        assert _search(client, "/api/v1/history/conversations", "alpha-orbit")["items"][0][
            "conversation_id"
        ] == english
        _send(client, "body-page-a", "共同分页词甲")
        _send(client, "body-page-b", "共同分页词乙")
        paged = client.get(
            "/api/v1/history/conversations",
            params={"q": "共同分页词", "limit": 1},
        )
        assert paged.status_code == 200
        cursor = paged.json()["next_cursor"]
        assert cursor
        reused = client.get(
            "/api/v1/history/conversations",
            params={"q": "木星环", "limit": 1, "cursor": cursor},
        )
        assert reused.status_code == 400
        assert reused.json()["code"] == "HISTORY_CURSOR_INVALID"
        blank = client.get("/api/v1/history/conversations", params={"q": "   "})
        assert blank.status_code == 200
        assert first in {item["conversation_id"] for item in blank.json()["items"]}
        with factory() as session:
            expected_messages = session.scalar(select(func.count()).select_from(Message))
            session.execute(text("DELETE FROM history_search_fts"))
            session.execute(text("DELETE FROM history_search_documents"))
            session.execute(text("DELETE FROM history_search_owners"))
            state = session.get(HistorySearchState, "projection")
            assert state is not None
            state.status = "PENDING"
            session.commit()
            status = backfill_history_search(session, limit=2)
            session.commit()
            while status != "READY":
                status = backfill_history_search(session, limit=2)
                session.commit()
            verify_history_search_projection(session)
            indexed = session.scalar(select(func.count()).select_from(HistorySearchDocument))
            again = backfill_history_search(session, limit=2)
            session.commit()
            assert again == "READY"
            assert session.scalar(select(func.count()).select_from(HistorySearchDocument)) == indexed
        restored = _search(client, "/api/v1/history/conversations", "木星环")
        assert restored["items"][0]["conversation_id"] == first
        assert restored["search_index_status"] == "READY"
        assert _message_count(client) == expected_messages
    finally:
        client.__exit__(None, None, None)


def test_learning_answer_key_is_hidden_until_feedback_is_published(tmp_path: Path) -> None:
    client, data = _learning_client(tmp_path)
    try:
        pending = _create(client, data.knowledge_base_id, "body-pending")
        question = pending["question"]
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            row = session.get(LearningQuestion, question["question_id"])
            assert row is not None
            secret = f"HIDDEN-KEY-{row.answer_key_json['option_id']}"
            row.grading_rule_json = {**row.grading_rule_json, "marker": secret}
            row.prompt_template_version = "prompt-secret-template"
            correct = next(
                option["label"]
                for option in row.options_json
                if option["option_id"] == row.answer_key_json["option_id"]
            )
            session.commit()
            attempts_before = session.scalar(select(func.count()).select_from(LearningAttempt))
        assert _search(client, "/api/v1/history/learning-sessions", secret)["items"] == []
        assert _search(client, "/api/v1/history/learning-sessions", "prompt-secret-template")[
            "items"
        ] == []
        assert _search(client, "/api/v1/history/learning-sessions", correct)["items"] == []
        assert _search(
            client, "/api/v1/history/learning-sessions", "不得跳过校验或降低证据门槛"
        )["items"] == []
        prompt_hit = _search(client, "/api/v1/history/learning-sessions", "根据当前资料")
        assert prompt_hit["items"][0]["learning_session_id"] == pending["learning_session_id"]
        assert prompt_hit["items"][0]["locations"][0]["section"] == "question"
        assert prompt_hit["items"][0]["locations"][0]["record_id"] == question["question_id"]
        submitted = client.post(
            f"/api/v1/learning-questions/{question['question_id']}/attempts",
            headers=_headers("body-submit"),
            json={
                "selected_option": question["options"][0]["option_id"],
                "client_request_id": "body-submit",
                "expected_question_version": question["row_version"],
            },
        )
        assert submitted.status_code == 200, submitted.text
        selected = question["options"][0]["label"]
        after = _search(client, "/api/v1/history/learning-sessions", selected)
        assert after["items"][0]["learning_session_id"] == pending["learning_session_id"]
        assert {item["section"] for item in after["items"][0]["locations"]} & {
            "submitted_answer",
            "feedback",
        }
        assert secret not in client.get(
            "/api/v1/history/learning-sessions", params={"q": selected}
        ).text
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(LearningAttempt)) == (
                attempts_before or 0
            ) + 1
        assert _counts(client)[0] >= 1
    finally:
        client.__exit__(None, None, None)


def test_multistep_learning_search_keeps_each_question_location(tmp_path: Path) -> None:
    settings = _multi_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1"})
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(
            factory, settings, content=MULTI_FACTS[0], display_name="多题定位资料.txt"
        )
        rows = _add_fact_chunks(factory, data, MULTI_FACTS)
        _install_query(client, _SequenceQuery(rows))
        created = _create_session(client, data, key="stage59-history-multi-create", target_count=3)
        current = created
        locations: list[tuple[str, str]] = []
        for index in range(3):
            question = current["question"]
            with factory() as session:
                stored = session.get(LearningQuestion, question["question_id"])
                assert stored is not None
                correct_id = str(stored.answer_key_json["option_id"])
                selected_label = next(
                    option["label"]
                    for option in stored.options_json
                    if option["option_id"] == correct_id
                )
            _answer_question(
                client,
                factory,
                question,
                key=f"stage59-history-multi-answer-{index + 1}",
            )
            locations.append((question["question_id"], selected_label))
            if index < 2:
                next_response = _next_question(
                    client,
                    client.get(
                        f"/api/v1/learning-sessions/{created['learning_session_id']}"
                    ).json(),
                    key=f"stage59-history-multi-next-{index + 2}",
                )
                assert next_response.status_code == 200, next_response.text
                current = next_response.json()

        for question_id, selected_label in locations:
            page = _search(client, "/api/v1/history/learning-sessions", selected_label)
            assert page["items"][0]["learning_session_id"] == created["learning_session_id"]
            assert any(
                location["record_id"] == question_id
                and location["section"] in {"submitted_answer", "feedback"}
                for location in page["items"][0]["locations"]
            )


def test_history_projection_migration_is_reversible(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "migrate", env="test")
    config = Config(str(settings.alembic_ini))
    config.attributes["settings"] = settings
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{settings.database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "b55c0e1a8d27"
        assert connection.scalar(
            text("SELECT status FROM history_search_state WHERE state_key = 'projection'")
        ) == "PENDING"
        assert connection.scalar(text("SELECT COUNT(*) FROM history_search_documents")) == 0
    command.downgrade(config, "c8d4f1a27b63")
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        }
    assert "history_search_documents" not in tables
    assert "history_search_fts" not in tables
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT status FROM history_search_state WHERE state_key = 'projection'")
        ) == "PENDING"
    engine.dispose()
