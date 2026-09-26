"""Read-only home counts and task projection. This module does not commit."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from mindmate.infrastructure.models import (
    BackgroundTask,
    Conversation,
    FileRecord,
    KnowledgeBase,
    LearningSession,
)

COUNT_SCOPE = {
    "files": "未回收文件，包含解析失败和其他未进回收站的状态",
    "knowledge_bases": "未回收知识库，包含空库、准备中和索引失败",
    "conversations": "未回收对话，包含普通对话和知识库对话",
    "learning_sessions": "未回收学习会话，包含未完成、已完成和未能出题",
}

_QUEUED = frozenset({"CREATED", "QUEUED"})
_RUNNING = frozenset({"RUNNING"})
_FAILED = frozenset({"FAILED"})
_BLOCKED = frozenset({"BLOCKED"})
_INTERRUPTED = frozenset({"INTERRUPTED"})
_TERMINAL_DONE = frozenset({"SUCCEEDED", "COMPLETED", "PARTIAL"})
_FAILURE_VISIBLE = frozenset({"FAILED", "INTERRUPTED"})
_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,79}")
_UNSAFE_SUMMARY = re.compile(
    r"[\\/]|sk-|api[_ -]?key|bearer\s|traceback|password|secret|token",
    re.IGNORECASE,
)


def build_home_overview(session: Session, *, task_limit: int) -> dict[str, Any]:
    with session.begin():
        session.execute(text("SELECT 1"))
        recent = [
            _task_item(task)
            for task in session.scalars(
                select(BackgroundTask)
                .order_by(BackgroundTask.updated_at.desc(), BackgroundTask.task_id.desc())
                .limit(task_limit)
            )
        ]
        return {
            "files": _active_count(session, FileRecord),
            "knowledge_bases": _active_count(session, KnowledgeBase),
            "conversations": _active_count(session, Conversation),
            "learning_sessions": _active_count(session, LearningSession),
            "count_scope": COUNT_SCOPE,
            "tasks": {
                "queued_count": _status_count(session, _QUEUED),
                "running_count": _status_count(session, _RUNNING),
                "failed_count": _status_count(session, _FAILED),
                "blocked_count": _status_count(session, _BLOCKED),
                "interrupted_count": _status_count(session, _INTERRUPTED),
                "total_count": int(
                    session.scalar(select(func.count()).select_from(BackgroundTask)) or 0
                ),
                "latest": recent[0] if recent else None,
                "recent": recent,
            },
        }


def _active_count(session: Session, model: Any) -> int:
    value = session.scalar(
        select(func.count()).select_from(model).where(model.deleted_at.is_(None))
    )
    return int(value or 0)


def _status_count(session: Session, statuses: frozenset[str]) -> int:
    value = session.scalar(
        select(func.count())
        .select_from(BackgroundTask)
        .where(BackgroundTask.status.in_(statuses))
    )
    return int(value or 0)


def _task_item(task: BackgroundTask) -> dict[str, Any]:
    failure_code, failure_summary = _failure_fields(task)
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "phase": task.phase,
        "progress_percent": _progress_percent(task),
        "failure_code": failure_code,
        "failure_summary": failure_summary,
        "updated_at": task.updated_at,
    }


def _progress_percent(task: BackgroundTask) -> int | None:
    value = task.progress
    if not isinstance(value, int) or value < 0 or value > 100:
        return None
    if not _checkpoint_has_units(task.checkpoint_json):
        return None
    if task.status == "RUNNING":
        return value
    if task.status in _TERMINAL_DONE and value == 100:
        return 100
    return None


def _checkpoint_has_units(checkpoint: Any) -> bool:
    if not isinstance(checkpoint, dict):
        return False
    ordinal = checkpoint.get("next_ordinal")
    if isinstance(ordinal, int) and ordinal > 0:
        return True
    items = checkpoint.get("items")
    results = checkpoint.get("results")
    return (
        isinstance(items, list)
        and len(items) > 0
        and isinstance(results, list)
        and len(results) > 0
    )


def _failure_fields(task: BackgroundTask) -> tuple[str | None, str | None]:
    if task.status not in _FAILURE_VISIBLE:
        return None, None
    summary = _safe_summary(task.error_summary)
    return _failure_code(task), summary or "失败详情已省略"


def _failure_code(task: BackgroundTask) -> str | None:
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    for key in ("error_id", "reason_code"):
        value = checkpoint.get(key)
        if isinstance(value, str) and _CODE.fullmatch(value):
            return value
    items = checkpoint.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("parse_error_id", "error_id"):
                value = item.get(key)
                if isinstance(value, str) and _CODE.fullmatch(value):
                    return value
    return None


def _safe_summary(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > 80 or _UNSAFE_SUMMARY.search(text):
        return None
    return text
