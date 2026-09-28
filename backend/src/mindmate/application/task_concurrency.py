"""Persistent, cross-process limits for durable background task workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from mindmate.application.provider_configuration import write_setting
from mindmate.infrastructure.models import AppSetting

TASK_CONCURRENCY_SETTING_KEY = "tasks.concurrency"
DEFAULT_HEAVY_TASK_LIMIT = 2
DEFAULT_VECTOR_WRITE_LIMIT = 1

# These are durable task types that compete for the ordinary local CPU/DISK
# budget. Interactive provider requests and backup creation are intentionally
# outside this group: they have their own lifecycle and limits.
HEAVY_TASK_TYPES = frozenset(
    {
        "FILE_IMPORT",
        "FILE_REPROCESS",
        "INDEX_PREPROCESS",
        "INDEX_CHUNK",
        "INDEX_EMBED",
        "INDEX_FTS",
        "KNOWLEDGE_MEMBERSHIP_ADD",
        "EMBEDDING_MODEL_INSTALL",
    }
)
VECTOR_WRITE_TASK_TYPES = frozenset({"INDEX_EMBED"})

ConcurrencySource = Literal["default", "stored", "invalid"]


@dataclass(frozen=True, slots=True)
class TaskConcurrencyConfig:
    heavy_task_limit: int
    vector_write_limit: int
    source: ConcurrencySource
    updated_at: datetime | None = None
    error_code: str | None = None

    def limit_for(self, group: str) -> int | None:
        if group == "HEAVY":
            return self.heavy_task_limit
        if group == "VECTOR_WRITE":
            return self.vector_write_limit
        return None


def _valid_limit(value: object, *, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= maximum


def read_task_concurrency(session: Any) -> TaskConcurrencyConfig:
    """Read the effective limit without ever increasing an invalid value.

    A missing setting uses the frozen defaults. A malformed persisted row fails
    closed to one worker per group and exposes a stable error code to the
    settings endpoint instead of silently restoring a higher limit.
    """

    row = session.get(AppSetting, TASK_CONCURRENCY_SETTING_KEY)
    if row is None:
        return TaskConcurrencyConfig(
            DEFAULT_HEAVY_TASK_LIMIT,
            DEFAULT_VECTOR_WRITE_LIMIT,
            "default",
        )
    value = row.setting_value_json
    heavy = value.get("heavy_task_limit") if isinstance(value, dict) else None
    vector = value.get("vector_write_limit") if isinstance(value, dict) else None
    if (
        isinstance(heavy, int)
        and not isinstance(heavy, bool)
        and 1 <= heavy <= DEFAULT_HEAVY_TASK_LIMIT
        and isinstance(vector, int)
        and not isinstance(vector, bool)
        and 1 <= vector <= DEFAULT_VECTOR_WRITE_LIMIT
    ):
        return TaskConcurrencyConfig(
            heavy,
            vector,
            "stored",
            row.updated_at,
        )
    return TaskConcurrencyConfig(1, 1, "invalid", row.updated_at, "TASK_CONCURRENCY_INVALID")


def validate_task_concurrency(heavy_task_limit: object, vector_write_limit: object) -> None:
    if not _valid_limit(heavy_task_limit, maximum=DEFAULT_HEAVY_TASK_LIMIT):
        raise ValueError("TASK_HEAVY_LIMIT_INVALID")
    if not _valid_limit(vector_write_limit, maximum=DEFAULT_VECTOR_WRITE_LIMIT):
        raise ValueError("TASK_VECTOR_LIMIT_INVALID")


def write_task_concurrency(
    session: Any, *, heavy_task_limit: int, vector_write_limit: int
) -> TaskConcurrencyConfig:
    validate_task_concurrency(heavy_task_limit, vector_write_limit)
    write_setting(
        session,
        TASK_CONCURRENCY_SETTING_KEY,
        {
            "heavy_task_limit": heavy_task_limit,
            "vector_write_limit": vector_write_limit,
        },
    )
    session.flush()
    return read_task_concurrency(session)


def task_concurrency_payload(config: TaskConcurrencyConfig) -> dict[str, Any]:
    return {
        "heavy_task_limit": config.heavy_task_limit,
        "vector_write_limit": config.vector_write_limit,
        "default_heavy_task_limit": DEFAULT_HEAVY_TASK_LIMIT,
        "default_vector_write_limit": DEFAULT_VECTOR_WRITE_LIMIT,
        "source": config.source,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        "error_code": config.error_code,
    }
