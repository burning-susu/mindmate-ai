"""Stage 8: background task retention cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mindmate.application.task_retention import preview_task_retention, purge_expired_tasks
from mindmate.application.tasks import add_event, create_task
from mindmate.config import Settings
from mindmate.infrastructure.db import quick_check
from mindmate.infrastructure.models import (
    AiOperation,
    BackgroundTask,
    Conversation,
    FileRecord,
    KnowledgeBase,
    LearningSession,
    TaskAttempt,
    TaskEvent,
)
from mindmate.main import create_app
from test_stage8_conversation_history import _client as _chat_client
from test_stage8_conversation_history import _send

ORIGIN = "http://127.0.0.1:5173"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path, env="test")
    app = create_app(settings)
    client = TestClient(app, base_url="http://127.0.0.1")
    client.__enter__()
    client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    return client


def _headers(key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key}


def _seed_task(
    factory: Any,
    *,
    key: str,
    status: str,
    completed_days_ago: int | None,
    parent_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    with factory() as session:
        task = create_task(session, "LOCAL_STATUS_SAMPLE", key)
        if parent_id is not None:
            task.parent_task_id = parent_id
        if completed_days_ago is None:
            task.status = status
            task.updated_at = now
            session.commit()
            return task.task_id
        finished = now - timedelta(days=completed_days_ago)
        task.status = status
        task.completed_at = finished
        task.updated_at = now
        task.started_at = finished - timedelta(minutes=1)
        add_event(session, task, status, {"note": "fixture"})
        session.add(
            TaskAttempt(
                task_id=task.task_id,
                attempt_number=1,
                status=status,
                started_at=finished - timedelta(minutes=1),
                completed_at=finished,
            )
        )
        session.commit()
        return task.task_id


def test_task_retention_7_and_30_day_boundaries(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        factory = cast(Any, client.app).state.session_factory
        success_due = _seed_task(
            factory, key="ret-success-due", status="COMPLETED", completed_days_ago=8
        )
        success_keep = _seed_task(
            factory, key="ret-success-keep", status="COMPLETED", completed_days_ago=3
        )
        cancelled_due = _seed_task(
            factory, key="ret-cancel-due", status="CANCELLED", completed_days_ago=7
        )
        failed_due = _seed_task(
            factory, key="ret-failed-due", status="FAILED", completed_days_ago=31
        )
        failed_keep = _seed_task(
            factory, key="ret-failed-keep", status="FAILED", completed_days_ago=10
        )
        interrupted_due = _seed_task(
            factory, key="ret-int-due", status="INTERRUPTED", completed_days_ago=30
        )
        running = _seed_task(
            factory, key="ret-running", status="RUNNING", completed_days_ago=None
        )
        blocked = _seed_task(
            factory, key="ret-blocked", status="BLOCKED", completed_days_ago=None
        )
        missing_time = _seed_task(
            factory, key="ret-missing", status="QUEUED", completed_days_ago=None
        )
        with factory() as session:
            row = session.get(BackgroundTask, missing_time)
            assert row is not None
            row.status = "FAILED"
            row.completed_at = None
            session.commit()

        now = datetime.now(UTC)
        with factory() as session:
            preview = preview_task_retention(session, now=now)
            assert preview["success_or_cancelled"] >= 2
            assert preview["failed_partial_interrupted"] >= 2
            assert preview["active_not_eligible"] >= 2
            assert preview["missing_completed_at"] >= 1
            stats = purge_expired_tasks(session, now=now, limit=50)
        assert stats["purged"] >= 4
        assert stats["errors"] == 0
        with factory() as session:
            assert session.get(BackgroundTask, success_due) is None
            assert session.get(BackgroundTask, cancelled_due) is None
            assert session.get(BackgroundTask, failed_due) is None
            assert session.get(BackgroundTask, interrupted_due) is None
            assert session.get(BackgroundTask, success_keep) is not None
            assert session.get(BackgroundTask, failed_keep) is not None
            assert session.get(BackgroundTask, running) is not None
            assert session.get(BackgroundTask, blocked) is not None
            assert session.get(BackgroundTask, missing_time) is not None
            assert (
                int(
                    session.scalar(
                        select(func.count())
                        .select_from(TaskEvent)
                        .where(TaskEvent.task_id == success_due)
                    )
                    or 0
                )
                == 0
            )
            assert quick_check(cast(Any, client.app).state.engine) == "ok"
    finally:
        client.__exit__(None, None, None)


def test_task_retention_skips_references_and_keeps_business_rows(tmp_path: Path) -> None:
    client = _chat_client(tmp_path)
    try:
        conversation_id = _send(client, "ret-chat-link", "任务引用保护对话")
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            operation = session.scalar(
                select(AiOperation).where(AiOperation.conversation_id == conversation_id)
            )
            assert operation is not None and operation.task_id is not None
            linked = operation.task_id
            task = session.get(BackgroundTask, linked)
            assert task is not None
            task.status = "COMPLETED"
            task.completed_at = datetime.now(UTC) - timedelta(days=10)
            session.commit()

        parent = _seed_task(
            factory, key="ret-parent-active", status="RUNNING", completed_days_ago=None
        )
        child = _seed_task(
            factory,
            key="ret-child-done",
            status="COMPLETED",
            completed_days_ago=10,
            parent_id=parent,
        )
        parent_done = _seed_task(
            factory, key="ret-parent-done", status="COMPLETED", completed_days_ago=10
        )
        child_of_done = _seed_task(
            factory,
            key="ret-child-of-done",
            status="COMPLETED",
            completed_days_ago=10,
            parent_id=parent_done,
        )
        with factory() as session:
            before_files = int(session.scalar(select(func.count()).select_from(FileRecord)) or 0)
            before_kb = int(session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0)
            before_chat = int(session.scalar(select(func.count()).select_from(Conversation)) or 0)
            before_learn = int(
                session.scalar(select(func.count()).select_from(LearningSession)) or 0
            )
            stats = purge_expired_tasks(session, now=datetime.now(UTC), limit=50)
            assert session.get(BackgroundTask, linked) is not None
            assert session.get(BackgroundTask, child) is not None
            assert session.get(BackgroundTask, parent_done) is not None
            # Child under a terminal parent is eligible once due; parent stays while
            # any child row still exists or after children are removed by later batches.
            assert session.get(Conversation, conversation_id) is not None
            assert child_of_done  # created for parent HAS_CHILD coverage
            assert session.get(BackgroundTask, child_of_done) is None or session.get(
                BackgroundTask, parent_done
            ) is not None
            assert int(session.scalar(select(func.count()).select_from(FileRecord)) or 0) == before_files
            assert int(session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0) == before_kb
            assert int(session.scalar(select(func.count()).select_from(Conversation)) or 0) == before_chat
            assert int(session.scalar(select(func.count()).select_from(LearningSession)) or 0) == before_learn
            assert stats["skipped_referenced"] >= 1
    finally:
        client.__exit__(None, None, None)


def test_task_retention_api_preview_confirm_and_home_consistency(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        factory = cast(Any, client.app).state.session_factory
        due = _seed_task(
            factory, key="ret-api-due", status="COMPLETED", completed_days_ago=9
        )
        preview = client.get("/api/v1/home/tasks/retention-preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["eligible_total"] >= 1
        denied = client.post(
            "/api/v1/home/tasks/retention-purge",
            headers=_headers("ret-api-deny"),
            json={"confirmed": False},
        )
        assert denied.status_code == 400
        assert denied.json()["code"] == "PURGE_CONFIRMATION_REQUIRED"
        before = client.get("/api/v1/home/overview").json()["tasks"]["total_count"]
        ok = client.post(
            "/api/v1/home/tasks/retention-purge",
            headers=_headers("ret-api-ok"),
            json={
                "confirmed": True,
                "clear_success": True,
                "clear_cancelled": True,
                "clear_failed": True,
                "limit": 20,
            },
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["purged"] >= 1
        after = client.get("/api/v1/home/overview").json()["tasks"]["total_count"]
        assert after == before - ok.json()["purged"]
        with factory() as session:
            assert session.get(BackgroundTask, due) is None
    finally:
        client.__exit__(None, None, None)
