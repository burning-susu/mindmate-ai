from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.application.provider_configuration import (
    openai_public_cost_estimate,
    public_cost_estimate,
    read_setting,
    write_setting,
)
from mindmate.infrastructure.models import AiOperation

BUDGET_SETTING_KEY = "ai.budget.period"
BUDGET_CURRENCY = "USD"
DEFAULT_PERIOD = "30d"
_BUDGET_LOCK = RLock()


def utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _estimate_usd(input_tokens: int, output_tokens: int, rates: dict[str, Any]) -> Decimal:
    input_rate = _parse_decimal(rates.get("input_usd_per_million_tokens")) or Decimal("0")
    output_rate = _parse_decimal(rates.get("output_usd_per_million_tokens")) or Decimal("0")
    return (Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate) / Decimal(
        1_000_000
    )


def _rates_for_provider(provider: str) -> dict[str, Any] | None:
    normalized = (provider or "").strip().upper()
    if normalized in {"DEEPSEEK", "ONLINE"}:
        return public_cost_estimate()
    if normalized == "OPENAI":
        return openai_public_cost_estimate()
    return None


def _channel(provider: str) -> str:
    normalized = (provider or "").strip().upper()
    if normalized in {"DEEPSEEK", "OPENAI", "ONLINE"}:
        return "online"
    return "mock"


def summarize_usage(session: Session, *, days: int = 30) -> dict[str, Any]:
    since = utc_now() - timedelta(days=days)
    rows = session.scalars(
        select(AiOperation).where(AiOperation.created_at >= since).order_by(AiOperation.created_at)
    ).all()
    daily: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    totals = {
        "mock": _empty_bucket(),
        "online": _empty_bucket(),
    }
    by_provider: dict[str, dict[str, Any]] = {}
    deepseek_rates = public_cost_estimate()
    unknown_usage_ops = 0

    for row in rows:
        channel = _channel(row.provider)
        provider_name = (row.provider or "UNKNOWN").strip().upper() or "UNKNOWN"
        day = row.created_at.astimezone(UTC).date().isoformat()
        model = row.resolved_model or row.requested_model or "unknown"
        day_bucket = daily.setdefault(
            day,
            {"date": day, "mock": _empty_bucket(), "online": _empty_bucket()},
        )
        model_bucket = by_model.setdefault(
            f"{channel}:{provider_name}:{model}",
            {"channel": channel, "provider": provider_name, "model": model, **_empty_bucket()},
        )
        provider_bucket = by_provider.setdefault(
            provider_name, {"provider": provider_name, **_empty_bucket()}
        )
        row_rates = _rates_for_provider(row.provider)
        input_tokens = row.usage_input_tokens
        output_tokens = row.usage_output_tokens
        tracked = (totals[channel], day_bucket[channel], model_bucket, provider_bucket)
        if input_tokens is None or output_tokens is None or (channel == "online" and row_rates is None):
            unknown_usage_ops += 1
            for bucket in tracked:
                bucket["operations"] += 1
                bucket["unknown_usage_operations"] += 1
            continue
        measured_input = input_tokens
        measured_output = output_tokens
        estimated = _estimate_usd(measured_input, measured_output, row_rates or deepseek_rates)
        for bucket in tracked:
            bucket["operations"] += 1
            bucket["input_tokens"] += measured_input
            bucket["output_tokens"] += measured_output
            if row.usage_total_tokens is not None:
                bucket["total_tokens"] += int(row.usage_total_tokens)
            else:
                bucket["total_tokens"] += measured_input + measured_output
            if channel == "online" and row_rates is not None:
                bucket["estimated_usd"] = str(
                    (Decimal(bucket["estimated_usd"]) + estimated).quantize(Decimal("0.000001"))
                )
            else:
                bucket["estimated_usd"] = None

    online_estimated = totals["online"]["estimated_usd"]
    return {
        "period_days": days,
        "since": since.isoformat(),
        "until": utc_now().isoformat(),
        "currency": BUDGET_CURRENCY,
        "cost_estimate": deepseek_rates,
        "cost_estimates": {
            "deepseek": deepseek_rates,
            "openai": openai_public_cost_estimate(),
        },
        "by_provider": [
            {
                "provider": item["provider"],
                **_public_bucket(item, estimated=item["provider"] in {"DEEPSEEK", "OPENAI", "ONLINE"}),
            }
            for item in sorted(by_provider.values(), key=lambda value: value["provider"])
        ],
        "totals": {
            "mock": _public_bucket(totals["mock"], estimated=False),
            "online": _public_bucket(totals["online"], estimated=True),
        },
        "daily": [
            {
                "date": item["date"],
                "mock": _public_bucket(item["mock"], estimated=False),
                "online": _public_bucket(item["online"], estimated=True),
            }
            for item in sorted(daily.values(), key=lambda value: value["date"])
        ],
        "by_model": [
            {
                "channel": item["channel"],
                "model": item["model"],
                **_public_bucket(item, estimated=item["channel"] == "online"),
            }
            for item in sorted(by_model.values(), key=lambda value: (value["channel"], value["model"]))
        ],
        "online_actual_usage_available": totals["online"]["operations"] > 0
        and totals["online"]["unknown_usage_operations"] < totals["online"]["operations"],
        "online_actual_usage_message": (
            None
            if totals["online"]["operations"] > 0
            else "在线实际用量暂无记录（当前未产生 DeepSeek 或 OpenAI 调用，或仅使用 Mock）。"
        ),
        "unknown_usage_operations": unknown_usage_ops,
        "estimated_online_usd": online_estimated,
        "estimate_disclaimer": deepseek_rates["disclaimer"],
    }


