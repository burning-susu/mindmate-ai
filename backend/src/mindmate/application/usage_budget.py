from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from mindmate.application.provider_configuration import (
    openai_public_cost_estimate,
    public_cost_estimate,
    read_setting,
    write_setting,
)
from mindmate.infrastructure.models import AiOperation, LearningProviderOperation, Message

BUDGET_SETTING_KEY = "ai.budget.period"
BUDGET_CURRENCY = "USD"
DEFAULT_PERIOD = "30d"
_MONEY_QUANTUM = Decimal("0.000001")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY_QUANTUM))


def _estimate_usd(input_tokens: int, output_tokens: int, rates: dict[str, Any]) -> Decimal | None:
    input_rate = _parse_decimal(rates.get("input_usd_per_million_tokens"))
    output_rate = _parse_decimal(rates.get("output_usd_per_million_tokens"))
    if input_rate is None or output_rate is None:
        return None
    return (
        Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)


def _price_snapshot(provider: str, model: str) -> dict[str, Any] | None:
    rates = _rates_for_provider(provider)
    if rates is None:
        return None
    return {
        "provider": provider.upper(),
        "model": model,
        "checked_on": rates.get("checked_on"),
        "pricing_url": rates.get("pricing_url"),
        "input_usd_per_million_tokens": rates.get("input_usd_per_million_tokens"),
        "output_usd_per_million_tokens": rates.get("output_usd_per_million_tokens"),
        "rate_assumption": rates.get("rate_assumption"),
    }


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


def _request_stage(row: Any) -> str:
    return str(getattr(row, "request_stage", None) or "UNKNOWN").upper()


def _row_category(row: Any, chat_mode: str | None = None) -> str:
    if isinstance(row, LearningProviderOperation):
        return "LEARNING_FEEDBACK" if "FEEDBACK" in row.task_type.upper() else "LEARNING_QUESTION"
    return "RAG" if (chat_mode or "").upper() in {"KNOWLEDGE_CHAT", "KNOWLEDGE_BASE_CHAT"} else "CHAT"


def _activity_time(row: Any) -> datetime:
    return _as_utc(row.request_sent_at or row.reserved_at or row.created_at)


def _empty_bucket() -> dict[str, Any]:
    return {
        "operations": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "unknown_usage_operations": 0,
        "unknown_price_operations": 0,
        "estimated_usd": Decimal("0"),
        "reserved_estimated_usd": Decimal("0"),
        "unknown_exposure_estimated_usd": Decimal("0"),
    }


def _snapshot_cost(row: Any, input_tokens: int, output_tokens: int) -> Decimal | None:
    snapshot = row.price_snapshot_json
    if not isinstance(snapshot, dict):
        return None
    return _estimate_usd(input_tokens, output_tokens, snapshot)


def _add_row(bucket: dict[str, Any], row: Any, *, online: bool) -> None:
    bucket["operations"] += 1
    input_tokens = row.usage_input_tokens
    output_tokens = row.usage_output_tokens
    total_tokens = row.usage_total_tokens
    if input_tokens is not None:
        bucket["input_tokens"] += int(input_tokens)
    if output_tokens is not None:
        bucket["output_tokens"] += int(output_tokens)
    if total_tokens is not None:
        bucket["total_tokens"] += int(total_tokens)
    elif input_tokens is not None and output_tokens is not None:
        bucket["total_tokens"] += int(input_tokens) + int(output_tokens)

    complete_usage = input_tokens is not None and output_tokens is not None
    if not online:
        if not complete_usage:
            bucket["unknown_usage_operations"] += 1
        return

    reserved = _parse_decimal(row.reserved_estimate_usd) or Decimal("0")
    stage = _request_stage(row)
    if input_tokens is not None and output_tokens is not None:
        estimate = _snapshot_cost(row, int(input_tokens), int(output_tokens))
        if estimate is None:
            bucket["unknown_usage_operations"] += 1
            bucket["unknown_price_operations"] += 1
            bucket["unknown_exposure_estimated_usd"] += reserved
        else:
            bucket["estimated_usd"] += estimate
        return

    if stage == "RESERVED":
        bucket["reserved_estimated_usd"] += reserved
        if _snapshot_cost(row, 0, 0) is None:
            bucket["unknown_usage_operations"] += 1
            bucket["unknown_price_operations"] += 1
    elif stage in {"POSSIBLY_SENT", "UNKNOWN"}:
        bucket["unknown_usage_operations"] += 1
        bucket["unknown_exposure_estimated_usd"] += reserved
    elif stage not in {"NOT_SENT", "RELEASED", "USAGE_KNOWN"}:
        bucket["unknown_usage_operations"] += 1
        bucket["unknown_exposure_estimated_usd"] += reserved


