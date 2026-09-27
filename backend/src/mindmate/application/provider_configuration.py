from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.ai.providers.base import ProviderProbeResult
from mindmate.ai.providers.deepseek import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from mindmate.ai.providers.openai import OPENAI_BASE_URL, OPENAI_MODEL
from mindmate.infrastructure.models import AppSetting, ProviderProfile
from mindmate.security.credentials import CredentialStorePort

DEEPSEEK_PROVIDER_TYPE = "DEEPSEEK"
DEEPSEEK_DISPLAY_NAME = "DeepSeek"
DEEPSEEK_SECRET_REFERENCE = "provider/deepseek/api-key"
EXTERNAL_AI_CONSENT_VERSION = "deepseek-external-ai-v1"
CONSENT_SETTING_KEY = "privacy.external_ai_consent"
PROBE_SETTING_KEY = "ai.deepseek.connection_probe"
OPENAI_PROVIDER_ID = "openai_gpt6_sol"
OPENAI_PROVIDER_TYPE = "OPENAI"
OPENAI_DISPLAY_NAME = "OpenAI GPT-6 Sol"
OPENAI_SECRET_REFERENCE = "provider/openai/api-key"
OPENAI_CONSENT_VERSION = "openai-external-ai-v1"
OPENAI_CONSENT_SETTING_KEY = "privacy.openai_external_ai_consent"
OPENAI_PROBE_SETTING_KEY = "ai.openai.connection_probe"
GENERATION_MODE_SETTING_KEY = "ai.chat.generation_mode"
GENERATION_MODES = {"mock", "deepseek", OPENAI_PROVIDER_ID}
LEARNING_PROVIDER_NOTICE = "模型选择目前适用于 AI 对话；学习出题仍是本地演示规则。"
ACCOUNT_NOTICE = "OpenAI 和 DeepSeek 是两套不同账户、API Key 和账单。"
_PROVIDER_LOCK = RLock()


def utc_now() -> datetime:
    return datetime.now(UTC)


def provider_spec(provider_id: str = "deepseek") -> dict[str, str]:
    if provider_id == OPENAI_PROVIDER_ID:
        return {
            "provider_id": OPENAI_PROVIDER_ID,
            "provider_type": OPENAI_PROVIDER_TYPE,
            "display_name": OPENAI_DISPLAY_NAME,
            "endpoint": OPENAI_BASE_URL,
            "model": OPENAI_MODEL,
            "secret_reference": OPENAI_SECRET_REFERENCE,
            "consent_version": OPENAI_CONSENT_VERSION,
            "consent_key": OPENAI_CONSENT_SETTING_KEY,
            "probe_key": OPENAI_PROBE_SETTING_KEY,
            "source_url": "https://platform.openai.com/api-keys",
            "pricing_url": "https://developers.openai.com/api/docs/models/gpt-6-sol",
            "billing_note": "API 费用由 OpenAI Platform 单独结算。未配置官方 Key 时为未配置/不可用。",
        }
    if provider_id != "deepseek":
        raise ValueError(provider_id)
    return {
        "provider_id": "deepseek",
        "provider_type": DEEPSEEK_PROVIDER_TYPE,
        "display_name": DEEPSEEK_DISPLAY_NAME,
        "endpoint": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
        "secret_reference": DEEPSEEK_SECRET_REFERENCE,
        "consent_version": EXTERNAL_AI_CONSENT_VERSION,
        "consent_key": CONSENT_SETTING_KEY,
        "probe_key": PROBE_SETTING_KEY,
        "source_url": "https://platform.deepseek.com/api_keys",
        "pricing_url": "https://api-docs.deepseek.com/quick_start/pricing",
        "billing_note": "API 费用由 DeepSeek 开放平台单独结算。",
    }


def _profile(session: Session, provider_type: str = DEEPSEEK_PROVIDER_TYPE) -> ProviderProfile | None:
    return session.scalar(
        select(ProviderProfile)
        .where(ProviderProfile.provider_type == provider_type)
        .order_by(ProviderProfile.created_at)
        .limit(1)
    )


