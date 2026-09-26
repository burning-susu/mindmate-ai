from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.ai.providers.mock import MockChatProvider
from mindmate.application.source_snapshots import purge_source_snapshots_for_files
from mindmate.config import Settings
from mindmate.infrastructure.models import Conversation, FileRecord, KnowledgeBase, Message
from mindmate.main import create_app
from test_stage5_source_snapshots import _seed_active_index, _supported_result
from test_stage6_knowledge_chat import _Encoder, _Query

ORIGIN = "http://127.0.0.1:5173"


def _headers(key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key}


def _client(tmp_path: Path, provider: MockChatProvider | None = None) -> TestClient:
    app = create_app(Settings(data_dir=tmp_path, env="test", chat_worker_poll_seconds=0.01))
    app.state.chat_provider = provider or MockChatProvider()
    client = TestClient(app, base_url="http://127.0.0.1")
    client.__enter__()
    client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    return client


def _wait(client: TestClient, operation_id: str) -> dict[str, Any]:
    for _ in range(200):
        payload = client.get(f"/api/v1/ai-operations/{operation_id}").json()
        if payload["status"] not in {"QUEUED", "RUNNING", "STOPPING"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("chat operation did not finish")


def _send(client: TestClient, key: str, content: str) -> str:
    created = client.post(
        "/api/v1/conversations",
        headers=_headers(key),
        json={"first_message": content, "client_request_id": key},
    )
    assert created.status_code == 202, created.text
    operation = _wait(client, created.json()["operation_id"])
    assert operation["status"] == "COMPLETED"
    return created.json()["conversation_id"]


def _message_count(client: TestClient) -> int:
    factory = cast(Any, client.app).state.session_factory
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(Message)) or 0)


def test_history_sorts_pages_and_skips_recycled_conversations(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        first = _send(client, "history-a", "最早的问题")
        second = _send(client, "history-b", "中间的问题")
        tail = "HISTORY-TAIL-NOT-IN-LIST"
        third = _send(client, "history-c", f"{'最新问题' * 30}{tail}")
        recycled = _send(client, "history-d", "已回收的问题")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            record = session.get(Conversation, recycled)
            assert record is not None
            record.deleted_at = datetime.now(UTC)
            session.commit()
        before = _message_count(client)
        page = client.get("/api/v1/history/conversations", params={"limit": 1})
        assert page.status_code == 200, page.text
        body = page.json()
        assert [item["conversation_id"] for item in body["items"]] == [third]
        assert body["next_cursor"]
        assert tail not in page.text
        assert "resolved_model" not in page.text
        assert len(body["items"][0]["summary"]) <= 81
        assert body["items"][0]["current_mode"] == "GENERAL_CHAT"
        assert body["items"][0]["source_status"] == "NOT_APPLICABLE"
        assert body["items"][0]["status"] == "ACTIVE"
        second_page = client.get(
            "/api/v1/history/conversations",
            params={"limit": 2, "cursor": body["next_cursor"]},
        )
        assert second_page.status_code == 200
        ids = [item["conversation_id"] for item in second_page.json()["items"]]
        assert ids == [second, first]
        assert second_page.json()["next_cursor"] is None
        assert recycled not in ids
        assert _message_count(client) == before
        invalid = client.get("/api/v1/history/conversations", params={"cursor": "not-a-cursor"})
        assert invalid.status_code == 400
        assert invalid.json()["code"] == "HISTORY_CURSOR_INVALID"
    finally:
        client.__exit__(None, None, None)


def test_history_reopens_same_messages_after_process_restart(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        conversation_id = _send(client, "history-restart", "重启后仍应读到的问题")
        before = client.get(f"/api/v1/conversations/{conversation_id}/messages").json()
    finally:
        client.__exit__(None, None, None)

    restarted = _client(tmp_path)
    try:
        listed = restarted.get("/api/v1/history/conversations")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["conversation_id"] == conversation_id
        after = restarted.get(f"/api/v1/conversations/{conversation_id}/messages").json()
        assert [item["message_id"] for item in after["items"]] == [
            item["message_id"] for item in before["items"]
        ]
        assert [item["content"] for item in after["items"]] == [
            item["content"] for item in before["items"]
        ]
        assert _message_count(restarted) == len(before["items"])
    finally:
        restarted.__exit__(None, None, None)


def test_history_marks_deleted_trashed_and_unready_sources(tmp_path: Path) -> None:
    provider = MockChatProvider(response_factory=lambda _request: "资料结论 [1]")
    client = _client(tmp_path, provider)
    try:
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, Settings(data_dir=tmp_path, env="test"))
        result = _supported_result(data)
        worker = cast(Any, client.app).state.chat_worker
        worker._retrieval_query_encoder_getter = lambda: _Encoder()
        worker._retrieval_query_getter = lambda _settings: _Query(result)
        created = client.post(
            "/api/v1/conversations",
            headers=_headers("history-source"),
            json={
                "mode": "KNOWLEDGE_CHAT",
                "source_scope": {
                    "scope_type": "KNOWLEDGE_BASE",
                    "knowledge_base_id": data.knowledge_base_id,
                },
                "first_message": "什么是向量数据库？",
                "client_request_id": "history-source",
            },
        )
        assert created.status_code == 202, created.text
        operation = _wait(client, created.json()["operation_id"])
        assert operation["status"] == "COMPLETED"
        conversation_id = created.json()["conversation_id"]
        calls = len(provider.calls)
        ready = client.get("/api/v1/history/conversations").json()["items"][0]
        assert ready["conversation_id"] == conversation_id
        assert ready["source_status"] == "AVAILABLE"
        assert ready["scope_name"]

        with factory() as session:
            knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
            assert knowledge_base is not None
            knowledge_base.status = "PREPARING"
            session.commit()
        unready = client.get("/api/v1/history/conversations").json()["items"][0]
        assert unready["source_status"] == "INDEX_VERSION_RETIRED"
        assert unready["status"] == "SOURCE_INVALID"
        with factory() as session:
            knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
            assert knowledge_base is not None
            knowledge_base.status = "READY"
            file_record = session.get(FileRecord, data.file_id)
            assert file_record is not None
            file_record.deleted_at = datetime.now(UTC)
            session.commit()
        trashed = client.get("/api/v1/history/conversations").json()["items"][0]
        assert trashed["source_status"] == "SOURCE_IN_TRASH"
        with factory() as session:
            purge_source_snapshots_for_files(session, [data.file_id])
            session.commit()
        deleted = client.get("/api/v1/history/conversations").json()["items"][0]
        assert deleted["source_status"] == "SOURCE_DELETED"
        assert deleted["status"] == "SOURCE_INVALID"
        messages = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert messages.status_code == 200
        user = messages.json()["items"][0]
        assistant = messages.json()["items"][1]
        assert user["content"] == "什么是向量数据库？"
        assert "资料结论" in assistant["content"]
        assert assistant["citations"][0]["source_status"] == "SOURCE_DELETED"
        assert assistant["citations"][0]["can_open_source"] is False
        assert len(provider.calls) == calls
    finally:
        client.__exit__(None, None, None)