def _public_bucket(bucket: dict[str, Any], *, estimated: bool) -> dict[str, Any]:
    return {
        "operations": bucket["operations"],
        "input_tokens": bucket["input_tokens"],
        "output_tokens": bucket["output_tokens"],
        "total_tokens": bucket["total_tokens"],
        "unknown_usage_operations": bucket["unknown_usage_operations"],
        "unknown_price_operations": bucket["unknown_price_operations"],
        "estimated_usd": _money(bucket["estimated_usd"]) if estimated else None,
        "reserved_estimated_usd": _money(bucket["reserved_estimated_usd"]),
        "unknown_exposure_estimated_usd": _money(bucket["unknown_exposure_estimated_usd"]),
        "usage_complete": bucket["unknown_usage_operations"] == 0,
    }


def _window_bounds(
    *, period: str, now: datetime, start: datetime | None, end: datetime | None, days: int
) -> tuple[datetime, datetime]:
    if (start is None) != (end is None):
        raise ValueError("USAGE_WINDOW_BOTH_BOUNDS_REQUIRED")
    if start is not None and end is not None:
        lower, upper = _as_utc(start), _as_utc(end)
        if lower >= upper:
            raise ValueError("USAGE_WINDOW_START_MUST_PRECEDE_END")
        return lower, upper
    upper = _as_utc(now)
    if period == "calendar_month":
        return datetime(upper.year, upper.month, 1, tzinfo=UTC), upper
    return upper - timedelta(days=days), upper