def _ensure_profile(session: Session, provider_id: str = "deepseek") -> ProviderProfile:
    spec = provider_spec(provider_id)
    profile = _profile(session, spec["provider_type"])
    if profile is not None:
        return profile
    now = utc_now()
    profile = ProviderProfile(
        provider_type=spec["provider_type"],
        display_name=spec["display_name"],
        endpoint=spec["endpoint"],
        default_chat_model=spec["model"],
        enabled=False,
        secret_reference=spec["secret_reference"],
        created_at=now,
        updated_at=now,
    )
    session.add(profile)
    session.flush()
    return profile


def read_setting(session: Session, key: str) -> dict[str, Any] | None:
    row = session.get(AppSetting, key)
    if row is None or not isinstance(row.setting_value_json, dict):
        return None
    return row.setting_value_json


def write_setting(session: Session, key: str, value: dict[str, Any]) -> None:
    row = session.get(AppSetting, key)
    now = utc_now()
    if row is None:
        session.add(
            AppSetting(
                setting_key=key,
                setting_value_json=value,
                setting_schema_version=1,
                updated_at=now,
            )
        )
    else:
        row.setting_value_json = value
        row.setting_schema_version = 1
        row.updated_at = now


# Compatibility aliases used by existing modules.
_setting = read_setting
_set_setting = write_setting


def public_cost_estimate() -> dict[str, Any]:
    """Conservative display estimate from the 2026-09-26 public price page.

    The numbers are not a billing authority and are not enforced as a USD cap.
    """

    return {
        "checked_on": "2026-09-26",
        "model": DEEPSEEK_MODEL,
        "pricing_url": "https://api-docs.deepseek.com/quick_start/pricing",
        "rate_assumption": "deepseek-flash 高峰时段、输入缓存未命中",
        "input_usd_per_million_tokens": "0.30",
        "output_usd_per_million_tokens": "1.20",
        "knowledge_input_token_cap": 2048,
        "knowledge_output_token_cap": 256,
        "knowledge_question_estimated_usd_ceiling": "0.001",
        "probe_output_token_cap": 8,
        "probe_estimated_usd_ceiling": "0.0001",
        "disclaimer": (
            "这是按 2026-09-26 公开费率、用满本地上限时的保守估算，不是严格美元限额，"
            "也不是账户扣费承诺。实际费用以 DeepSeek 账单为准，价格可能变化。"
        ),
    }


def openai_public_cost_estimate() -> dict[str, Any]:
    """Display estimate from the official gpt-6-sol page checked on 2026-09-27.

    Standard text rates only. Long-context, regional, batch and flex premiums
    are not included. This is not an OpenAI invoice.
    """

    return {
        "checked_on": "2026-09-27",
        "model": OPENAI_MODEL,
        "pricing_url": "https://developers.openai.com/api/docs/models/gpt-6-sol",
        "rate_assumption": "gpt-6-sol 标准文本价，未计缓存、超长输入和区域附加",
        "input_usd_per_million_tokens": "2.00",
        "output_usd_per_million_tokens": "10.00",
        "knowledge_input_token_cap": 2048,
        "knowledge_output_token_cap": 256,
        "knowledge_question_estimated_usd_ceiling": "0.0067",
        "probe_output_token_cap": 32,
        "probe_estimated_usd_ceiling": "0.001",
        "disclaimer": (
            "这是按 2026-09-27 官方模型页公开费率、用满本地上限时的保守估算，不是严格美元限额，"
            "也不是 OpenAI 账单。实际费用以 OpenAI Platform 账单为准，价格可能变化。"
            "API 费用由 OpenAI Platform 单独结算。"
        ),
    }


def public_cost_estimate_for(provider_id: str) -> dict[str, Any]:
    if provider_id == OPENAI_PROVIDER_ID:
        return openai_public_cost_estimate()
    return public_cost_estimate()


