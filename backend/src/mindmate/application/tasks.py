from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session, aliased
from uuid6 import uuid7

from mindmate.application.task_concurrency import (
    HEAVY_TASK_TYPES,
    VECTOR_WRITE_TASK_TYPES,
    read_task_concurrency,
)
from mindmate.infrastructure.models import (
    BackgroundTask,
    IndexVersion,
    IndexVersionInput,
    TaskAttempt,
    TaskEvent,
)

FINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
CLAIMABLE_STATES = {"QUEUED", "INTERRUPTED"}
TARGET_CANCEL_STATES = {"QUEUED", "BLOCKED", "RUNNING", "INTERRUPTED", "PAUSED", "CANCELLING"}
PARTIAL_FILE_TASK_TYPES = {
    "FILE_IMPORT",
    "FILE_REPROCESS",
    "KNOWLEDGE_MEMBERSHIP_ADD",
}


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


def _claimable_clause(now_value: datetime, task_model=BackgroundTask):
    return or_(
        task_model.status.in_(CLAIMABLE_STATES),
        and_(
            task_model.status == "RUNNING",
            or_(
                task_model.lease_until.is_(None),
                task_model.lease_until <= now_value,
            ),
        ),
    )


def _normalize_concurrency_groups(
    groups: str | tuple[str, ...] | None,
) -> tuple[str, ...]:
    if groups is None:
        return ()
    if isinstance(groups, str):
        return (groups,)
    return tuple(dict.fromkeys(groups))


def _concurrency_available_clauses(
    session: Session,
    current: datetime,
    groups: str | tuple[str, ...] | None,
    *,
    task_model=BackgroundTask,
) -> list[Any]:
    normalized = _normalize_concurrency_groups(groups)
    if not normalized:
        return []
    config = read_task_concurrency(session)
    clauses: list[Any] = []
    group_types = {
        "HEAVY": HEAVY_TASK_TYPES,
        "VECTOR_WRITE": VECTOR_WRITE_TASK_TYPES,
    }
    for group in normalized:
        task_types = group_types.get(group)
        limit = config.limit_for(group)
        if not task_types or limit is None:
            continue
        active_count = (
            select(func.count())
            .select_from(task_model)
            .where(
                task_model.task_type.in_(task_types),
                task_model.status == "RUNNING",
                task_model.lease_until > current,
            )
            .scalar_subquery()
        )
        clauses.append(active_count < limit)
    return clauses


