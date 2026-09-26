from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.infrastructure.models import (
    FileRecord,
    LearningAttempt,
    LearningQuestion,
    LearningSession,
)
from mindmate.main import create_app
from test_stage5_source_snapshots import _seed_active_index
from test_stage7_learning_session import (
    ORIGIN,
    PUBLIC_FILE,
    _body,
    _Encoder,
    _headers,
    _Query,
    _settings,
    _supported_public,
)


def _open(tmp_path: Path) -> TestClient:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")
    client.__enter__()
    client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    return client


def _client(tmp_path: Path) -> tuple[TestClient, Any]:
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")
    client.__enter__()
    client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    factory = cast(Any, client.app).state.session_factory
    content = PUBLIC_FILE.read_text(encoding="utf-8")
    data = _seed_active_index(factory, settings, content=content, display_name="服务超时策略.txt")
    result = _supported_public(data, content)
    encoder = _Encoder()
    cast(Any, client.app).state.learning_encoder_getter = lambda: encoder
    cast(Any, client.app).state.learning_query_getter = lambda _settings: _Query(result)
    return client, data


def _create(client: TestClient, knowledge_base_id: str, key: str) -> dict[str, Any]:
    created = client.post(
        "/api/v1/learning-sessions",
        headers=_headers(key),
        json=_body(knowledge_base_id, key),
    )
    assert created.status_code == 200, created.text
    return created.json()


def _submit_first_option(client: TestClient, payload: dict[str, Any], key: str) -> dict[str, Any]:
    question = payload["question"]
    answered = client.post(
        f"/api/v1/learning-questions/{question['question_id']}/attempts",
        headers=_headers(key),
        json={
            "selected_option": question["options"][0]["option_id"],
            "client_request_id": key,
            "expected_question_version": question["row_version"],
        },
    )
    assert answered.status_code == 200, answered.text
    return answered.json()


def _counts(client: TestClient) -> tuple[int, int]:
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        attempts = int(session.scalar(select(func.count()).select_from(LearningAttempt)) or 0)
        questions = int(session.scalar(select(func.count()).select_from(LearningQuestion)) or 0)
    return attempts, questions


def test_learning_history_sorts_pages_and_hides_answers(tmp_path: Path) -> None:
    client, data = _client(tmp_path)
    try:
        first = _create(client, data.knowledge_base_id, "history-learn-a")
        second = _create(client, data.knowledge_base_id, "history-learn-b")
        third = _create(client, data.knowledge_base_id, "history-learn-c")
        submitted = _submit_first_option(client, third, "history-learn-c-answer")
        recycled = _create(client, data.knowledge_base_id, "history-learn-d")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            record = session.get(LearningSession, recycled["learning_session_id"])
            assert record is not None
            record.deleted_at = datetime.now(UTC)
            session.commit()
        before = _counts(client)
        page = client.get("/api/v1/history/learning-sessions", params={"limit": 1})
        assert page.status_code == 200, page.text
        body = page.json()
        assert [item["learning_session_id"] for item in body["items"]] == [
            third["learning_session_id"]
        ]
        item = body["items"][0]
        assert item["answered_count"] == 1
        assert item["target_question_count"] == 1
        assert item["status"] == "IN_PROGRESS"
        assert item["source_status"] == "AVAILABLE"
        assert item["scope_name"]
        assert item["scope_file_count"] == 1
        assert item["topic"] == third["topic"]
        for forbidden in (
            "answer_key",
            "prompt_text",
            "explanation",
            "selected_option",
            "excerpt",
            submitted["explanation"],
        ):
            assert forbidden not in page.text
        assert body["next_cursor"]
        second_page = client.get(
            "/api/v1/history/learning-sessions",
            params={"limit": 2, "cursor": body["next_cursor"]},
        )
        assert second_page.status_code == 200
        ids = [item["learning_session_id"] for item in second_page.json()["items"]]
        assert ids == [second["learning_session_id"], first["learning_session_id"]]
        assert second_page.json()["next_cursor"] is None
        assert all(item["answered_count"] == 0 for item in second_page.json()["items"])
        assert recycled["learning_session_id"] not in ids
        assert _counts(client) == before
        invalid = client.get(
            "/api/v1/history/learning-sessions", params={"cursor": "not-a-cursor"}
        )
        assert invalid.status_code == 400
        assert invalid.json()["code"] == "HISTORY_CURSOR_INVALID"
    finally:
        client.__exit__(None, None, None)