def read_generation_mode(session: Session, *, fallback: str = "mock") -> str:
    stored = _setting(session, GENERATION_MODE_SETTING_KEY)
    if stored is None:
        return fallback if fallback in GENERATION_MODES else "mock"
    mode = stored.get("mode")
    if isinstance(mode, str) and mode in GENERATION_MODES:
        return mode
    return "mock"


def set_generation_mode(session: Session, mode: str) -> dict[str, Any]:
    if mode not in GENERATION_MODES:
        raise ValueError(mode)
    _set_setting(session, GENERATION_MODE_SETTING_KEY, {"mode": mode})
    session.commit()
    return {"mode": mode}


def read_consent(session: Session, provider_id: str = "deepseek") -> dict[str, Any]:
    spec = provider_spec(provider_id)
    stored = _setting(session, spec["consent_key"]) or {}
    version = stored.get("version") if isinstance(stored.get("version"), str) else None
    accepted_at = stored.get("accepted_at") if isinstance(stored.get("accepted_at"), str) else None
    return {
        "current_version": spec["consent_version"],
        "accepted": version == spec["consent_version"],
        "version": version,
        "accepted_at": accepted_at,
    }


def record_consent(session: Session, provider_id: str = "deepseek") -> dict[str, Any]:
    spec = provider_spec(provider_id)
    accepted_at = utc_now().isoformat()
    _set_setting(
        session,
        spec["consent_key"],
        {"version": spec["consent_version"], "accepted_at": accepted_at},
    )
    session.commit()
    return read_consent(session, provider_id)


def read_probe(session: Session, provider_id: str = "deepseek") -> dict[str, Any] | None:
    stored = _setting(session, provider_spec(provider_id)["probe_key"])
    if stored is None:
        return None
    allowed = {
        "status",
        "checked_at",
        "requested_model",
        "resolved_model",
        "stream_supported",
        "usage_supported",
        "structured_output_supported",
        "provider_request_id",
        "response_fingerprint",
        "usage",
        "error_code",
        "error_detail",
        "retryable",
    }
    return {key: value for key, value in stored.items() if key in allowed}


def save_probe_success(
    session: Session, result: ProviderProbeResult, *, provider_id: str = "deepseek"
) -> None:
    _set_setting(
        session,
        provider_spec(provider_id)["probe_key"],
        {
            "status": "success",
            "checked_at": utc_now().isoformat(),
            "requested_model": result.requested_model,
            "resolved_model": result.resolved_model,
            "stream_supported": result.stream_supported,
            "usage_supported": result.usage_supported,
            "structured_output_supported": result.structured_output_supported,
            "provider_request_id": result.provider_request_id,
            "response_fingerprint": result.response_fingerprint,
            "usage": result.usage,
        },
    )
    session.commit()


def save_probe_failure(
    session: Session,
    requested_model: str,
    code: str,
    detail: str,
    retryable: bool,
    *,
    provider_id: str = "deepseek",
) -> None:
    _set_setting(
        session,
        provider_spec(provider_id)["probe_key"],
        {
            "status": "failed",
            "checked_at": utc_now().isoformat(),
            "requested_model": requested_model,
            "resolved_model": None,
            "stream_supported": "unknown",
            "usage_supported": "unknown",
            "structured_output_supported": "unknown",
            "provider_request_id": None,
            "response_fingerprint": None,
            "usage": None,
            "error_code": code,
            "error_detail": detail,
            "retryable": retryable,
        },
    )
    session.commit()


def _provider_card(
    session: Session,
    credential_store: CredentialStorePort,
    provider_id: str,
) -> tuple[dict[str, Any], bool]:
    spec = provider_spec(provider_id)
    configured = False
    credential_store_available = True
    credential_store_error: str | None = None
    try:
        configured = credential_store.has_secret(spec["secret_reference"])
    except Exception as exc:
        credential_store_available = False
        credential_store_error = getattr(exc, "code", "CREDENTIAL_STORE_UNAVAILABLE")
    return (
        {
            "provider_id": spec["provider_id"],
            "provider": spec["provider_type"],
            "display_name": spec["display_name"],
            "configured": configured,
            "credential_store": {
                "available": credential_store_available,
                "type": "windows-credential-manager",
                "error_code": credential_store_error,
            },
            "requested_model": spec["model"],
            "consent": read_consent(session, provider_id),
            "probe": read_probe(session, provider_id),
            "source_url": spec["source_url"],
            "pricing_url": spec["pricing_url"],
            "cost_estimate": public_cost_estimate_for(provider_id),
            "billing_note": spec["billing_note"],
        },
        credential_store_available,
    )