def summarize_usage(
    session: Session,
    *,
    days: int = 30,
    period: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    now: datetime | None = None,
    include_active_reservations: bool = False,
) -> dict[str, Any]:
    checked_at = _as_utc(now or utc_now())
    selected_period = period or f"{days}d"
    since, until = _window_bounds(
        period=selected_period, now=checked_at, start=start, end=end, days=days
    )
    chat_activity = func.coalesce(
        AiOperation.request_sent_at, AiOperation.reserved_at, AiOperation.created_at
    )
    learning_activity = func.coalesce(
        LearningProviderOperation.request_sent_at,
        LearningProviderOperation.reserved_at,
        LearningProviderOperation.created_at,
    )
    chat_window = (chat_activity >= since) & (chat_activity < until)
    learning_window = (learning_activity >= since) & (learning_activity < until)
    if include_active_reservations:
        chat_window = or_(chat_window, AiOperation.request_stage == "RESERVED")
        learning_window = or_(learning_window, LearningProviderOperation.request_stage == "RESERVED")
    chat_rows = list(
        session.execute(
            select(AiOperation, Message.mode_snapshot)
            .outerjoin(Message, Message.message_id == AiOperation.user_message_id)
            .where(chat_window)
            .order_by(chat_activity)
        ).all()
    )
    learning_rows = list(
        session.scalars(
            select(LearningProviderOperation)
            .where(
                learning_window,
            )
            .order_by(learning_activity)
        ).all()
    )

    daily: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_provider: dict[str, dict[str, Any]] = {}
    by_operation_type: dict[str, dict[str, Any]] = {}
    price_sources: dict[tuple[str, str, str], int] = {}
    totals = {"mock": _empty_bucket(), "online": _empty_bucket()}
    rows: list[tuple[Any, str | None]] = [(row, mode) for row, mode in chat_rows]
    rows.extend((row, None) for row in learning_rows)

    for row, chat_mode in rows:
        provider = (row.provider or "UNKNOWN").strip().upper() or "UNKNOWN"
        channel = _channel(provider)
        model = row.resolved_model or row.requested_model or "unknown"
        category = _row_category(row, chat_mode)
        snapshot = row.price_snapshot_json
        if isinstance(snapshot, dict) and snapshot.get("checked_on") and snapshot.get("pricing_url"):
            source_key = (provider, str(snapshot["checked_on"]), str(snapshot["pricing_url"]))
            price_sources[source_key] = price_sources.get(source_key, 0) + 1
        activity_time = _activity_time(row)
        if include_active_reservations and _request_stage(row) == "RESERVED":
            activity_time = max(activity_time, since)
        day = activity_time.date().isoformat()
        day_bucket = daily.setdefault(
            day, {"date": day, "mock": _empty_bucket(), "online": _empty_bucket()}
        )
        model_key = f"{channel}:{provider}:{model}:{category}"
        model_bucket = by_model.setdefault(
            model_key,
            {"channel": channel, "provider": provider, "model": model, "operation_type": category, **_empty_bucket()},
        )
        provider_bucket = by_provider.setdefault(
            provider, {"provider": provider, **_empty_bucket()}
        )
        category_bucket = by_operation_type.setdefault(
            category, {"operation_type": category, **_empty_bucket()}
        )
        for bucket in (
            totals[channel],
            day_bucket[channel],
            model_bucket,
            provider_bucket,
            category_bucket,
        ):
            _add_row(bucket, row, online=channel == "online")

    deepseek_rates = public_cost_estimate()
    openai_rates = openai_public_cost_estimate()
    online = totals["online"]
    known_estimate = _money(online["estimated_usd"])
    reserved = online["reserved_estimated_usd"]
    unknown_exposure = online["unknown_exposure_estimated_usd"]
    budget_exposure = online["estimated_usd"] + reserved + unknown_exposure
    return {
        "period_days": days,
        "window_period": selected_period,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "checked_at": checked_at.isoformat(),
        "currency": BUDGET_CURRENCY,
        "cost_estimate": deepseek_rates,
        "cost_estimates": {"deepseek": deepseek_rates, "openai": openai_rates},
        "provider_billing_urls": {
            "deepseek": "https://platform.deepseek.com/usage",
            "openai": "https://platform.openai.com/usage",
        },
        "used_price_sources": [
            {"provider": provider, "checked_on": checked_on, "pricing_url": url, "operations": count}
            for (provider, checked_on, url), count in sorted(price_sources.items())
        ],
        "by_provider": [
            {"provider": item["provider"], **_public_bucket(item, estimated=item["provider"] in {"DEEPSEEK", "OPENAI", "ONLINE"})}
            for item in sorted(by_provider.values(), key=lambda value: value["provider"])
        ],
        "totals": {
            "mock": _public_bucket(totals["mock"], estimated=False),
            "online": _public_bucket(online, estimated=True),
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
                "provider": item["provider"],
                "model": item["model"],
                "operation_type": item["operation_type"],
                **_public_bucket(item, estimated=item["channel"] == "online"),
            }
            for item in sorted(
                by_model.values(),
                key=lambda value: (value["channel"], value["provider"], value["model"], value["operation_type"]),
            )
        ],
        "by_operation_type": [
            {"operation_type": item["operation_type"], **_public_bucket(item, estimated=True)}
            for item in sorted(by_operation_type.values(), key=lambda value: value["operation_type"])
        ],
        "online_actual_usage_available": online["operations"] > 0
        and online["unknown_usage_operations"] < online["operations"],
        "online_actual_usage_message": (
            "尚无在线 Provider 响应 usage 记录；费用由各服务商账户结算。"
            if online["operations"] == 0
            else "Provider 响应 usage 用于本地估算；尚未与官方账单核对。"
        ),
        "unknown_usage_operations": sum(
            item["unknown_usage_operations"] for item in totals.values()
        ),
        "estimated_online_usd": known_estimate,
        "reserved_online_usd": _money(reserved),
        "unknown_exposure_estimated_usd": _money(unknown_exposure),
        "budget_exposure_estimated_usd": _money(budget_exposure),
        "estimate_disclaimer": "费用由 DeepSeek 或 OpenAI 各自账户结算；这里仅按 Provider usage 和请求时价格快照估算，不是官方账单或费用上限。",
        "billing_reconciliation_status": "尚未与官方账单核对",
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
    checked_at = utc_now()
    budget = read_budget(session)
    usage = summarize_usage(
        session,
        period=budget["period"],
        now=checked_at,
        include_active_reservations=True,
    )
    known_spend = _parse_decimal(usage["estimated_online_usd"]) or Decimal("0")
    exposure = _parse_decimal(usage["budget_exposure_estimated_usd"]) or known_spend
    hard_stop = _parse_decimal(budget.get("hard_stop_usd"))
    remaining = None if hard_stop is None else _money(hard_stop - exposure)
    soft_remind = _parse_decimal(budget.get("soft_remind_usd"))
    unknown_ops = int(usage["totals"]["online"]["unknown_usage_operations"])
    soft_triggered = bool(
        budget["enabled"] and soft_remind is not None and exposure >= soft_remind
    )
    block_reason = None
    if budget["enabled"] and hard_stop is not None:
        if unknown_ops and budget["unknown_usage_policy"] == "deny":
            block_reason = "周期内存在 usage 未知或价格快照缺失的在线操作，保守拒绝新请求。"
        elif exposure >= hard_stop:
            block_reason = "已用本地估算、未知用量预留与未完成预留达到硬停止阈值。"
    return {
        "budget": budget,
        "usage_summary": {
            "estimated_online_usd": usage["estimated_online_usd"],
            "reserved_online_usd": usage["reserved_online_usd"],
            "unknown_exposure_estimated_usd": usage["unknown_exposure_estimated_usd"],
            "budget_exposure_estimated_usd": usage["budget_exposure_estimated_usd"],
            "unknown_usage_operations": unknown_ops,
            "online_operations": usage["totals"]["online"]["operations"],
            "online_usage_complete": usage["totals"]["online"]["usage_complete"],
            "online_actual_usage_message": usage["online_actual_usage_message"],
        },
        "spent_estimated_usd": _money(known_spend),
        "budget_exposure_estimated_usd": _money(exposure),
        "remaining_estimated_usd": remaining,
        "soft_remind_triggered": soft_triggered,
        "hard_stop_would_block": block_reason is not None,
        "hard_stop_block_reason": block_reason,
        "checked_at": checked_at.isoformat(),
        "window_start": usage["window_start"],
        "window_end": usage["window_end"],
        "currency": BUDGET_CURRENCY,
        "estimate_disclaimer": usage["estimate_disclaimer"],
        "billing_reconciliation_status": usage["billing_reconciliation_status"],
    }


