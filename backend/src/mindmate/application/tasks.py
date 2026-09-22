from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from uuid6 import uuid7

from mindmate.infrastructure.models import BackgroundTask, TaskAttempt, TaskEvent

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}


def now() -> datetime:
    return datetime.now(UTC)


def create_task(
    session: Session, task_type: str, idempotency_key: str, payload: dict[str, Any] | None = None
) -> BackgroundTask:
    existing = session.scalar(
        select(BackgroundTask).where(BackgroundTask.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    task = BackgroundTask(
        task_id=str(uuid7()),
        task_type=task_type,
        status="QUEUED",
        checkpoint_json=payload,
        idempotency_key=idempotency_key,
        created_at=now(),
        updated_at=now(),
    )
    session.add(task)
    session.flush()
    add_event(session, task, "QUEUED", {"checkpoint_version": task.checkpoint_version})
    return task


def add_event(
    session: Session, task: BackgroundTask, event_type: str, payload: dict[str, Any] | None = None
) -> TaskEvent:
    sequence = (
        session.scalar(
            select(TaskEvent.sequence)
            .where(TaskEvent.task_id == task.task_id)
            .order_by(TaskEvent.sequence.desc())
            .limit(1)
        )
        or 0
    )
    event = TaskEvent(
        task_id=task.task_id,
        sequence=sequence + 1,
        event_type=event_type,
        payload_json=payload,
        created_at=now(),
    )
    session.add(event)
    return event


def claim_task(
    session: Session, task_id: str, worker_id: str, lease_seconds: int = 60
) -> BackgroundTask | None:
    task = session.get(BackgroundTask, task_id)
    if task is None or task.status in TERMINAL_STATES:
        return None
    if task.lease_until and task.lease_until > now() and task.lease_owner != worker_id:
        return None
    task.status = "RUNNING"
    task.lease_owner = worker_id
    task.lease_until = now() + timedelta(seconds=lease_seconds)
    task.started_at = task.started_at or now()
    task.updated_at = now()
    task.row_version += 1
    attempt_number = (
        session.scalar(
            select(TaskAttempt.attempt_number)
            .where(TaskAttempt.task_id == task_id)
            .order_by(TaskAttempt.attempt_number.desc())
            .limit(1)
        )
        or 0
    ) + 1
    session.add(
        TaskAttempt(
            task_id=task_id,
            attempt_number=attempt_number,
            started_at=now(),
            checkpoint_version=task.checkpoint_version,
        )
    )
    add_event(session, task, "RUNNING", {"worker_id": worker_id, "attempt": attempt_number})
    return task


def checkpoint_task(
    session: Session,
    task: BackgroundTask,
    phase: str,
    checkpoint: dict[str, Any],
    progress: int | None = None,
) -> None:
    if progress is not None and task.progress is not None and progress < task.progress:
        raise ValueError("task progress cannot decrease")
    task.phase = phase
    task.progress = progress
    task.checkpoint_json = checkpoint
    task.checkpoint_version += 1
    task.row_version += 1
    task.updated_at = now()
    add_event(
        session,
        task,
        "CHECKPOINT",
        {"phase": phase, "progress": progress, "version": task.checkpoint_version},
    )


def cancel_task(session: Session, task: BackgroundTask) -> None:
    if task.status in TERMINAL_STATES and task.status != "INTERRUPTED":
        return
    task.status = "CANCELLED"
    task.updated_at = now()
    task.completed_at = now()
    task.row_version += 1
    add_event(session, task, "CANCELLED")


def recover_running_tasks(session: Session) -> int:
    result = session.execute(
        update(BackgroundTask)
        .where(BackgroundTask.status == "RUNNING")
        .values(
            status="INTERRUPTED",
            updated_at=now(),
            lease_owner=None,
            lease_until=None,
            row_version=BackgroundTask.row_version + 1,
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)
