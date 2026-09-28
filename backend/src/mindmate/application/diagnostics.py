"""Build a bounded, local-only diagnostic projection.

The projection intentionally does not read raw logs, content objects, messages,
prompts, provider responses, credentials, or task checkpoints.  Preview and
export both consume this module so the user sees exactly what can be exported.
"""

from __future__ import annotations

import json
import os
import platform
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mindmate import __version__
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask

DIAGNOSTICS_SCHEMA_VERSION = "mindmate-diagnostics.v1"
MAX_RECENT_TASKS = 50
_ERROR_CODE = re.compile(r"^([A-Z][A-Z0-9_]{2,79})(?:$|[\s:])")
_SAFE_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")

INCLUDED_CATEGORIES = [
    "应用版本与平台运行状态",
    "非秘密 Provider/模型配置状态",
    "本地数据库可读写状态",
    "有限任务类型、状态、阶段、时间、进度",
    "脱敏错误码、诊断 ID 与计数",
]
EXCLUDED_CATEGORIES = [
    "原始日志、数据库快照、备份、文件与解析正文",
    "用户问题、回答、Prompt、模型原始响应和个人学习答案",
    "Key、Authorization、Cookie、本地会话令牌和完整路径",
    "Chunk、向量、Embedding、模型缓存和 HTTP 原始请求",
]


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_error_code(value: str | None) -> str | None:
    """Keep only a conservative machine-like prefix; never export the detail."""

    if not value:
        return None
    match = _ERROR_CODE.match(value.strip())
    return match.group(1) if match else "TASK_FAILED"


def _safe_model(value: str | None) -> str:
    if value and _SAFE_MODEL.fullmatch(value):
        return value
    return "configured"


def _directory_writable(path: Any) -> bool:
    try:
        return bool(path.is_dir() and os.access(path, os.W_OK))
    except OSError:
        return False


def build_diagnostics_projection(session: Session, settings: Settings) -> dict[str, Any]:
    """Return the single allow-listed object shared by preview and export."""

    total_tasks = int(session.scalar(select(func.count()).select_from(BackgroundTask)) or 0)
    status_counts = {
        str(status): int(count)
        for status, count in session.execute(
            select(BackgroundTask.status, func.count()).group_by(BackgroundTask.status)
        ).all()
    }
    created_range = session.execute(
        select(
            func.min(BackgroundTask.created_at),
            func.max(func.coalesce(BackgroundTask.completed_at, BackgroundTask.updated_at)),
        )
    ).one()
    recent_tasks = list(
        session.scalars(
            select(BackgroundTask)
            .order_by(BackgroundTask.created_at.desc(), BackgroundTask.task_id.desc())
            .limit(MAX_RECENT_TASKS)
        ).all()
    )

    task_items = [
        {
            "diagnostic_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "phase": task.phase,
            "progress": task.progress,
            "created_at": _iso(task.created_at),
            "started_at": _iso(task.started_at),
            "completed_at": _iso(task.completed_at),
            "error_code": _safe_error_code(task.error_summary),
        }
        for task in recent_tasks
    ]
    provider_mode = str(settings.provider_mode or "mock").strip().lower()
    if provider_mode not in {"mock", "deepseek", "openai"}:
        provider_mode = "unknown"
    data_dir = settings.resolved_data_dir
    database = settings.database_path

    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "included_categories": INCLUDED_CATEGORIES,
        "excluded_categories": EXCLUDED_CATEGORIES,
        "application": {
            "version": __version__,
            "runtime": "local",
            "platform": platform.system() or "unknown",
            "platform_release": platform.release() or "unknown",
            "architecture": platform.machine() or "unknown",
            "python_version": platform.python_version(),
        },
        "configuration": {
            "provider_mode": provider_mode,
            "provider_model": _safe_model(settings.provider_model),
            "data_directory_configured": settings.data_dir is not None,
        },
        "storage": {
            "database": "sqlite",
            "database_present": database.is_file(),
            "database_readable": bool(database.is_file() and os.access(database, os.R_OK)),
            "data_directory_writable": _directory_writable(data_dir),
        },
        "tasks": {
            "total_count": total_tasks,
            "status_counts": status_counts,
            "recent_count": len(task_items),
            "truncated": total_tasks > len(task_items),
            "time_range": {
                "from": _iso(created_range[0]),
                "to": _iso(created_range[1]),
            },
            "items": task_items,
        },
        "privacy": {
            "local_only": True,
            "auto_upload": False,
            "notice": "保存在本机，不自动上传。",
        },
    }


def build_diagnostics_document(
    session: Session, settings: Settings, *, generated_at: datetime | None = None
) -> dict[str, Any]:
    projection = build_diagnostics_projection(session, settings)
    captured = generated_at or datetime.now(UTC)
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "generated_at": _iso(captured),
        "projection": projection,
    }


def serialize_diagnostics(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def diagnostics_preview(document: dict[str, Any]) -> dict[str, Any]:
    payload = serialize_diagnostics(document)
    projection = document["projection"]
    return {
        "schema_version": document["schema_version"],
        "generated_at": document["generated_at"],
        "estimated_size_bytes": len(payload),
        "included_categories": projection["included_categories"],
        "excluded_categories": projection["excluded_categories"],
        "time_range": projection["tasks"]["time_range"],
        "task_summary": {
            "total_count": projection["tasks"]["total_count"],
            "recent_count": projection["tasks"]["recent_count"],
            "truncated": projection["tasks"]["truncated"],
            "status_counts": projection["tasks"]["status_counts"],
        },
        "projection": projection,
    }


__all__ = [
    "DIAGNOSTICS_SCHEMA_VERSION",
    "diagnostics_preview",
    "build_diagnostics_document",
    "build_diagnostics_projection",
    "serialize_diagnostics",
]
