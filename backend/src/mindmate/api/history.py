from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindmate.api.files import get_session
from mindmate.application.conversation_history import (
    HistoryQueryError,
    list_conversation_history,
    list_trashed_conversations,
)
from mindmate.application.learning_history import (
    list_learning_history,
    list_trashed_learning_sessions,
)

router = APIRouter(prefix="/api/v1")


class HistoryApiError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


class HistoryLocation(BaseModel):
    section: str
    snippet: str
    record_id: str | None = None


class ConversationHistoryItem(BaseModel):
    conversation_id: str
    title: str
    summary: str
    current_mode: str
    scope_name: str | None
    status: str
    source_status: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    row_version: int
    locations: list[HistoryLocation] = Field(default_factory=list)


class ConversationHistoryListResponse(BaseModel):
    items: list[ConversationHistoryItem]
    next_cursor: str | None = None
    search_index_status: str = "PENDING"
    search_truncated: bool = False


class LearningHistoryItem(BaseModel):
    learning_session_id: str
    topic: str
    goal_type: str
    scope_name: str | None
    scope_file_count: int
    status: str
    source_status: str
    answered_count: int
    target_question_count: int
    created_at: datetime
    updated_at: datetime
    row_version: int
    locations: list[HistoryLocation] = Field(default_factory=list)


class LearningHistoryListResponse(BaseModel):
    items: list[LearningHistoryItem]
    next_cursor: str | None = None
    search_index_status: str = "PENDING"
    search_truncated: bool = False


class HistoryTrashItem(BaseModel):
    object_type: str
    object_id: str
    title: str
    deleted_at: datetime
    row_version: int


class HistoryTrashResponse(BaseModel):
    items: list[HistoryTrashItem]
    next_cursor: str | None = None


_CONVERSATION_MODES = {"GENERAL_CHAT", "KNOWLEDGE_CHAT"}
_CONVERSATION_STATUSES = {"ACTIVE", "INTERRUPTED", "SOURCE_INVALID"}
_CONVERSATION_SOURCES = {
    "NOT_APPLICABLE",
    "AVAILABLE",
    "SOURCE_DELETED",
    "SOURCE_IN_TRASH",
    "INDEX_VERSION_RETIRED",
    "PARTIAL_SOURCE",
    "SOURCE_OUT_OF_SCOPE",
}
_LEARNING_STATUSES = {"PREPARING", "IN_PROGRESS", "FAILED", "SOURCE_INVALID"}
_LEARNING_SOURCES = {
    "AVAILABLE",
    "SOURCE_DELETED",
    "SOURCE_IN_TRASH",
    "INDEX_VERSION_RETIRED",
    "PARTIAL_SOURCE",
    "SOURCE_OUT_OF_SCOPE",
    "SOURCE_VERSION_STALE",
}


def _choice(value: str | None, allowed: set[str], label: str) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise HistoryQueryError("HISTORY_QUERY_INVALID", f"{label}不是当前可筛选的值。")
    return value


def _goal_type(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if len(value) > 40 or not value.replace("_", "").isalnum() or not value.isupper():
        raise HistoryQueryError("HISTORY_QUERY_INVALID", "学习目标类型不是当前可筛选的值。")
    return value


def _date_window(date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
    start = _parse_day(date_from, "开始日期")
    end = _parse_day(date_to, "结束日期")
    if start is not None and end is not None and start > end:
        raise HistoryQueryError("HISTORY_QUERY_INVALID", "开始日期不能晚于结束日期。")
    before = end + timedelta(days=1) if end is not None else None
    return start, before


def _parse_day(value: str | None, label: str) -> datetime | None:
    if value is None or value == "":
        return None
    if len(value) != 10:
        raise HistoryQueryError("HISTORY_QUERY_INVALID", f"{label}需要使用 YYYY-MM-DD。")
    try:
        parsed = datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        raise HistoryQueryError("HISTORY_QUERY_INVALID", f"{label}无效。") from None
    return parsed


@router.get(
    "/history/conversations",
    response_model=ConversationHistoryListResponse,
    tags=["history"],
)
def list_history_conversations(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    q: str | None = Query(default=None, max_length=200),
    mode: str | None = Query(default=None, max_length=30),
    status: str | None = Query(default=None, max_length=40),
    source_status: str | None = Query(default=None, max_length=40),
    date_from: str | None = Query(default=None, max_length=10),
    date_to: str | None = Query(default=None, max_length=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        active_from, active_before = _date_window(date_from, date_to)
        return list_conversation_history(
            session,
            limit=limit,
            cursor=cursor,
            q=q,
            mode=_choice(mode, _CONVERSATION_MODES, "对话模式"),
            status=_choice(status, _CONVERSATION_STATUSES, "对话状态"),
            source_status=_choice(source_status, _CONVERSATION_SOURCES, "来源状态"),
            active_from=active_from,
            active_before=active_before,
        )
    except HistoryQueryError as exc:
        raise HistoryApiError(exc.code, exc.detail, exc.status) from exc


@router.get(
    "/history/learning-sessions",
    response_model=LearningHistoryListResponse,
    tags=["history"],
)
def list_history_learning_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    q: str | None = Query(default=None, max_length=200),
    goal_type: str | None = Query(default=None, max_length=40),
    status: str | None = Query(default=None, max_length=40),
    source_status: str | None = Query(default=None, max_length=40),
    date_from: str | None = Query(default=None, max_length=10),
    date_to: str | None = Query(default=None, max_length=10),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        active_from, active_before = _date_window(date_from, date_to)
        return list_learning_history(
            session,
            limit=limit,
            cursor=cursor,
            q=q,
            goal_type=_goal_type(goal_type),
            status=_choice(status, _LEARNING_STATUSES, "学习状态"),
            source_status=_choice(source_status, _LEARNING_SOURCES, "来源状态"),
            active_from=active_from,
            active_before=active_before,
        )
    except HistoryQueryError as exc:
        raise HistoryApiError(exc.code, exc.detail, exc.status) from exc


@router.get("/history/trash", response_model=HistoryTrashResponse, tags=["history"])
def list_history_trash(
    object_type: str = Query(min_length=1, max_length=40),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        if object_type == "conversation":
            return list_trashed_conversations(session, limit=limit, cursor=cursor)
        if object_type == "learning_session":
            return list_trashed_learning_sessions(session, limit=limit, cursor=cursor)
        raise HistoryQueryError("HISTORY_QUERY_INVALID", "回收站类型不是当前可查看的历史对象。")
    except HistoryQueryError as exc:
        raise HistoryApiError(exc.code, exc.detail, exc.status) from exc
