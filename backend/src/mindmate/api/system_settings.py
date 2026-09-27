from __future__ import annotations

# ruff: noqa: B008
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindmate.api.files import get_session
from mindmate.application.storage_stats import storage_overview
from mindmate.application.usage_budget import (
    budget_status,
    privacy_diagnostics_status,
    set_budget,
    summarize_usage,
)
from mindmate.config import Settings

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class SystemSettingsApiError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400, retryable: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status_code
        self.retryable = retryable


class StorageCategoryResponse(BaseModel):
    key: str
    label: str
    byte_size: int | None = None
    available: bool
    message: str | None = None


class StorageOverviewResponse(BaseModel):
    data_dir_configured: bool
    data_dir_display: str
    database: str
    writable: bool
    categories: list[StorageCategoryResponse]
    total_byte_size: int | None = None
    readable: bool
    message: str | None = None


class UsageBucketResponse(BaseModel):
    operations: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    unknown_usage_operations: int
    estimated_usd: str | None = None
    usage_complete: bool


class BudgetConfigResponse(BaseModel):
    enabled: bool
    currency: str
    period: str
    hard_stop_usd: str | None = None
    soft_remind_usd: str | None = None
    unknown_usage_policy: Literal["deny", "confirm"]
    updated_at: str | None = None


class BudgetUpdateRequest(BaseModel):
    enabled: bool = False
    hard_stop_usd: str | None = Field(default=None, max_length=32)
    soft_remind_usd: str | None = Field(default=None, max_length=32)
    period: Literal["30d", "calendar_month"] = "30d"
    unknown_usage_policy: Literal["deny", "confirm"] = "deny"


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/storage", response_model=StorageOverviewResponse)
def get_storage_overview(request: Request) -> dict[str, Any]:
    return storage_overview(_settings(request))


@router.get("/ai-usage")
def get_ai_usage(session: Session = Depends(get_session)) -> dict[str, Any]:
    return summarize_usage(session, days=30)


@router.get("/ai-budget")
def get_ai_budget(session: Session = Depends(get_session)) -> dict[str, Any]:
    return budget_status(session)


@router.put("/ai-budget")
def put_ai_budget(
    payload: BudgetUpdateRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        set_budget(
            session,
            enabled=payload.enabled,
            hard_stop_usd=payload.hard_stop_usd,
            soft_remind_usd=payload.soft_remind_usd,
            period=payload.period,
            unknown_usage_policy=payload.unknown_usage_policy,
        )
    except ValueError as exc:
        code = str(exc)
        raise SystemSettingsApiError(code, _budget_error_detail(code), 400) from exc
    return budget_status(session)


@router.get("/privacy")
def get_privacy_status() -> dict[str, Any]:
    return privacy_diagnostics_status()


def _budget_error_detail(code: str) -> str:
    mapping = {
        "BUDGET_PERIOD_UNSUPPORTED": "不支持的预算周期。",
        "BUDGET_POLICY_UNSUPPORTED": "不支持的未知用量策略。",
        "BUDGET_HARD_STOP_REQUIRED": "启用硬停止前必须设置有效的阈值金额。",
        "BUDGET_SOFT_ABOVE_HARD": "软提醒阈值不能高于硬停止阈值。",
    }
    return mapping.get(code, "预算配置无效。")


__all__ = ["SystemSettingsApiError", "router"]
