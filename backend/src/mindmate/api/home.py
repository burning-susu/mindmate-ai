from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindmate.api.files import get_session
from mindmate.application.home_overview import build_home_overview
from mindmate.application.task_retention import (
    TaskRetentionError,
    preview_task_retention,
    purge_expired_tasks,
)

router = APIRouter(prefix="/api/v1")


class HomeApiError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


class HomeCountScopeResponse(BaseModel):
    files: str
    knowledge_bases: str
    conversations: str
    learning_sessions: str


class HomeTaskItemResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    phase: str | None = None
    progress_percent: int | None = None
    failure_code: str | None = None
    failure_summary: str | None = None
    updated_at: datetime


class HomeTaskSummaryResponse(BaseModel):
    queued_count: int
    running_count: int
    failed_count: int
    blocked_count: int
    interrupted_count: int
    total_count: int
    latest: HomeTaskItemResponse | None = None
    recent: list[HomeTaskItemResponse]


class HomeOverviewResponse(BaseModel):
    files: int = Field(description="未回收文件数，包含解析失败。")
    knowledge_bases: int = Field(description="未回收知识库数，包含空库和索引失败。")
    conversations: int = Field(description="未回收对话数。")
    learning_sessions: int = Field(description="未回收学习会话数，包含已完成和未能出题。")
    count_scope: HomeCountScopeResponse
    tasks: HomeTaskSummaryResponse


@router.get("/home/overview", response_model=HomeOverviewResponse, tags=["home"])
def get_home_overview(
    task_limit: int = Query(default=8, ge=1, le=30),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return build_home_overview(session, task_limit=task_limit)


class TaskRetentionPreviewResponse(BaseModel):
    as_of: datetime
    eligible_total: int
    skipped_referenced: int
    success_or_cancelled: int
    failed_partial_interrupted: int
    active_not_eligible: int
    missing_completed_at: int


class TaskRetentionRunResponse(BaseModel):
    as_of: datetime
    scanned: int
    purged: int
    skipped_referenced: int
    skipped_not_due: int
    skipped_active: int
    errors: int
    error_codes: list[str]


class TaskRetentionPurgeRequest(BaseModel):
    confirmed: bool = False
    limit: int = Field(default=20, ge=1, le=100)
    clear_success: bool = True
    clear_cancelled: bool = True
    clear_failed: bool = True


@router.get(
    "/home/tasks/retention-preview",
    response_model=TaskRetentionPreviewResponse,
    tags=["home"],
)
def get_task_retention_preview(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        return preview_task_retention(session)
    except TaskRetentionError as exc:
        raise HomeApiError(exc.code, exc.detail, exc.status) from exc


@router.post(
    "/home/tasks/retention-purge",
    response_model=TaskRetentionRunResponse,
    tags=["home"],
)
def run_task_retention_purge(
    body: TaskRetentionPurgeRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if not body.confirmed:
        raise HomeApiError(
            "PURGE_CONFIRMATION_REQUIRED", "清理任务记录需要明确确认。"
        )
    categories: set[str] = set()
    if body.clear_success or body.clear_cancelled:
        categories.add("success_or_cancelled")
    if body.clear_failed:
        categories.add("failed_partial_interrupted")
    if not categories:
        raise HomeApiError(
            "TASK_RETENTION_CATEGORY_INVALID", "请至少选择一类可清理的任务记录。"
        )
    try:
        return purge_expired_tasks(session, limit=body.limit, categories=categories)
    except TaskRetentionError as exc:
        raise HomeApiError(exc.code, exc.detail, exc.status) from exc
