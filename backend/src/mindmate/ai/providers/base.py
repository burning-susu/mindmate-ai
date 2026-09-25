from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

CapabilityState = Literal["supported", "unsupported", "unknown"]


@dataclass(frozen=True)
class ProviderProbeResult:
    requested_model: str
    resolved_model: str | None
    stream_supported: CapabilityState
    usage_supported: CapabilityState
    structured_output_supported: CapabilityState
    provider_request_id: str | None
    response_fingerprint: str | None
    usage: dict[str, int] | None


@dataclass(frozen=True)
class ChatRequest:
    """Provider-neutral request used by the chat application service."""

    request_id: str
    task_type: str
    model_profile: str
    system_instructions: str
    messages: tuple[dict[str, str], ...]
    evidence_blocks: tuple[dict[str, str], ...] = ()
    response_schema: dict[str, Any] | None = None
    temperature: float = 0.6
    max_output_tokens: int = 2048
    reasoning_profile: str = "LOW"
    timeout_profile: str = "chat"
    stream: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResponse:
    request_id: str
    status: str
    content: str
    finish_reason: str | None
    provider: str
    requested_model: str
    resolved_model: str | None
    usage: dict[str, int] | None
    provider_request_id: str | None = None


class ProviderRequestError(RuntimeError):
    def __init__(self, code: str, detail: str, status: int, retryable: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.retryable = retryable


class ChatProviderPort(Protocol):
    requires_external_transfer: bool

    def test_connection(self, api_key: str) -> ProviderProbeResult: ...

    def generate(self, request: ChatRequest, api_key: str | None = None) -> ChatResponse: ...


__all__ = [
    "CapabilityState",
    "ChatProviderPort",
    "ChatRequest",
    "ChatResponse",
    "ProviderProbeResult",
    "ProviderRequestError",
]