def test_learning_history_reopens_same_session_after_restart(tmp_path: Path) -> None:
    client, data = _client(tmp_path)
    try:
        pending = _create(client, data.knowledge_base_id, "history-learn-open")
        answered_session = _create(client, data.knowledge_base_id, "history-learn-done")
        feedback = _submit_first_option(client, answered_session, "history-learn-done-answer")
        before = client.get(
            f"/api/v1/learning-sessions/{answered_session['learning_session_id']}"
        ).json()
        pending_before = client.get(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}"
        ).json()
        counts = _counts(client)
    finally:
        client.__exit__(None, None, None)

    restarted = _open(tmp_path)
    try:
        listed = restarted.get("/api/v1/history/learning-sessions")
        assert listed.status_code == 200
        ids = [item["learning_session_id"] for item in listed.json()["items"]]
        assert answered_session["learning_session_id"] in ids
        assert pending["learning_session_id"] in ids
        after = restarted.get(
            f"/api/v1/learning-sessions/{answered_session['learning_session_id']}"
        ).json()
        pending_after = restarted.get(
            f"/api/v1/learning-sessions/{pending['learning_session_id']}"
        ).json()
        assert after["current_question_id"] == before["current_question_id"]
        assert after["question"]["question_id"] == before["question"]["question_id"]
        assert after["question"]["options"] == before["question"]["options"]
        assert after["question"]["feedback"]["explanation"] == feedback["explanation"]
        assert after["question"]["feedback"]["selected_option"] == feedback["selected_option"]
        assert after["question"]["feedback"]["attempt_id"] == feedback["attempt_id"]
        assert pending_after["question"]["question_id"] == pending_before["question"]["question_id"]
        assert pending_after["question"]["feedback"] is None
        assert pending_after["question"]["options"] == pending_before["question"]["options"]
        assert _counts(restarted) == counts
    finally:
        restarted.__exit__(None, None, None)


def test_learning_history_blocks_invalid_source_without_new_attempt(tmp_path: Path) -> None:
    client, data = _client(tmp_path)
    try:
        pending = _create(client, data.knowledge_base_id, "history-learn-invalid-open")
        answered_session = _create(client, data.knowledge_base_id, "history-learn-invalid-done")
        feedback = _submit_first_option(client, answered_session, "history-learn-invalid-answer")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            stored = session.get(LearningSession, pending["learning_session_id"])
            assert stored is not None
            stored_status = stored.status
            stored_version = stored.row_version
        with factory() as session:
            file_record = session.get(FileRecord, data.file_id)
            assert file_record is not None
            file_record.deleted_at = datetime.now(UTC)
            session.commit()
        listed = client.get("/api/v1/history/learning-sessions").json()["items"]
        by_id = {item["learning_session_id"]: item for item in listed}
        assert by_id[pending["learning_session_id"]]["status"] == "SOURCE_INVALID"
        assert by_id[pending["learning_session_id"]]["source_status"] == "SOURCE_IN_TRASH"
        assert by_id[pending["learning_session_id"]]["answered_count"] == 0
        assert by_id[answered_session["learning_session_id"]]["answered_count"] == 1
        assert by_id[answered_session["learning_session_id"]]["source_status"] == "SOURCE_IN_TRASH"
        with factory() as session:
            stored = session.get(LearningSession, pending["learning_session_id"])
            assert stored is not None
            assert stored.status == stored_status
            assert stored.row_version == stored_version
        opened = client.get(f"/api/v1/learning-sessions/{pending['learning_session_id']}")
        assert opened.status_code == 200
        assert opened.json()["status"] == "SOURCE_INVALID"
        blocked = client.post(
            f"/api/v1/learning-questions/{pending['question']['question_id']}/attempts",
            headers=_headers("history-learn-invalid-submit"),
            json={
                "selected_option": pending["question"]["options"][0]["option_id"],
                "client_request_id": "history-learn-invalid-submit",
                "expected_question_version": pending["question"]["row_version"],
            },
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "SOURCE_INVALID"
        kept = client.get(
            f"/api/v1/learning-sessions/{answered_session['learning_session_id']}"
        )
        assert kept.status_code == 200
        assert kept.json()["question"]["feedback"]["explanation"] == feedback["explanation"]
        assert kept.json()["question"]["feedback"]["citations"][0]["source_status"] != "AVAILABLE"
        assert kept.json()["question"]["feedback"]["citations"][0]["can_open_source"] is False
        again = client.post(
            f"/api/v1/learning-questions/{answered_session['question']['question_id']}/attempts",
            headers=_headers("history-learn-invalid-again"),
            json={
                "selected_option": answered_session["question"]["options"][0]["option_id"],
                "client_request_id": "history-learn-invalid-again",
                "expected_question_version": answered_session["question"]["row_version"],
            },
        )
        assert again.status_code == 409
        attempts, questions = _counts(client)
        assert attempts == 1
        assert questions == 2
    finally:
        client.__exit__(None, None, None)
