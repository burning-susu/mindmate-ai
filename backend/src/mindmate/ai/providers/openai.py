from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator

import httpx

from mindmate.ai.providers.base import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    ProviderProbeResult,
    ProviderRequestError,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-6-sol"
OPENAI_REASONING_EFFORT = "none"
PROBE_TEXT = "请只回复：连接测试成功"
PROBE_MAX_COMPLETION_TOKENS = 32
MAX_GENERATION_RESPONSE_BYTES = 512 * 1024
_VISIBLE_PART_TYPES = {"text", "output_text"}


class OpenAIChatProvider:
    """Chat Completions adapter for the fixed official gpt-6-sol model.

    The outbound payload does not copy DeepSeek sampling fields. Reasoning
    fields stay out of the answer text. The browser never sees raw SSE.
    """

    requires_external_transfer = True
    provider_name = "OPENAI"

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = OPENAI_BASE_URL
        self.model = OPENAI_MODEL
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def test_connection(self, api_key: str) -> ProviderProbeResult:
        if not api_key:
            raise ProviderRequestError("PROVIDER_KEY_MISSING", "尚未配置 OpenAI API Key。", 409)
        payload = self._payload(
            [{"role": "user", "content": PROBE_TEXT}],
            max_completion_tokens=PROBE_MAX_COMPLETION_TOKENS,
            stream=True,
        )
        resolved_model: str | None = None
        provider_request_id: str | None = None
        usage: dict[str, int] | None = None
        event_count = 0
        saw_done = False
        saw_json = False
        saw_content = False
        finish_reasons: list[str] = []
        try:
            with self._client() as client:
                with client.stream(
                    "POST",
                    "/chat/completions",
                    headers=self._headers(api_key, stream=True),
                    json=payload,
                ) as response:
                    self._ensure_success(response)
                    for data in self._iter_sse(response, limit=64 * 1024, line_limit=16 * 1024):
                        if data == "[DONE]":
                            saw_done = True
                            continue
                        body = self._json_object(data)
                        saw_json = True
                        event_count += 1
                        resolved_model = self._model_field(body) or resolved_model
                        provider_request_id = self._request_id(body) or provider_request_id
                        normalized = self._normalize_usage(body.get("usage"))
                        if normalized is not None:
                            usage = normalized
                        choice = self._choice(body)
                        if choice is None:
                            continue
                        delta = choice.get("delta")
                        text = self._visible_text(delta.get("content") if isinstance(delta, dict) else None)
                        saw_content = saw_content or bool(text)
                        finish_reason = choice.get("finish_reason")
                        if isinstance(finish_reason, str):
                            finish_reasons.append(finish_reason[:80])
        except ProviderRequestError:
            raise
        except httpx.HTTPError as exc:
            raise self._network_error(exc) from exc
        if not saw_json or not saw_content or not saw_done:
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "OpenAI 返回了不完整的连接测试响应。", 502
            )
        fingerprint_payload = {
            "model": resolved_model,
            "event_count": event_count,
            "finish_reasons": finish_reasons,
            "usage_keys": sorted(usage or {}),
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return ProviderProbeResult(
            requested_model=self.model,
            resolved_model=resolved_model,
            stream_supported="supported",
            usage_supported="supported" if usage is not None else "unknown",
            structured_output_supported="unknown",
            provider_request_id=provider_request_id,
            response_fingerprint=fingerprint,
            usage=usage,
        )

    def generate(self, request: ChatRequest, api_key: str | None = None) -> ChatResponse:
        if not api_key:
            raise ProviderRequestError("PROVIDER_KEY_MISSING", "尚未配置 OpenAI API Key。", 409)
        payload = self._payload(
            self._messages(request),
            max_completion_tokens=request.max_output_tokens,
            stream=False,
        )
        try:
            with self._client() as client:
                response = client.post(
                    "/chat/completions",
                    headers=self._headers(api_key, stream=False),
                    json=payload,
                )
                self._ensure_success(response)
                if len(response.content) > MAX_GENERATION_RESPONSE_BYTES:
                    raise ProviderRequestError(
                        "PROVIDER_RESPONSE_TOO_LARGE",
                        "OpenAI 返回的聊天响应超过本地安全上限。",
                        502,
                    )
                body = self._json_object(response.text)
        except ProviderRequestError:
            raise
        except httpx.HTTPError as exc:
            raise self._network_error(exc) from exc
        choice = self._choice(body)
        message = choice.get("message") if choice is not None else None
        content = self._visible_text(message.get("content") if isinstance(message, dict) else None)
        if not content.strip():
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "OpenAI 返回的生成响应缺少回答正文。", 502
            )
        finish_reason = choice.get("finish_reason") if choice is not None else None
        return ChatResponse(
            request_id=request.request_id,
            status="completed",
            content=content,
            finish_reason=finish_reason[:80] if isinstance(finish_reason, str) else None,
            provider=self.provider_name,
            requested_model=self.model,
            resolved_model=self._model_field(body),
            usage=self._normalize_usage(body.get("usage")),
            provider_request_id=self._request_id(body),
        )

    def generate_stream(
        self, request: ChatRequest, api_key: str | None = None
    ) -> Iterator[ChatStreamChunk]:
        if not api_key:
            raise ProviderRequestError("PROVIDER_KEY_MISSING", "尚未配置 OpenAI API Key。", 409)
        payload = self._payload(
            self._messages(request),
            max_completion_tokens=request.max_output_tokens,
            stream=True,
        )
        resolved_model: str | None = None
        provider_request_id: str | None = None
        usage: dict[str, int] | None = None
        saw_content = False
        saw_done = False
        try:
            with self._client() as client:
                with client.stream(
                    "POST",
                    "/chat/completions",
                    headers=self._headers(api_key, stream=True),
                    json=payload,
                ) as response:
                    self._ensure_success(response)
                    for data in self._iter_sse(response):
                        if data == "[DONE]":
                            saw_done = True
                            yield ChatStreamChunk(
                                request_id=request.request_id,
                                provider=self.provider_name,
                                requested_model=self.model,
                                resolved_model=resolved_model,
                                usage=usage,
                                provider_request_id=provider_request_id,
                                done=True,
                            )
                            break
                        body = self._json_object(data)
                        resolved_model = self._model_field(body) or resolved_model
                        provider_request_id = self._request_id(body) or provider_request_id
                        normalized = self._normalize_usage(body.get("usage"))
                        if normalized is not None:
                            usage = normalized
                        choice = self._choice(body)
                        if choice is None:
                            if usage is not None:
                                yield ChatStreamChunk(
                                    request_id=request.request_id,
                                    provider=self.provider_name,
                                    requested_model=self.model,
                                    resolved_model=resolved_model,
                                    usage=usage,
                                    provider_request_id=provider_request_id,
                                )
                            continue
                        delta = choice.get("delta")
                        text = self._visible_text(delta.get("content") if isinstance(delta, dict) else None)
                        finish_reason = choice.get("finish_reason")
                        finish_reason = finish_reason[:80] if isinstance(finish_reason, str) else None
                        if text:
                            saw_content = True
                        if text or finish_reason or usage is not None:
                            yield ChatStreamChunk(
                                request_id=request.request_id,
                                delta=text,
                                finish_reason=finish_reason,
                                provider=self.provider_name,
                                requested_model=self.model,
                                resolved_model=resolved_model,
                                usage=usage,
                                provider_request_id=provider_request_id,
                            )
                    if not saw_done or not saw_content:
                        raise ProviderRequestError(
                            "PROVIDER_INVALID_RESPONSE", "OpenAI 返回了不完整的生成响应。", 502
                        )
        except ProviderRequestError:
            raise
        except httpx.HTTPError as exc:
            raise self._network_error(exc) from exc

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            verify=True,
            transport=self.transport,
        )

    def _payload(
        self,
        messages: list[dict[str, str]],
        *,
        max_completion_tokens: int,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max(1, int(max_completion_tokens)),
            "reasoning_effort": OPENAI_REASONING_EFFORT,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    @staticmethod
    def _messages(request: ChatRequest) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": request.system_instructions}]
        messages.extend(
            {"role": message["role"], "content": message["content"]}
            for message in request.messages
            if message.get("role") in {"user", "assistant"}
        )
        return messages

    @staticmethod
    def _headers(api_key: str, *, stream: bool) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }

    def _ensure_success(self, response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code == 200:
            return
        if 300 <= status_code <= 399:
            raise ProviderRequestError(
                "PROVIDER_REDIRECT_REJECTED", "OpenAI 返回了重定向，已拒绝跟随。", 502
            )
        response.read()
        if status_code in {401, 403}:
            code = "PROVIDER_AUTHENTICATION_FAILED" if status_code == 401 else "PROVIDER_FORBIDDEN"
            detail = (
                "OpenAI API Key 无效或已被拒绝。"
                if status_code == 401
                else "OpenAI 拒绝了这次请求。未改用其他服务。"
            )
            raise ProviderRequestError(code, detail, status_code)
        if status_code == 429:
            raise ProviderRequestError(
                "PROVIDER_RATE_LIMITED", "OpenAI 请求过于频繁或额度受限，请稍后重试。未改用其他服务。", 429, True
            )
        if 500 <= status_code <= 599:
            raise ProviderRequestError(
                "PROVIDER_SERVER_ERROR", "OpenAI 服务暂时不可用，请稍后重试。未改用其他服务。", 502, True
            )
        raise ProviderRequestError("PROVIDER_REQUEST_REJECTED", "OpenAI 拒绝了这次请求。", 502)

    def _iter_sse(
        self,
        response: httpx.Response,
        *,
        limit: int = MAX_GENERATION_RESPONSE_BYTES,
        line_limit: int = 64 * 1024,
    ) -> Iterator[str]:
        response_bytes = 0
        data_lines: list[str] = []
        for raw_line in response.iter_lines():
            line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace")
            response_bytes += len(line.encode("utf-8")) + 1
            if response_bytes > limit or len(line) > line_limit:
                raise ProviderRequestError(
                    "PROVIDER_RESPONSE_TOO_LARGE", "OpenAI 返回的响应超过本地安全上限。", 502
                )
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
                continue
            if not data_lines:
                continue
            data = "\n".join(data_lines).strip()
            data_lines = []
            if data:
                yield data
        if data_lines:
            data = "\n".join(data_lines).strip()
            if data:
                yield data

    @staticmethod
    def _json_object(data: str) -> dict[str, object]:
        try:
            body = json.loads(data)
        except (TypeError, ValueError) as exc:
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "OpenAI 返回了无法识别的响应。", 502
            ) from exc
        if not isinstance(body, dict):
            raise ProviderRequestError("PROVIDER_INVALID_RESPONSE", "OpenAI 返回了无法识别的响应。", 502)
        return body

    @staticmethod
    def _choice(body: dict[str, object]) -> dict[str, object] | None:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return None
        return choices[0]

    @staticmethod
    def _model_field(body: dict[str, object]) -> str | None:
        model = body.get("model")
        return model[:200] if isinstance(model, str) and model else None

    @staticmethod
    def _request_id(body: dict[str, object]) -> str | None:
        response_id = body.get("id")
        return response_id[:128] if isinstance(response_id, str) and response_id else None

    @classmethod
    def _visible_text(cls, content: object) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            part_type = item.get("type")
            if part_type not in _VISIBLE_PART_TYPES and part_type is not None:
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _normalize_usage(value: object) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        usage = {
            key: raw
            for key, raw in value.items()
            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and type(raw) is int
            and raw >= 0
        }
        return usage or None

    @staticmethod
    def _network_error(exc: httpx.HTTPError) -> ProviderRequestError:
        if isinstance(exc, httpx.ConnectTimeout):
            return ProviderRequestError(
                "PROVIDER_CONNECT_TIMEOUT", "连接 OpenAI 超时，请检查网络后重试。未改用其他服务。", 504, True
            )
        if isinstance(exc, httpx.ReadTimeout):
            return ProviderRequestError(
                "PROVIDER_READ_TIMEOUT", "等待 OpenAI 响应超时，请稍后重试。未改用其他服务。", 504, True
            )
        if isinstance(exc, httpx.TimeoutException):
            return ProviderRequestError(
                "PROVIDER_TIMEOUT", "OpenAI 请求超时，请稍后重试。未改用其他服务。", 504, True
            )
        return ProviderRequestError(
            "PROVIDER_NETWORK_ERROR", "无法连接 OpenAI，请检查网络后重试。未改用其他服务。", 502, True
        )


__all__ = [
    "MAX_GENERATION_RESPONSE_BYTES",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
    "OpenAIChatProvider",
    "PROBE_MAX_COMPLETION_TOKENS",
    "PROBE_TEXT",
]