def claim_task(
    session: Session,
    task_id: str,
    worker_id: str,
    lease_seconds: int = 60,
    *,
    concurrency_groups: str | tuple[str, ...] | None = None,
) -> BackgroundTask | None:
    """Atomically claim one task if it is queued or its lease has expired.

    The conditional UPDATE is the concurrency boundary. A caller may inspect task
    candidates first, but only a rowcount of one grants ownership.
    """
    started = now()
    lease_until = started + timedelta(seconds=lease_seconds)
    result = session.execute(
        update(BackgroundTask)
        .where(
            BackgroundTask.task_id == task_id,
            _claimable_clause(started),
            *_concurrency_available_clauses(session, started, concurrency_groups),
        )
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
    _record_claim(session, task, worker_id)
    return task


def claim_next_serial_task(
    session: Session,
    task_type: str,
    worker_id: str,
    lease_seconds: int = 60,
    *,
    concurrency_groups: str | tuple[str, ...] | None = None,
) -> BackgroundTask | None:
    """Atomically claim one task while enforcing a process-wide concurrency limit of one."""
    current = now()
    lease_until = current + timedelta(seconds=lease_seconds)
    expired_ids = list(
        session.scalars(
            select(BackgroundTask.task_id).where(
                BackgroundTask.task_type == task_type,
                BackgroundTask.status == "RUNNING",
                or_(BackgroundTask.lease_until.is_(None), BackgroundTask.lease_until <= current),
            )
        )
    )
    if expired_ids:
        session.execute(
            update(BackgroundTask)
            .where(
                BackgroundTask.task_id.in_(expired_ids),
                BackgroundTask.status == "RUNNING",
                or_(BackgroundTask.lease_until.is_(None), BackgroundTask.lease_until <= current),
            )
            .values(
                status="INTERRUPTED",
                lease_owner=None,
                lease_until=None,
                updated_at=current,
                row_version=BackgroundTask.row_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        for task_id in expired_ids:
            finish_attempt(session, task_id, "INTERRUPTED", "Worker lease expired.")
    candidate = aliased(BackgroundTask)
    active = aliased(BackgroundTask)
    candidate_id = (
        select(candidate.task_id)
        .where(
            candidate.task_type == task_type,
            _claimable_clause(current, candidate),
            *_concurrency_available_clauses(session, current, concurrency_groups),
            ~exists(
                select(1).select_from(active).where(
                    active.task_type == task_type,
                    active.status == "RUNNING",
                    active.lease_until > current,
                )
            ),
        )
        .order_by(candidate.priority.desc(), candidate.created_at)
        .limit(1)
        .scalar_subquery()
    )
    result = session.execute(
        update(BackgroundTask)
        .where(
            BackgroundTask.task_id == candidate_id,
            _claimable_clause(current),
            *_concurrency_available_clauses(session, current, concurrency_groups),
        )
        .values(
            status="RUNNING",
            lease_owner=worker_id,
            lease_until=lease_until,
            started_at=func.coalesce(BackgroundTask.started_at, current),
            updated_at=current,
            row_version=BackgroundTask.row_version + 1,
        )
        .returning(BackgroundTask.task_id)
        .execution_options(synchronize_session=False)
    )
    task_id = result.scalar_one_or_none()
    if task_id is None:
        session.commit()
        return None
    task = session.get(BackgroundTask, task_id)
    if task is None:
        return None
    _record_claim(session, task, worker_id)
    return task


def _record_claim(session: Session, task: BackgroundTask, worker_id: str) -> None:
    attempt_number = (
        session.scalar(
            select(TaskAttempt.attempt_number)
            .where(TaskAttempt.task_id == task.task_id)
            .order_by(TaskAttempt.attempt_number.desc())
            .limit(1)
        )
        or 0
    ) + 1
    session.add(
        TaskAttempt(
            task_id=task.task_id,
            attempt_number=attempt_number,
            started_at=now(),
            checkpoint_version=task.checkpoint_version,
        )
    )
    add_event(session, task, "RUNNING", {"worker_id": worker_id, "attempt": attempt_number})


def claim_next_task(
    session: Session,
    worker_id: str,
    lease_seconds: int = 60,
    task_types: set[str] | None = None,
    *,
    concurrency_groups: str | tuple[str, ...] | None = None,
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
        claimed = claim_task(
            session,
            task_id,
            worker_id,
            lease_seconds,
            concurrency_groups=concurrency_groups,
        )
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


def cancel_task(
    session: Session,
    task: BackgroundTask,
    reason_code: str = "USER_REQUESTED",
) -> None:
    if task.status in FINAL_STATES:
        return
    cancellation_time = now()
    was_running = task.status == "RUNNING"
    task.cancel_requested_at = cancellation_time
    task.cancel_reason_code = reason_code[:80]
    task.status = "CANCELLED"
    task.updated_at = cancellation_time
    task.completed_at = cancellation_time
    task.lease_owner = None
    task.lease_until = None
    task.row_version += 1
    add_event(
        session,
        task,
        "CANCEL_REQUESTED" if was_running else "CANCELLED",
        {"reason_code": task.cancel_reason_code},
    )
    if was_running:
        add_event(session, task, "CANCELLED", {"reason_code": task.cancel_reason_code})
    finish_attempt(session, task.task_id, "CANCELLED", task.cancel_reason_code)


def cancel_tasks_for_targets(
    session: Session,
    *,
    file_ids: set[str] | None = None,
    folder_ids: set[str] | None = None,
    knowledge_base_ids: set[str] | None = None,
    reason_code: str = "TARGET_IN_TRASH",
) -> list[str]:
    """Cancel only durable tasks whose persisted target is now invalid.

    The caller keeps this operation in the same transaction as the soft
    deletion. Index-stage tasks are matched through their immutable version
    inputs, while old completed indexes and shared source objects are left
    untouched.
    """

    file_ids = set(file_ids or ())
    folder_ids = set(folder_ids or ())
    knowledge_base_ids = set(knowledge_base_ids or ())
    if not file_ids and not folder_ids and not knowledge_base_ids:
        return []

    tasks = list(
        session.scalars(
            select(BackgroundTask).where(~BackgroundTask.status.in_(FINAL_STATES))
        )
    )
    version_ids = {
        str(checkpoint.get("index_version_id"))
        for task in tasks
        if isinstance(task.checkpoint_json, dict)
        and isinstance((checkpoint := task.checkpoint_json).get("index_version_id"), str)
    }
    versions = {
        version.index_version_id: version
        for version in session.scalars(
            select(IndexVersion).where(IndexVersion.index_version_id.in_(version_ids))
        )
    }
    input_file_ids: dict[str, set[str]] = {}
    if file_ids and version_ids:
        for version_id, input_file_id in session.execute(
            select(IndexVersionInput.index_version_id, IndexVersionInput.file_id).where(
                IndexVersionInput.index_version_id.in_(version_ids),
                IndexVersionInput.file_id.in_(file_ids),
            )
        ):
            input_file_ids.setdefault(str(version_id), set()).add(str(input_file_id))

    cancelled: list[str] = []
    for task in tasks:
        if task.status not in TARGET_CANCEL_STATES:
            continue
        checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
        context_value = checkpoint.get("context")
        context = context_value if isinstance(context_value, dict) else {}
        direct_file_ids = {
            str(context.get("file_id"))
        } if isinstance(context.get("file_id"), str) else set()
        items = checkpoint.get("items")
        if isinstance(items, list):
            direct_file_ids.update(
                str(item.get("file_id"))
                for item in items
                if isinstance(item, dict) and isinstance(item.get("file_id"), str)
            )
        direct_folder_id = context.get("folder_id")
        target_knowledge_base = checkpoint.get("knowledge_base_id")
        version_id = checkpoint.get("index_version_id")
        version = versions.get(version_id) if isinstance(version_id, str) else None
        direct_file_matches = direct_file_ids & file_ids
        matches = bool(direct_file_matches) and (
            task.task_type not in PARTIAL_FILE_TASK_TYPES
            or not (direct_file_ids - file_ids)
        )
        matches = matches or (isinstance(direct_folder_id, str) and direct_folder_id in folder_ids)
        matches = matches or (
            isinstance(target_knowledge_base, str) and target_knowledge_base in knowledge_base_ids
        )
        matches = matches or (
            version is not None and version.scope_id in knowledge_base_ids
        )
        matches = matches or (
            isinstance(version_id, str) and bool(input_file_ids.get(version_id))
        )
        if matches:
            cancel_task(session, task, reason_code)
            cancelled.append(task.task_id)
    return cancelled


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
