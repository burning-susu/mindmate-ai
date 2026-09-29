from __future__ import annotations

# ruff: noqa: B008
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mindmate.api.files import get_session
from mindmate.application.diagnostic_log_retention import (
    DiagnosticLogError,
    clear_diagnostic_logs,
    inspect_log_retention,
)
from mindmate.application.diagnostics import (
    build_diagnostics_document,
    diagnostics_preview,
    serialize_diagnostics,
)
from mindmate.application.storage_stats import storage_overview
from mindmate.application.task_concurrency import (
    DEFAULT_HEAVY_TASK_LIMIT,
    DEFAULT_VECTOR_WRITE_LIMIT,
    read_task_concurrency,
    task_concurrency_payload,
    write_task_concurrency,
)
from mindmate.application.usage_budget import (
    budget_status,
    privacy_diagnostics_status,
    read_budget,
    set_budget,
    summarize_usage,
)
from mindmate.config import Settings
from mindmate.security.session import SESSION_COOKIE

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


class TaskConcurrencyResponse(BaseModel):
    heavy_task_limit: int
    vector_write_limit: int
    default_heavy_task_limit: int
    default_vector_write_limit: int
    source: Literal["default", "stored", "invalid"]
    updated_at: str | None = None
    error_code: str | None = None


class TaskConcurrencyUpdateRequest(BaseModel):
    heavy_task_limit: int = Field(default=DEFAULT_HEAVY_TASK_LIMIT, ge=1, le=DEFAULT_HEAVY_TASK_LIMIT)
    vector_write_limit: int = Field(
        default=DEFAULT_VECTOR_WRITE_LIMIT, ge=1, le=DEFAULT_VECTOR_WRITE_LIMIT
    )


class DiagnosticLogClearResponse(BaseModel):
    files_removed: int
    bytes_removed: int
    remaining_files: int
    remaining_bytes: int
    complete: bool


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _require_local_session(request: Request) -> None:
    local = getattr(request.app.state, "session", None)
    if local is None or not local.matches(request.cookies.get(SESSION_COOKIE)):
        raise SystemSettingsApiError(
            "LOCAL_SESSION_REQUIRED",
            "请从当前 MindMate 应用页面重新建立本地会话。",
            401,
        )


@router.get("/storage", response_model=StorageOverviewResponse)
def get_storage_overview(request: Request) -> dict[str, Any]:
    return storage_overview(_settings(request))


