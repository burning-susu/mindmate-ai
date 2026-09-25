from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

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


class ProviderRequestError(RuntimeError):
    def __init__(self, code: str, detail: str, status: int, retryable: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.retryable = retryable


class ChatProviderPort(Protocol):
    def test_connection(self, api_key: str) -> ProviderProbeResult: ...


__all__ = ["CapabilityState", "ChatProviderPort", "ProviderProbeResult", "ProviderRequestError"]
