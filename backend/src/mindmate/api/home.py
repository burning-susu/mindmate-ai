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

router = APIRouter(prefix="/api/v1")


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