def _empty_bucket() -> dict[str, Any]:
    return {
        "operations": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "unknown_usage_operations": 0,
        "estimated_usd": "0",
    }


def _public_bucket(bucket: dict[str, Any], *, estimated: bool) -> dict[str, Any]:
    return {
        "operations": bucket["operations"],
        "input_tokens": bucket["input_tokens"],
        "output_tokens": bucket["output_tokens"],
        "total_tokens": bucket["total_tokens"],
        "unknown_usage_operations": bucket["unknown_usage_operations"],
        "estimated_usd": bucket["estimated_usd"] if estimated else None,
        "usage_complete": bucket["unknown_usage_operations"] == 0,
    }


def default_budget() -> dict[str, Any]:
    return {
        "enabled": False,
        "currency": BUDGET_CURRENCY,
        "period": DEFAULT_PERIOD,
        "hard_stop_usd": None,
        "soft_remind_usd": None,
        "unknown_usage_policy": "deny",
        "updated_at": None,
    }


def read_budget(session: Session) -> dict[str, Any]:
    stored = read_setting(session, BUDGET_SETTING_KEY) or {}
    base = default_budget()
    enabled = bool(stored.get("enabled")) if "enabled" in stored else False
    hard_stop = _parse_decimal(stored.get("hard_stop_usd"))
    soft_remind = _parse_decimal(stored.get("soft_remind_usd"))
    policy = stored.get("unknown_usage_policy")
    if policy not in {"deny", "confirm"}:
        policy = "deny"
    period = stored.get("period") if stored.get("period") in {DEFAULT_PERIOD, "calendar_month"} else DEFAULT_PERIOD
    return {
        **base,
        "enabled": enabled,
        "period": period,
        "hard_stop_usd": str(hard_stop) if hard_stop is not None else None,
        "soft_remind_usd": str(soft_remind) if soft_remind is not None else None,
        "unknown_usage_policy": policy,
        "updated_at": stored.get("updated_at") if isinstance(stored.get("updated_at"), str) else None,
    }


def set_budget(
    session: Session,
    *,
    enabled: bool,
    hard_stop_usd: str | None,
    soft_remind_usd: str | None = None,
    period: str = DEFAULT_PERIOD,
    unknown_usage_policy: str = "deny",
) -> dict[str, Any]:
    if period not in {DEFAULT_PERIOD, "calendar_month"}:
        raise ValueError("BUDGET_PERIOD_UNSUPPORTED")
    if unknown_usage_policy not in {"deny", "confirm"}:
        raise ValueError("BUDGET_POLICY_UNSUPPORTED")
    hard_stop = _parse_decimal(hard_stop_usd)
    soft_remind = _parse_decimal(soft_remind_usd)
    if enabled and hard_stop is None:
        raise ValueError("BUDGET_HARD_STOP_REQUIRED")
    if soft_remind is not None and hard_stop is not None and soft_remind > hard_stop:
        raise ValueError("BUDGET_SOFT_ABOVE_HARD")
    payload = {
        "enabled": enabled,
        "currency": BUDGET_CURRENCY,
        "period": period,
        "hard_stop_usd": str(hard_stop) if hard_stop is not None else None,
        "soft_remind_usd": str(soft_remind) if soft_remind is not None else None,
        "unknown_usage_policy": unknown_usage_policy,
        "updated_at": utc_now().isoformat(),
    }
    write_setting(session, BUDGET_SETTING_KEY, payload)
    session.commit()
    return read_budget(session)


