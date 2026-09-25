from __future__ import annotations

import time
from collections.abc import Callable, Iterator

from mindmate.ai.providers.base import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
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
        stream_chunk_size: int = 12,
    ) -> None:
        self.response_factory = response_factory
        self.delay_seconds = max(0.0, delay_seconds)
        self.failure = failure
        self.stream_chunk_size = max(1, stream_chunk_size)
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

    def _content(self, request: ChatRequest) -> str:
        if self.response_factory is not None:
            return self.response_factory(request)
        question = next(
            (message["content"] for message in reversed(request.messages) if message["role"] == "user"),
            "",
        )
        return f"Mock response: {question[:500]}"

    def generate_stream(
        self, request: ChatRequest, api_key: str | None = None
    ) -> Iterator[ChatStreamChunk]:
        """Yield deterministic bounded chunks for the local development runtime."""
        self.calls.append(request)
        if self.failure is not None:
            raise self.failure
        content = self._content(request)
        for start in range(0, len(content), self.stream_chunk_size):
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
            yield ChatStreamChunk(
                request_id=request.request_id,
                delta=content[start : start + self.stream_chunk_size],
                provider=self.provider_name,
                requested_model=request.model_profile,
                resolved_model=self.model,
            )
        yield ChatStreamChunk(
            request_id=request.request_id,
            finish_reason="stop",
            provider=self.provider_name,
            requested_model=request.model_profile,
            resolved_model=self.model,
            done=True,
        )


__all__ = ["MockChatProvider"]
