"""Retention cleanup for durable background task records only.

Deletes expired terminal BackgroundTask rows and their TaskAttempt/TaskEvent
children. Never deletes files, knowledge bases, conversations, or learning data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from mindmate.infrastructure.models import (
    AiOperation,
    BackgroundTask,
    TaskAttempt,
    TaskEvent,
)

SUCCESS_STATES = frozenset({"COMPLETED", "SUCCEEDED", "CANCELLED"})
FAILURE_STATES = frozenset({"FAILED", "PARTIAL", "INTERRUPTED"})
ACTIVE_STATES = frozenset(
    {"CREATED", "QUEUED", "RUNNING", "BLOCKED", "PAUSED", "CANCELLING", "STOPPING"}
)
SUCCESS_RETENTION = timedelta(days=7)
FAILURE_RETENTION = timedelta(days=30)
DEFAULT_BATCH = 20


class TaskRetentionError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def utc_now() -> datetime:
    return datetime.now(UTC)


def preview_task_retention(
    session: Session, *, now: datetime | None = None
) -> dict[str, Any]:
    clock = _normalize(now)
    sql_now = _sql_utc(clock)
    eligible = _eligible_ids(session, sql_now, limit=500)
    skipped = _count_referenced(session, eligible)
    cleanable = [task_id for task_id in eligible if task_id not in skipped]
    by_group = _group_counts(session, cleanable)
    return {
        "as_of": clock,
        "eligible_total": len(cleanable),
        "skipped_referenced": len(skipped),
        "success_or_cancelled": by_group["success_or_cancelled"],
        "failed_partial_interrupted": by_group["failed_partial_interrupted"],
        "active_not_eligible": _count_active(session),
        "missing_completed_at": _count_missing_terminal_time(session),
    }


def purge_expired_tasks(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_BATCH,
    categories: set[str] | None = None,
) -> dict[str, Any]:
    """Purge a bounded set of expired, unreferenced terminal tasks."""
    if limit < 1 or limit > 100:
        raise TaskRetentionError("TASK_RETENTION_LIMIT_INVALID", "单批清理数量无效。")
    allowed = categories or {"success_or_cancelled", "failed_partial_interrupted"}
    unknown = allowed - {"success_or_cancelled", "failed_partial_interrupted"}
    if unknown:
        raise TaskRetentionError("TASK_RETENTION_CATEGORY_INVALID", "清理类别无效。")
    clock = _normalize(now)
    sql_now = _sql_utc(clock)
    error_codes: list[str] = []
    stats: dict[str, Any] = {
        "as_of": clock,
        "scanned": 0,
        "purged": 0,
        "skipped_referenced": 0,
        "skipped_not_due": 0,
        "skipped_active": 0,
        "errors": 0,
        "error_codes": error_codes,
    }
    candidates = _eligible_ids(session, sql_now, limit=limit * 3)
    stats["scanned"] = len(candidates)
    purged = 0
    for task_id in candidates:
        if purged >= limit:
            break
        task = session.get(BackgroundTask, task_id)
        if task is None:
            continue
        group = _category(task)
        if group is None or group not in allowed:
            continue
        if not _is_due(task, sql_now):
            stats["skipped_not_due"] += 1
            continue
        if task.status in ACTIVE_STATES:
            stats["skipped_active"] += 1
            continue
        reason = _reference_block(session, task)
        if reason is not None:
            stats["skipped_referenced"] += 1
            continue
        try:
            with session.begin_nested():
                _delete_task_tree(session, task, now=sql_now)
            purged += 1
            stats["purged"] += 1
        except TaskRetentionError as exc:
            if exc.code == "TASK_STILL_REFERENCED":
                stats["skipped_referenced"] += 1
            elif exc.code == "TASK_RETENTION_RACE":
                stats["skipped_not_due"] += 1
            else:
                stats["errors"] += 1
                if exc.code not in error_codes and len(error_codes) < 8:
                    error_codes.append(exc.code)
        except Exception:
            stats["errors"] += 1
            if "TASK_RETENTION_FAILED" not in error_codes and len(error_codes) < 8:
                error_codes.append("TASK_RETENTION_FAILED")
    session.commit()
    return stats


def _normalize(value: datetime | None) -> datetime:
    clock = value or utc_now()
    if clock.tzinfo is None:
        return clock.replace(tzinfo=UTC)
    return clock.astimezone(UTC)


def _sql_utc(value: datetime | None) -> datetime:
    return _normalize(value).replace(tzinfo=None)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _terminal_at(task: BackgroundTask) -> datetime | None:
    return _as_utc(task.completed_at)


def _category(task: BackgroundTask) -> str | None:
    if task.status in SUCCESS_STATES:
        return "success_or_cancelled"
    if task.status in FAILURE_STATES:
        return "failed_partial_interrupted"
    return None


def _retention_for(task: BackgroundTask) -> timedelta | None:
    if task.status in SUCCESS_STATES:
        return SUCCESS_RETENTION
    if task.status in FAILURE_STATES:
        return FAILURE_RETENTION
    return None


def _is_due(task: BackgroundTask, now: datetime) -> bool:
    finished = _terminal_at(task)
    retention = _retention_for(task)
    if finished is None or retention is None:
        return False
    cutoff = _as_utc(now)
    if cutoff is None:
        return False
    return finished + retention <= cutoff


def _eligible_ids(session: Session, now: datetime, *, limit: int) -> list[str]:
    success_cut = now - SUCCESS_RETENTION
    failure_cut = now - FAILURE_RETENTION
    rows = session.scalars(
        select(BackgroundTask.task_id)
        .where(
            BackgroundTask.completed_at.is_not(None),
            or_(
                and_(
                    BackgroundTask.status.in_(SUCCESS_STATES),
                    BackgroundTask.completed_at <= success_cut,
                ),
                and_(
                    BackgroundTask.status.in_(FAILURE_STATES),
                    BackgroundTask.completed_at <= failure_cut,
                ),
            ),
        )
        .order_by(BackgroundTask.completed_at, BackgroundTask.task_id)
        .limit(limit)
    )
    return list(rows)


def _count_active(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(BackgroundTask)
            .where(BackgroundTask.status.in_(ACTIVE_STATES))
        )
        or 0
    )


def _count_missing_terminal_time(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(BackgroundTask)
            .where(
                BackgroundTask.status.in_(SUCCESS_STATES | FAILURE_STATES),
                BackgroundTask.completed_at.is_(None),
            )
        )
        or 0
    )


def _group_counts(session: Session, task_ids: list[str]) -> dict[str, int]:
    result = {"success_or_cancelled": 0, "failed_partial_interrupted": 0}
    if not task_ids:
        return result
    for task in session.scalars(
        select(BackgroundTask).where(BackgroundTask.task_id.in_(task_ids))
    ):
        group = _category(task)
        if group is not None:
            result[group] += 1
    return result


def _count_referenced(session: Session, task_ids: list[str]) -> set[str]:
    blocked: set[str] = set()
    for task_id in task_ids:
        task = session.get(BackgroundTask, task_id)
        if task is None:
            continue
        if _reference_block(session, task) is not None:
            blocked.add(task_id)
    return blocked


def _reference_block(session: Session, task: BackgroundTask) -> str | None:
    """Return a skip reason when the task must be retained."""
    ai_ref = session.scalar(
        select(AiOperation.operation_id)
        .where(AiOperation.task_id == task.task_id)
        .limit(1)
    )
    if ai_ref is not None:
        return "AI_OPERATION"
    child = session.scalar(
        select(BackgroundTask.task_id)
        .where(BackgroundTask.parent_task_id == task.task_id)
        .limit(1)
    )
    if child is not None:
        return "HAS_CHILD"
    if task.parent_task_id is not None:
        parent = session.get(BackgroundTask, task.parent_task_id)
        if parent is not None and parent.status in ACTIVE_STATES:
            return "ACTIVE_PARENT"
    return None


def _delete_task_tree(session: Session, task: BackgroundTask, *, now: datetime) -> None:
    reason = _reference_block(session, task)
    if reason is not None:
        raise TaskRetentionError("TASK_STILL_REFERENCED", "任务仍被业务引用，已跳过。")
    if task.status in ACTIVE_STATES or not _is_due(task, now):
        raise TaskRetentionError("TASK_RETENTION_RACE", "清理过程中任务状态已变化。")
    session.execute(delete(TaskEvent).where(TaskEvent.task_id == task.task_id))
    session.execute(delete(TaskAttempt).where(TaskAttempt.task_id == task.task_id))
    deleted = session.execute(
        delete(BackgroundTask).where(
            BackgroundTask.task_id == task.task_id,
            BackgroundTask.status.in_(SUCCESS_STATES | FAILURE_STATES),
            BackgroundTask.completed_at.is_not(None),
        )
    )
    if int(getattr(deleted, "rowcount", 0) or 0) != 1:
        raise TaskRetentionError("TASK_RETENTION_RACE", "清理过程中任务状态已变化。")
