from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mindmate.api.files import get_session
from mindmate.application.conversation_history import HistoryQueryError, list_conversation_history
from mindmate.application.learning_history import list_learning_history

router = APIRouter(prefix="/api/v1")


class HistoryApiError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


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


class ConversationHistoryListResponse(BaseModel):
    items: list[ConversationHistoryItem]
    next_cursor: str | None = None


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


class LearningHistoryListResponse(BaseModel):
    items: list[LearningHistoryItem]
    next_cursor: str | None = None


@router.get(
    "/history/conversations",
    response_model=ConversationHistoryListResponse,
    tags=["history"],
)
def list_history_conversations(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        return list_conversation_history(session, limit=limit, cursor=cursor)
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
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        return list_learning_history(session, limit=limit, cursor=cursor)
    except HistoryQueryError as exc:
        raise HistoryApiError(exc.code, exc.detail, exc.status) from exc
