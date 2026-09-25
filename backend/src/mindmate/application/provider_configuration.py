from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.ai.providers.base import ProviderProbeResult
from mindmate.ai.providers.deepseek import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from mindmate.infrastructure.models import AppSetting, ProviderProfile
from mindmate.security.credentials import CredentialStorePort

DEEPSEEK_PROVIDER_TYPE = "DEEPSEEK"
DEEPSEEK_DISPLAY_NAME = "DeepSeek"
DEEPSEEK_SECRET_REFERENCE = "provider/deepseek/api-key"
EXTERNAL_AI_CONSENT_VERSION = "deepseek-external-ai-v1"
CONSENT_SETTING_KEY = "privacy.external_ai_consent"
PROBE_SETTING_KEY = "ai.deepseek.connection_probe"
_PROVIDER_LOCK = RLock()


def utc_now() -> datetime:
    return datetime.now(UTC)


def _profile(session: Session) -> ProviderProfile | None:
    return session.scalar(
        select(ProviderProfile)
        .where(ProviderProfile.provider_type == DEEPSEEK_PROVIDER_TYPE)
        .order_by(ProviderProfile.created_at)
        .limit(1)
    )


def _ensure_profile(session: Session) -> ProviderProfile:
    profile = _profile(session)
    if profile is not None:
        return profile
    now = utc_now()
    profile = ProviderProfile(
        provider_type=DEEPSEEK_PROVIDER_TYPE,
        display_name=DEEPSEEK_DISPLAY_NAME,
        endpoint=DEEPSEEK_BASE_URL,
        default_chat_model=DEEPSEEK_MODEL,
        enabled=False,
        secret_reference=DEEPSEEK_SECRET_REFERENCE,
        created_at=now,
        updated_at=now,
    )
    session.add(profile)
    session.flush()
    return profile


def _setting(session: Session, key: str) -> dict[str, Any] | None:
    row = session.get(AppSetting, key)
    if row is None or not isinstance(row.setting_value_json, dict):
        return None
    return row.setting_value_json


def _set_setting(session: Session, key: str, value: dict[str, Any]) -> None:
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


def read_consent(session: Session) -> dict[str, Any]:
    stored = _setting(session, CONSENT_SETTING_KEY) or {}
    version = stored.get("version") if isinstance(stored.get("version"), str) else None
    accepted_at = stored.get("accepted_at") if isinstance(stored.get("accepted_at"), str) else None
    return {
        "current_version": EXTERNAL_AI_CONSENT_VERSION,
        "accepted": version == EXTERNAL_AI_CONSENT_VERSION,
        "version": version,
        "accepted_at": accepted_at,
    }


def record_consent(session: Session) -> dict[str, Any]:
    accepted_at = utc_now().isoformat()
    _set_setting(
        session,
        CONSENT_SETTING_KEY,
        {"version": EXTERNAL_AI_CONSENT_VERSION, "accepted_at": accepted_at},
    )
    session.commit()
    return read_consent(session)


def read_probe(session: Session) -> dict[str, Any] | None:
    stored = _setting(session, PROBE_SETTING_KEY)
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


def save_probe_success(session: Session, result: ProviderProbeResult) -> None:
    _set_setting(
        session,
        PROBE_SETTING_KEY,
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
) -> None:
    _set_setting(
        session,
        PROBE_SETTING_KEY,
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


def provider_status(
    session: Session, credential_store: CredentialStorePort
) -> tuple[dict[str, Any], bool]:
    configured = False
    credential_store_available = True
    credential_store_error: str | None = None
    try:
        configured = credential_store.has_secret(DEEPSEEK_SECRET_REFERENCE)
    except Exception as exc:
        credential_store_available = False
        credential_store_error = getattr(exc, "code", "CREDENTIAL_STORE_UNAVAILABLE")
    consent = read_consent(session)
    probe = read_probe(session)
    return (
        {
            "provider": DEEPSEEK_PROVIDER_TYPE,
            "display_name": DEEPSEEK_DISPLAY_NAME,
            "configured": configured,
            "credential_store": {
                "available": credential_store_available,
                "type": "windows-credential-manager",
                "error_code": credential_store_error,
            },
            "requested_model": DEEPSEEK_MODEL,
            "consent": consent,
            "probe": probe,
            "source_url": "https://platform.deepseek.com/api_keys",
            "pricing_url": "https://api-docs.deepseek.com/quick_start/pricing",
        },
        credential_store_available,
    )


def save_api_key(session: Session, credential_store: CredentialStorePort, api_key: str) -> dict[str, Any]:
    with _PROVIDER_LOCK:
        credential_store.set_secret(DEEPSEEK_SECRET_REFERENCE, api_key)
        profile = _ensure_profile(session)
        profile.enabled = True
        profile.secret_reference = DEEPSEEK_SECRET_REFERENCE
        profile.updated_at = utc_now()
        session.commit()
        return provider_status(session, credential_store)[0]


def delete_api_key(session: Session, credential_store: CredentialStorePort) -> dict[str, Any]:
    with _PROVIDER_LOCK:
        credential_store.delete_secret(DEEPSEEK_SECRET_REFERENCE)
        profile = _profile(session)
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
    "EXTERNAL_AI_CONSENT_VERSION",
    "PROBE_SETTING_KEY",
    "delete_api_key",
    "provider_lock",
    "provider_status",
    "read_consent",
    "read_probe",
    "record_consent",
    "save_api_key",
    "save_probe_failure",
    "save_probe_success",
]
