from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    ContentObject,
    Conversation,
    FileRecord,
    KnowledgeBase,
    LearningSession,
    new_id,
)
from mindmate.main import create_app


def _session_factory(client: TestClient):
    app = client.app
    if not isinstance(app, FastAPI):
        raise AssertionError("测试客户端没有返回 FastAPI 应用。")
    return app.state.session_factory


def _overview(client: TestClient, **params: int) -> dict:
    response = client.get("/api/v1/home/overview", params=params or None)
    assert response.status_code == 200
    return response.json()


def test_home_overview_counts_active_records_and_keeps_reads_side_effect_free(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    now = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"})
        empty = _overview(client)
        assert empty["files"] == 0
        assert empty["knowledge_bases"] == 0
        assert empty["conversations"] == 0
        assert empty["learning_sessions"] == 0
        assert empty["tasks"]["queued_count"] == 0
        assert empty["tasks"]["running_count"] == 0
        assert empty["tasks"]["failed_count"] == 0
        assert empty["tasks"]["total_count"] == 0
        created = client.post(
            "/api/v1/knowledge-bases",
            headers={"Origin": "http://127.0.0.1:5173", "Idempotency-Key": "home-overview-kb"},
            json={"name": "公开合成库", "description": "公开合成资料"},
        )
        assert created.status_code == 201
        with _session_factory(client)() as session:
            content = ContentObject(
                content_object_id=new_id(),
                sha256="a" * 64,
                byte_size=4,
                storage_relative_path="objects/public.txt",
                storage_state="READY",
                reference_count=1,
                created_at=now,
            )
            session.add(content)
            session.add(
                FileRecord(
                    file_id=new_id(),
                    content_object_id=content.content_object_id,
                    display_name="失败样本.txt",
                    extension=".txt",
                    document_type="TXT",
                    status="PARSE_FAILED",
                    source_name="失败样本.txt",
                    content_hash="a" * 64,
                    byte_size=4,
                    created_at=now,
                    updated_at=now,
                )
            )
            trashed_content = ContentObject(
                content_object_id=new_id(),
                sha256="b" * 64,
                byte_size=4,
                storage_relative_path="objects/trashed.txt",
                storage_state="READY",
                reference_count=1,
                created_at=now,
            )
            session.add(trashed_content)
            session.add(
                FileRecord(
                    file_id=new_id(),
                    content_object_id=trashed_content.content_object_id,
                    display_name="已回收.txt",
                    extension=".txt",
                    document_type="TXT",
                    status="IN_TRASH",
                    source_name="已回收.txt",
                    content_hash="b" * 64,
                    byte_size=4,
                    created_at=now,
                    updated_at=now,
                    deleted_at=now,
                )
            )
            session.add(
                KnowledgeBase(
                    knowledge_base_id=new_id(),
                    name="已回收库",
                    status="IN_TRASH",
                    created_at=now,
                    updated_at=now,
                    deleted_at=now,
                )
            )
            session.add(
                Conversation(
                    conversation_id=new_id(),
                    title="公开问答",
                    current_mode="GENERAL_CHAT",
                    current_scope_type="NONE",
                    current_scope_id_list=[],
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                    last_active_at=now,
                )
            )
            session.add(
                Conversation(
                    conversation_id=new_id(),
                    title="已回收问答",
                    current_mode="GENERAL_CHAT",
                    current_scope_type="NONE",
                    current_scope_id_list=[],
                    status="IN_TRASH",
                    created_at=now,
                    updated_at=now,
                    last_active_at=now,
                    deleted_at=now,
                )
            )
            session.add(
                LearningSession(
                    learning_session_id=new_id(),
                    topic="已完成",
                    goal_text="记住公开样本",
                    knowledge_base_id=created.json()["knowledge_base_id"],
                    target_question_count=1,
                    status="COMPLETED",
                    idempotency_key="home-learning-done",
                    client_request_id="home-learning-done",
                    request_hash="c" * 64,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                LearningSession(
                    learning_session_id=new_id(),
                    topic="已回收",
                    goal_text="不应计入",
                    knowledge_base_id=created.json()["knowledge_base_id"],
                    target_question_count=1,
                    status="IN_PROGRESS",
                    idempotency_key="home-learning-trash",
                    client_request_id="home-learning-trash",
                    request_hash="d" * 64,
                    created_at=now,
                    updated_at=now,
                    deleted_at=now,
                )
            )
            session.commit()
            before_tasks = session.scalar(select(func.count()).select_from(BackgroundTask))

        payload = _overview(client)
        assert payload["files"] == 1
        assert payload["knowledge_bases"] == 1
        assert payload["conversations"] == 1
        assert payload["learning_sessions"] == 1
        assert "解析失败" in payload["count_scope"]["files"]
        assert "已完成" in payload["count_scope"]["learning_sessions"]
        assert payload["tasks"]["total_count"] == before_tasks
        assert payload["tasks"]["latest"] is None

        with _session_factory(client)() as session:
            assert session.scalar(select(func.count()).select_from(BackgroundTask)) == before_tasks


def test_home_overview_projects_task_states_without_sensitive_details(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    now = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
    secret = r"C:\Users\secret\notes.txt sk-live-secret"
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"})
        with _session_factory(client)() as session:
            queued = BackgroundTask(
                task_id=new_id(),
                task_type="HOME_FIXTURE",
                status="QUEUED",
                phase="QUEUED",
                progress=0,
                checkpoint_json={"items": [{"source_name": "public.txt"}]},
                created_at=now,
                updated_at=now,
            )
            running = BackgroundTask(
                task_id=new_id(),
                task_type="HOME_FIXTURE",
                status="RUNNING",
                phase="EMBEDDING",
                progress=40,
                checkpoint_json={"next_ordinal": 2, "results": []},
                created_at=now,
                updated_at=now.replace(minute=5),
            )
            unknown = BackgroundTask(
                task_id=new_id(),
                task_type="HOME_FIXTURE",
                status="RUNNING",
                phase="CHUNKING",
                progress=0,
                checkpoint_json={},
                created_at=now,
                updated_at=now.replace(minute=4),
            )
            failed = BackgroundTask(
                task_id=new_id(),
                task_type="HOME_FIXTURE",
                status="FAILED",
                phase="PARSING",
                progress=100,
                error_summary=secret,
                checkpoint_json={"items": [{"parse_error_id": "PARSER_FAILED", "path": secret}]},
                created_at=now,
                updated_at=now.replace(minute=6),
            )
            session.add_all([queued, running, unknown, failed])
            session.commit()
            assert failed.row_version == 1

        payload = _overview(client, task_limit=2)
        tasks = payload["tasks"]
        assert tasks["queued_count"] == 1
        assert tasks["running_count"] == 2
        assert tasks["failed_count"] == 1
        assert tasks["total_count"] == 4
        assert tasks["latest"]["status"] == "FAILED"
        assert tasks["latest"]["failure_code"] == "PARSER_FAILED"
        assert tasks["latest"]["failure_summary"] == "失败详情已省略"
        assert tasks["latest"]["progress_percent"] is None
        assert len(tasks["recent"]) == 2
        running_item = next(
            item
            for item in _overview(client)["tasks"]["recent"]
            if item["status"] == "RUNNING" and item["phase"] == "EMBEDDING"
        )
        assert running_item["progress_percent"] == 40
        chunk_item = next(
            item
            for item in _overview(client)["tasks"]["recent"]
            if item["phase"] == "CHUNKING"
        )
        assert chunk_item["progress_percent"] is None
        body = client.get("/api/v1/home/overview").text
        assert secret not in body
        assert "sk-live-secret" not in body
        assert "notes.txt" not in body

        with _session_factory(client)() as session:
            stored = session.get(BackgroundTask, failed.task_id)
            assert stored is not None
            assert stored.row_version == 1
            assert stored.status == "FAILED"
            assert stored.error_summary == secret