def _check_budget(
    session: Session,
    *,
    estimated_request_usd: Decimal | None,
    confirm_unknown_usage: bool,
) -> dict[str, Any]:
    status = budget_status(session)
    budget = status["budget"]
    if not budget["enabled"]:
        return status
    hard_stop = _parse_decimal(budget.get("hard_stop_usd"))
    if hard_stop is None:
        return status
    unknown_ops = int(status["usage_summary"]["unknown_usage_operations"])
    if unknown_ops and budget["unknown_usage_policy"] == "deny":
        raise BudgetRejected(
            "BUDGET_USAGE_UNTRUSTED", "周期用量存在未知 usage 或缺少价格快照，硬限额按保守策略拒绝外发。"
        )
    if unknown_ops and budget["unknown_usage_policy"] == "confirm" and not confirm_unknown_usage:
        raise BudgetRejected(
            "BUDGET_UNKNOWN_USAGE_CONFIRM_REQUIRED", "周期用量存在未知 usage，需要明确确认后才能继续外发。"
        )
    exposure = _parse_decimal(status["budget_exposure_estimated_usd"]) or Decimal("0")
    request_cost = estimated_request_usd or Decimal("0")
    if exposure + request_cost >= hard_stop:
        raise BudgetRejected(
            "BUDGET_HARD_STOP_REACHED", "已达到或将超过本周期硬停止阈值，未发起外部 Provider 请求。"
        )
    return status


def assert_external_budget_allows(
    session: Session,
    *,
    estimated_request_usd: Decimal | None = None,
    confirm_unknown_usage: bool = False,
) -> dict[str, Any]:
    """Read-only preflight; the operation reservation is committed separately."""
    return {
        "allowed": True,
        "status": _check_budget(
            session,
            estimated_request_usd=estimated_request_usd,
            confirm_unknown_usage=confirm_unknown_usage,
        ),
    }