@router.get("/ai-usage")
def get_ai_usage(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    budget = read_budget(session)
    try:
        return summarize_usage(
            session,
            period=budget["period"],
            start=start,
            end=end,
            include_active_reservations=start is None and end is None,
        )
    except ValueError as exc:
        raise SystemSettingsApiError(
            str(exc), "用量查询窗口无效，请提供正确的 UTC 起止时间。", 400
        ) from exc


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


@router.get("/task-concurrency", response_model=TaskConcurrencyResponse)
def get_task_concurrency(session: Session = Depends(get_session)) -> dict[str, Any]:
    return task_concurrency_payload(read_task_concurrency(session))


@router.put("/task-concurrency", response_model=TaskConcurrencyResponse)
def put_task_concurrency(
    payload: TaskConcurrencyUpdateRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        config = write_task_concurrency(
            session,
            heavy_task_limit=payload.heavy_task_limit,
            vector_write_limit=payload.vector_write_limit,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise SystemSettingsApiError(
            str(exc), "任务并发配置无效，只能在默认上限内下调。", 400
        ) from exc
    return task_concurrency_payload(config)


@router.get("/privacy")
def get_privacy_status(request: Request) -> dict[str, Any]:
    result = privacy_diagnostics_status()
    retention = inspect_log_retention(_settings(request))
    if retention.available:
        state = (
            f"当前 {retention.file_count} 个文件 / {retention.bytes_used} 字节"
            if retention.cleanup_complete
            else f"有文件暂未清理；当前 {retention.file_count} 个文件 / {retention.bytes_used} 字节"
        )
        message = (
            "仅应用保存的结构化诊断事件：最多保留 30 天或 100 MiB（先达到者清理）；"
            f"后台服务 stdout/stderr 直出当前终端，不落盘；手动命令输出和 Windows 系统日志不在应用清理范围。{state}。"
        )
    else:
        message = "应用诊断日志目录暂不可安全访问，未提供清理操作。"
    result["log_retention"] = {
        "available": retention.available,
        "message": message,
        "retention_days": retention.retention_days,
        "max_bytes": retention.max_bytes,
        "file_count": retention.file_count,
        "bytes_used": retention.bytes_used,
        "cleanup_complete": retention.cleanup_complete,
    }
    return result


@router.post("/diagnostics/logs/clear", response_model=DiagnosticLogClearResponse)
def clear_local_diagnostic_logs(
    request: Request,
) -> DiagnosticLogClearResponse:
    _require_local_session(request)
    try:
        result = clear_diagnostic_logs(_settings(request))
    except DiagnosticLogError as exc:
        if exc.code == "LOG_DIRECTORY_UNSAFE":
            detail = "诊断日志目录结构异常，为保护应用外数据，本次未执行清理。"
        elif exc.code == "LOG_LOCK_UNAVAILABLE":
            detail = "诊断日志正在使用或暂不可访问，请稍后重试。"
        else:
            detail = "诊断日志暂时无法清理，请稍后重试。"
        raise SystemSettingsApiError("LOG_CLEANUP_FAILED", detail, 503, retryable=True) from exc
    except OSError as exc:
        raise SystemSettingsApiError(
            "LOG_CLEANUP_FAILED",
            "诊断日志暂时无法清理，请稍后重试。",
            503,
            retryable=True,
        ) from exc
    return DiagnosticLogClearResponse(
        files_removed=result.files_removed,
        bytes_removed=result.bytes_removed,
        remaining_files=result.remaining_files,
        remaining_bytes=result.remaining_bytes,
        complete=result.complete,
    )


@router.get("/diagnostics/preview")
def get_diagnostics_preview(
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_local_session(request)
    try:
        document = build_diagnostics_document(session, _settings(request))
        return diagnostics_preview(document)
    except Exception as exc:  # noqa: BLE001 - never expose private diagnostics errors
        raise SystemSettingsApiError(
            "DIAGNOSTICS_BUILD_FAILED",
            "诊断预览暂时无法生成，请重试。",
            503,
            retryable=True,
        ) from exc


@router.get("/diagnostics/export")
def export_diagnostics(request: Request, session: Session = Depends(get_session)) -> Response:
    _require_local_session(request)
    try:
        document = build_diagnostics_document(session, _settings(request))
        content = serialize_diagnostics(document)
    except Exception as exc:  # noqa: BLE001 - no partial file is created
        raise SystemSettingsApiError(
            "DIAGNOSTICS_BUILD_FAILED",
            "诊断包生成失败，未创建文件，请重试。",
            503,
            retryable=True,
        ) from exc
    generated_at = str(document["generated_at"]).replace(":", "").replace("-", "")[:15]
    response = Response(content=content, media_type="application/json")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="mindmate-diagnostics-{generated_at}.json"'
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def _budget_error_detail(code: str) -> str:
    mapping = {
        "BUDGET_PERIOD_UNSUPPORTED": "不支持的预算周期。",
        "BUDGET_POLICY_UNSUPPORTED": "不支持的未知用量策略。",
        "BUDGET_HARD_STOP_REQUIRED": "启用硬停止前必须设置有效的阈值金额。",
        "BUDGET_SOFT_ABOVE_HARD": "软提醒阈值不能高于硬停止阈值。",
    }
    return mapping.get(code, "预算配置无效。")


__all__ = ["SystemSettingsApiError", "router"]