def provider_status(
    session: Session,
    credential_store: CredentialStorePort,
    *,
    provider_mode_fallback: str = "mock",
) -> tuple[dict[str, Any], bool]:
    deepseek_card, credential_store_available = _provider_card(session, credential_store, "deepseek")
    openai_card, _openai_store_available = _provider_card(
        session, credential_store, OPENAI_PROVIDER_ID
    )
    return (
        {
            "provider": deepseek_card["provider"],
            "display_name": deepseek_card["display_name"],
            "configured": deepseek_card["configured"],
            "credential_store": deepseek_card["credential_store"],
            "requested_model": deepseek_card["requested_model"],
            "consent": deepseek_card["consent"],
            "probe": deepseek_card["probe"],
            "source_url": deepseek_card["source_url"],
            "pricing_url": deepseek_card["pricing_url"],
            "generation_mode": read_generation_mode(session, fallback=provider_mode_fallback),
            "cost_estimate": public_cost_estimate(),
            "providers": [deepseek_card, openai_card],
            "learning_notice": LEARNING_PROVIDER_NOTICE,
            "account_notice": ACCOUNT_NOTICE,
        },
        credential_store_available,
    )


def save_api_key(
    session: Session,
    credential_store: CredentialStorePort,
    api_key: str,
    *,
    provider_id: str = "deepseek",
) -> dict[str, Any]:
    spec = provider_spec(provider_id)
    with _PROVIDER_LOCK:
        credential_store.set_secret(spec["secret_reference"], api_key)
        profile = _ensure_profile(session, provider_id)
        profile.enabled = True
        profile.secret_reference = spec["secret_reference"]
        profile.updated_at = utc_now()
        session.commit()
        return provider_status(session, credential_store)[0]


def delete_api_key(
    session: Session,
    credential_store: CredentialStorePort,
    *,
    provider_id: str = "deepseek",
) -> dict[str, Any]:
    spec = provider_spec(provider_id)
    with _PROVIDER_LOCK:
        credential_store.delete_secret(spec["secret_reference"])
        profile = _profile(session, spec["provider_type"])
        if profile is not None:
            profile.enabled = False
            profile.updated_at = utc_now()
            session.commit()
        return provider_status(session, credential_store)[0]


def provider_lock() -> RLock:
    return _PROVIDER_LOCK


__all__ = [
    "CONSENT_SETTING_KEY",
    "DEEPSEEK_DISPLAY_NAME",
    "DEEPSEEK_PROVIDER_TYPE",
    "DEEPSEEK_SECRET_REFERENCE",
    "ACCOUNT_NOTICE",
    "EXTERNAL_AI_CONSENT_VERSION",
    "GENERATION_MODE_SETTING_KEY",
    "LEARNING_PROVIDER_NOTICE",
    "OPENAI_CONSENT_SETTING_KEY",
    "OPENAI_CONSENT_VERSION",
    "OPENAI_PROBE_SETTING_KEY",
    "OPENAI_PROVIDER_ID",
    "OPENAI_SECRET_REFERENCE",
    "PROBE_SETTING_KEY",
    "openai_public_cost_estimate",
    "provider_spec",
    "public_cost_estimate_for",
    "delete_api_key",
    "provider_lock",
    "provider_status",
    "public_cost_estimate",
    "read_consent",
    "read_generation_mode",
    "read_probe",
    "read_setting",
    "record_consent",
    "save_api_key",
    "save_probe_failure",
    "save_probe_success",
    "set_generation_mode",
    "write_setting",
]