def budget_status(session: Session) -> dict[str, Any]:
    budget = read_budget(session)
    usage = summarize_usage(session, days=30)
    spent_raw = usage.get("estimated_online_usd")
    spent = _parse_decimal(spent_raw) or Decimal("0")
    hard_stop = _parse_decimal(budget.get("hard_stop_usd"))
    remaining = None
    if hard_stop is not None:
        remaining = str((hard_stop - spent).quantize(Decimal("0.000001")))
    soft_remind = _parse_decimal(budget.get("soft_remind_usd"))
    soft_triggered = bool(
        budget["enabled"] and soft_remind is not None and spent >= soft_remind
    )
    return {
        "budget": budget,
        "usage_summary": {
            "estimated_online_usd": spent_raw,
            "unknown_usage_operations": usage["unknown_usage_operations"],
            "online_operations": usage["totals"]["online"]["operations"],
            "online_usage_complete": usage["totals"]["online"]["usage_complete"],
            "online_actual_usage_message": usage["online_actual_usage_message"],
        },
        "spent_estimated_usd": str(spent.quantize(Decimal("0.000001"))),
        "remaining_estimated_usd": remaining,
        "soft_remind_triggered": soft_triggered,
        "hard_stop_would_block": bool(
            budget["enabled"]
            and hard_stop is not None
            and (
                spent >= hard_stop
                or (
                    not usage["totals"]["online"]["usage_complete"]
                    and budget["unknown_usage_policy"] == "deny"
                    and usage["unknown_usage_operations"] > 0
                )
            )
        ),
        "currency": BUDGET_CURRENCY,
        "estimate_disclaimer": usage["estimate_disclaimer"],
    }


def assert_external_budget_allows(
    session: Session,
    *,
    estimated_request_usd: Decimal | None = None,
    confirm_unknown_usage: bool = False,
) -> dict[str, Any]:
    """Refuse external Provider calls when the hard stop would be exceeded.

    Concurrent callers serialize on `_BUDGET_LOCK` so two requests cannot both
    pass the same remaining allowance.
    """

    with _BUDGET_LOCK:
        status = budget_status(session)
        budget = status["budget"]
        if not budget["enabled"]:
            return {"allowed": True, "status": status}
        hard_stop = _parse_decimal(budget.get("hard_stop_usd"))
        if hard_stop is None:
            return {"allowed": True, "status": status}
        spent = _parse_decimal(status["spent_estimated_usd"]) or Decimal("0")
        unknown_ops = int(status["usage_summary"]["unknown_usage_operations"])
        if unknown_ops > 0 and budget["unknown_usage_policy"] == "deny":
            raise BudgetRejected(
                "BUDGET_USAGE_UNTRUSTED",
                "周期用量存在未知 usage，硬限额按保守策略拒绝外发。",
            )
        if unknown_ops > 0 and budget["unknown_usage_policy"] == "confirm" and not confirm_unknown_usage:
            raise BudgetRejected(
                "BUDGET_UNKNOWN_USAGE_CONFIRM_REQUIRED",
                "周期用量存在未知 usage，需要明确确认后才能继续外发。",
            )
        projected = spent + (estimated_request_usd or Decimal("0"))
        if projected > hard_stop:
            raise BudgetRejected(
                "BUDGET_HARD_STOP_REACHED",
                "已达到或将超过本周期硬停止阈值，未发起外部 Provider 请求。",
            )
        return {"allowed": True, "status": status}


class BudgetRejected(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def privacy_diagnostics_status() -> dict[str, Any]:
    return {
        "log_retention": {
            "available": False,
            "message": "日志保留与清理服务尚未验收，当前仅展示说明。",
        },
        "diagnostics_export": {
            "available": False,
            "message": "诊断包导出尚未提供；不会返回文档全文、Prompt 或 Key。",
        },
        "storage_migration": {
            "available": False,
            "message": "存储迁移尚未实现，请继续使用当前本机数据目录。",
        },
        "secrets_policy": {
            "api_key_in_sqlite": False,
            "api_key_in_backup": False,
            "message": "API Key 仅存于系统凭据；失效时需重新配置，不会自动重试在线请求。",
        },
    }


__all__ = [
    "BUDGET_SETTING_KEY",
    "BudgetRejected",
    "assert_external_budget_allows",
    "budget_status",
    "privacy_diagnostics_status",
    "read_budget",
    "set_budget",
    "summarize_usage",
]
