from __future__ import annotations

import time
from collections.abc import Callable

from mindmate.ai.providers.base import (
    ChatRequest,
    ChatResponse,
    ProviderProbeResult,
)


class MockChatProvider:
    """Deterministic local provider used by the development runtime and tests."""

    requires_external_transfer = False
    provider_name = "MOCK"
    model = "mock-chat-v1"

    def __init__(
        self,
        response_factory: Callable[[ChatRequest], str] | None = None,
        *,
        delay_seconds: float = 0.0,
        failure: Exception | None = None,
    ) -> None:
        self.response_factory = response_factory
        self.delay_seconds = max(0.0, delay_seconds)
        self.failure = failure
        self.calls: list[ChatRequest] = []

    def test_connection(self, api_key: str) -> ProviderProbeResult:
        return ProviderProbeResult(
            requested_model=self.model,
            resolved_model=self.model,
            stream_supported="supported",
            usage_supported="unknown",
            structured_output_supported="unknown",
            provider_request_id=None,
            response_fingerprint="mock",
            usage=None,
        )

    def generate(self, request: ChatRequest, api_key: str | None = None) -> ChatResponse:
        self.calls.append(request)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.failure is not None:
            raise self.failure
        if self.response_factory is not None:
            content = self.response_factory(request)
        else:
            question = next(
                (message["content"] for message in reversed(request.messages) if message["role"] == "user"),
                "",
            )
            content = f"Mock response: {question[:500]}"
        return ChatResponse(
            request_id=request.request_id,
            status="completed",
            content=content,
            finish_reason="stop",
            provider=self.provider_name,
            requested_model=request.model_profile,
            resolved_model=self.model,
            usage=None,
        )


__all__ = ["MockChatProvider"]
