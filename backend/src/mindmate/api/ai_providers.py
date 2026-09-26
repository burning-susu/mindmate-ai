from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from mindmate.ai.providers.base import ProviderRequestError
from mindmate.ai.providers.deepseek import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.api.files import get_session
from mindmate.application.provider_configuration import (
    DEEPSEEK_SECRET_REFERENCE,
    EXTERNAL_AI_CONSENT_VERSION,
    delete_api_key,
    provider_lock,
    provider_status,
    read_consent,
    record_consent,
    save_api_key,
    save_probe_failure,
    save_probe_success,
    set_generation_mode,
)
from mindmate.security.credentials import (
    CredentialStoreError,
    CredentialStorePort,
    WindowsCredentialStore,
)

router = APIRouter(prefix="/api/v1")


class AiProviderApiError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 503, retryable: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status_code
        self.retryable = retryable


CapabilityState = Literal["supported", "unsupported", "unknown"]


class ConsentResponse(BaseModel):
    current_version: str
    accepted: bool
    version: str | None = None
    accepted_at: str | None = None


class CredentialStoreResponse(BaseModel):
    available: bool
    type: str
    error_code: str | None = None


class ConnectionProbeResponse(BaseModel):
    status: Literal["success", "failed"]
    checked_at: str
    requested_model: str
    resolved_model: str | None = None
    stream_supported: CapabilityState
    usage_supported: CapabilityState
    structured_output_supported: CapabilityState
    provider_request_id: str | None = None
    response_fingerprint: str | None = None
    usage: dict[str, int] | None = None
    error_code: str | None = None
    error_detail: str | None = None
    retryable: bool | None = None


class CostEstimateResponse(BaseModel):
    checked_on: str
    model: str
    pricing_url: str
    rate_assumption: str
    input_usd_per_million_tokens: str
    output_usd_per_million_tokens: str
    knowledge_input_token_cap: int
    knowledge_output_token_cap: int
    knowledge_question_estimated_usd_ceiling: str
    probe_output_token_cap: int
    probe_estimated_usd_ceiling: str
    disclaimer: str


class AiProviderStatusResponse(BaseModel):
    provider: str
    display_name: str
    configured: bool
    credential_store: CredentialStoreResponse
    requested_model: str
    consent: ConsentResponse
    probe: ConnectionProbeResponse | None = None
    source_url: str
    pricing_url: str
    generation_mode: Literal["mock", "deepseek"] = "mock"
    cost_estimate: CostEstimateResponse


class ApiKeyRequest(BaseModel):
    api_key: SecretStr = Field(min_length=1, max_length=4096)


class ConnectionTestRequest(BaseModel):
    confirm_external_transfer: bool = False


class ConsentRequest(BaseModel):
    version: str = Field(min_length=1, max_length=80)


class GenerationModeRequest(BaseModel):
    mode: Literal["mock", "deepseek"]


def _credential_store(request: Request) -> CredentialStorePort:
    store = getattr(request.app.state, "credential_store", None)
    if store is None:
        store = WindowsCredentialStore()
        request.app.state.credential_store = store
    return store


def _provider(request: Request) -> DeepSeekChatProvider:
    provider = getattr(request.app.state, "deepseek_provider", None)
    if provider is None:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            raise AiProviderApiError("LOCAL_RUNTIME_UNAVAILABLE", "本地运行配置不可用。")
        provider = DeepSeekChatProvider(
            base_url=DEEPSEEK_BASE_URL,
            model=DEEPSEEK_MODEL,
            timeout_seconds=settings.provider_timeout_seconds,
        )
        request.app.state.deepseek_provider = provider
    return provider


def _status(request: Request, session: Session, store: CredentialStorePort) -> dict[str, Any]:
    settings = getattr(request.app.state, "settings", None)
    fallback = getattr(settings, "provider_mode", "mock")
    return provider_status(session, store, provider_mode_fallback=str(fallback))[0]


def _store_error(exc: CredentialStoreError) -> AiProviderApiError:
    return AiProviderApiError(
        exc.code,
        "Windows 凭据存储当前不可用，未保存任何明文 Key。请检查系统凭据服务后重试。",
        503,
        True,
    )


@router.get(
    "/ai/provider",
    response_model=AiProviderStatusResponse,
    tags=["ai-provider"],
)
def get_ai_provider_status(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return _status(request, session, _credential_store(request))


@router.post(
    "/ai/provider/key",
    response_model=AiProviderStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["ai-provider"],
)
def save_ai_provider_key(
    request: Request,
    payload: ApiKeyRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    store = _credential_store(request)
    secret = payload.api_key.get_secret_value()
    try:
        save_api_key(session, store, secret)
        return _status(request, session, store)
    except CredentialStoreError as exc:
        raise _store_error(exc) from exc
    finally:
        secret = ""


@router.delete(
    "/ai/provider/key",
    response_model=AiProviderStatusResponse,
    tags=["ai-provider"],
)
def delete_ai_provider_key(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    store = _credential_store(request)
    try:
        delete_api_key(session, store)
        return _status(request, session, store)
    except CredentialStoreError as exc:
        raise _store_error(exc) from exc


@router.post(
    "/ai/provider/test",
    response_model=AiProviderStatusResponse,
    tags=["ai-provider"],
)
def test_ai_provider_connection(
    request: Request,
    payload: ConnectionTestRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if not payload.confirm_external_transfer:
        raise AiProviderApiError(
            "EXTERNAL_TRANSFER_CONFIRMATION_REQUIRED",
            "连接测试前必须确认会向 DeepSeek 发送固定测试文本并产生极小 API 用量。",
            400,
        )
    store = _credential_store(request)
    provider = _provider(request)
    with provider_lock():
        try:
            secret = store.get_secret(DEEPSEEK_SECRET_REFERENCE)
        except CredentialStoreError as exc:
            raise _store_error(exc) from exc
        if not secret:
            raise AiProviderApiError("PROVIDER_KEY_MISSING", "请先保存 DeepSeek API Key。", 409)
        try:
            result = provider.test_connection(secret)
        except ProviderRequestError as exc:
            save_probe_failure(session, provider.model, exc.code, exc.detail, exc.retryable)
            raise
        finally:
            secret = ""
        save_probe_success(session, result)
    return _status(request, session, store)


@router.post(
    "/ai/provider/generation-mode",
    response_model=AiProviderStatusResponse,
    tags=["ai-provider"],
)
def set_ai_generation_mode(
    request: Request,
    payload: GenerationModeRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    set_generation_mode(session, payload.mode)
    return _status(request, session, _credential_store(request))


@router.post(
    "/ai/consent",
    response_model=ConsentResponse,
    tags=["ai-provider"],
)
def accept_external_ai_consent(
    payload: ConsentRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    if payload.version != EXTERNAL_AI_CONSENT_VERSION:
        raise AiProviderApiError(
            "CONSENT_VERSION_UNSUPPORTED",
            "当前外发说明版本已变化，请重新阅读后确认。",
            400,
        )
    return record_consent(session)


@router.get(
    "/ai/consent",
    response_model=ConsentResponse,
    tags=["ai-provider"],
)
def get_external_ai_consent(session: Session = Depends(get_session)) -> dict[str, Any]:
    return read_consent(session)
__all__ = ["router"]
