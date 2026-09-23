from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session
from uuid6 import uuid7

from mindmate.infrastructure.models import BackgroundTask, TaskAttempt, TaskEvent

FINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
CLAIMABLE_STATES = {"QUEUED", "INTERRUPTED"}


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


def _claimable_clause(now_value: datetime):
    return or_(
        BackgroundTask.status.in_(CLAIMABLE_STATES),
        and_(
            BackgroundTask.status == "RUNNING",
            or_(
                BackgroundTask.lease_until.is_(None),
                BackgroundTask.lease_until <= now_value,
            ),
        ),
    )


def claim_task(
    session: Session, task_id: str, worker_id: str, lease_seconds: int = 60
) -> BackgroundTask | None:
    """Atomically claim one task if it is queued or its lease has expired.

    The conditional UPDATE is the concurrency boundary. A caller may inspect task
    candidates first, but only a rowcount of one grants ownership.
    """
    started = now()
    lease_until = started + timedelta(seconds=lease_seconds)
    result = session.execute(
        update(BackgroundTask)
        .where(BackgroundTask.task_id == task_id, _claimable_clause(started))
        .values(
            status="RUNNING",
            lease_owner=worker_id,
            lease_until=lease_until,
            started_at=func.coalesce(BackgroundTask.started_at, started),
            updated_at=started,
            row_version=BackgroundTask.row_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        return None
    task = session.get(BackgroundTask, task_id)
    if task is None:
        return None
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


def claim_next_task(
    session: Session,
    worker_id: str,
    lease_seconds: int = 60,
    task_types: set[str] | None = None,
) -> BackgroundTask | None:
    """Find candidates and use the atomic claim boundary for each one."""
    statement = select(BackgroundTask.task_id).where(_claimable_clause(now()))
    if task_types is not None:
        statement = statement.where(BackgroundTask.task_type.in_(task_types))
    candidate_ids = session.scalars(
        statement
        .order_by(BackgroundTask.priority.desc(), BackgroundTask.created_at)
        .limit(32)
    )
    for task_id in candidate_ids:
        claimed = claim_task(session, task_id, worker_id, lease_seconds)
        if claimed is not None:
            return claimed
    return None


def renew_task_lease(
    session: Session, task_id: str, worker_id: str, lease_seconds: int = 60
) -> bool:
    current = now()
    result = session.execute(
        update(BackgroundTask)
        .where(
            BackgroundTask.task_id == task_id,
            BackgroundTask.status == "RUNNING",
            BackgroundTask.lease_owner == worker_id,
        )
        .values(
            lease_until=current + timedelta(seconds=lease_seconds),
            updated_at=current,
            row_version=BackgroundTask.row_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    return getattr(result, "rowcount", 0) == 1


def finish_attempt(
    session: Session, task_id: str, status: str, error_summary: str | None = None
) -> None:
    attempt = session.scalar(
        select(TaskAttempt)
        .where(TaskAttempt.task_id == task_id, TaskAttempt.status == "RUNNING")
        .order_by(TaskAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is not None:
        attempt.status = status
        attempt.error_summary = error_summary
        attempt.completed_at = now()


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
    if task.status in FINAL_STATES:
        return
    task.status = "CANCELLED"
    task.updated_at = now()
    task.completed_at = now()
    task.lease_owner = None
    task.lease_until = None
    task.row_version += 1
    add_event(session, task, "CANCELLED")


def recover_running_tasks(session: Session) -> int:
    """Legacy stage-3 recovery helper: mark all running work interrupted."""
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


def recover_expired_tasks(session: Session) -> int:
    """Release only leases that are known to be expired."""
    result = session.execute(
        update(BackgroundTask)
        .where(
            BackgroundTask.status == "RUNNING",
            or_(
                BackgroundTask.lease_until.is_(None),
                BackgroundTask.lease_until <= now(),
            ),
        )
        .values(
            status="INTERRUPTED",
            updated_at=now(),
            lease_owner=None,
            lease_until=None,
            row_version=BackgroundTask.row_version + 1,
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


def interrupt_owned_tasks(session: Session, worker_id: str) -> int:
    """Stop accepting work while leaving an explicit recoverable checkpoint."""
    result = session.execute(
        update(BackgroundTask)
        .where(
            BackgroundTask.status == "RUNNING",
            BackgroundTask.lease_owner == worker_id,
        )
        .values(
            status="INTERRUPTED",
            updated_at=now(),
            lease_owner=None,
            lease_until=None,
            row_version=BackgroundTask.row_version + 1,
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)