def reserve_external_operation(
    session: Session,
    *,
    operation_id: str,
    provider: str,
    model: str,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    confirm_unknown_usage: bool = False,
) -> dict[str, Any]:
    """Atomically reserve estimated cost using SQLite's cross-process writer lock."""
    snapshot = _price_snapshot(provider, model)
    estimate = None if snapshot is None else _estimate_usd(
        estimated_input_tokens, estimated_output_tokens, snapshot
    )
    bind = session.get_bind()
    with Session(bind=bind, join_transaction_mode="control_fully") as writer:
        writer.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            operation: Any = writer.get(AiOperation, operation_id)
            if operation is None:
                operation = writer.get(LearningProviderOperation, operation_id)
            if operation is None or operation.provider.upper() != provider.upper():
                raise BudgetRejected("BUDGET_OPERATION_NOT_FOUND", "在线调用记录不存在或 Provider 不匹配。")
            stage = _request_stage(operation)
            if stage != "NOT_SENT":
                return {"reserved": False, "stage": stage, "estimated_usd": _money(estimate) if estimate is not None else None}

            status = _check_budget(
                writer,
                estimated_request_usd=estimate,
                confirm_unknown_usage=confirm_unknown_usage,
            )
            if budget_enabled := status["budget"]["enabled"]:
                hard_stop = _parse_decimal(status["budget"].get("hard_stop_usd"))
                exposure = _parse_decimal(status["budget_exposure_estimated_usd"]) or Decimal("0")
                if hard_stop is not None and estimate is None and status["budget"]["unknown_usage_policy"] == "deny":
                    raise BudgetRejected("BUDGET_PRICE_UNKNOWN", "当前 Provider 缺少可用价格快照，未发起外部请求。")
                if hard_stop is not None and exposure >= hard_stop:
                    raise BudgetRejected("BUDGET_HARD_STOP_REACHED", "本周期预算没有可用余量，未发起外部 Provider 请求。")

            operation.request_stage = "RESERVED"
            operation.reserved_at = utc_now()
            operation.reserved_estimate_usd = estimate
            operation.price_snapshot_json = snapshot
            operation.updated_at = utc_now()
            writer.flush()
            writer.commit()
            return {
                "reserved": True,
                "stage": "RESERVED",
                "estimated_usd": _money(estimate) if estimate is not None else None,
                "budget_enabled": budget_enabled,
                "status": status,
            }
        except Exception:
            writer.rollback()
            raise


def mark_external_operation_possibly_sent(session: Session, operation_id: str) -> None:
    now = utc_now()
    for model in (AiOperation, LearningProviderOperation):
        result = session.execute(
            update(model)
            .where(model.operation_id == operation_id, model.request_stage == "RESERVED")
            .values(request_stage="POSSIBLY_SENT", request_sent_at=now, updated_at=now)
        )
        if int(getattr(result, "rowcount", 0) or 0) == 1:
            session.commit()
            return
    session.rollback()
    raise BudgetRejected(
        "BUDGET_RESERVATION_INVALID", "在线调用没有唯一有效的预算预留，未发起 Provider 请求。"
    )


def release_external_operation_reservation(session: Session, operation_id: str) -> None:
    now = utc_now()
    for model in (AiOperation, LearningProviderOperation):
        result = session.execute(
            update(model)
            .where(model.operation_id == operation_id, model.request_stage == "RESERVED")
            .values(
                request_stage="NOT_SENT",
                reserved_at=None,
                reserved_estimate_usd=None,
                updated_at=now,
            )
        )
        if int(getattr(result, "rowcount", 0) or 0) == 1:
            session.commit()
            return
    session.rollback()


def response_usage_stage(
    operation: Any, input_tokens: int | None, output_tokens: int | None
) -> str:
    operation.usage_input_tokens = input_tokens
    operation.usage_output_tokens = output_tokens
    operation.request_stage = (
        "USAGE_KNOWN"
        if input_tokens is not None
        and output_tokens is not None
        and _snapshot_cost(operation, input_tokens, output_tokens) is not None
        else "UNKNOWN"
    )
    return operation.request_stage


def uncertain_external_usage(operation: Any) -> None:
    if _request_stage(operation) == "POSSIBLY_SENT":
        operation.request_stage = "UNKNOWN"


class BudgetRejected(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def privacy_diagnostics_status() -> dict[str, Any]:
    return {
        "log_retention": {
            "available": False,
            "message": "仅管理应用保存的结构化诊断事件；终端输出、手动命令输出和 Windows 系统日志不在此范围。",
        },
        "diagnostics_export": {
            "available": True,
            "message": "可预览并导出安全状态包；仅保存在本机，不自动上传。",
        },
        "storage_migration": {
            "available": False,
            "message": "当前设置不提供现有数据目录搬迁；数据库 Schema 由 Alembic 执行版本升级。",
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
    "mark_external_operation_possibly_sent",
    "privacy_diagnostics_status",
    "read_budget",
    "release_external_operation_reservation",
    "reserve_external_operation",
    "response_usage_stage",
    "set_budget",
    "summarize_usage",
    "uncertain_external_usage",
]
