from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

import httpx

from mindmate.ai.providers.base import (
    ChatRequest,
    ChatResponse,
    ProviderProbeResult,
    ProviderRequestError,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"
PROBE_TEXT = "请只回复：连接测试成功"
PROBE_MAX_OUTPUT_TOKENS = 8
MAX_GENERATION_RESPONSE_BYTES = 512 * 1024


class DeepSeekChatProvider:
    """OpenAI-compatible adapter for explicit probes and bounded chat generation."""

    requires_external_transfer = True
    provider_name = "DEEPSEEK"

    def __init__(
        self,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEEPSEEK_MODEL,
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = self._validate_base_url(base_url)
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @staticmethod
    def _validate_base_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("provider base URL must be an HTTP(S) origin")
        return base_url.rstrip("/")

    def test_connection(self, api_key: str) -> ProviderProbeResult:
        if not api_key:
            raise ProviderRequestError("PROVIDER_KEY_MISSING", "尚未配置 DeepSeek API Key。", 409)

        request_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": PROBE_TEXT}],
            "max_tokens": PROBE_MAX_OUTPUT_TOKENS,
            "temperature": 0,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                with client.stream(
                    "POST", "/chat/completions", headers=headers, json=request_payload
                ) as response:
                    if response.status_code != 200:
                        self._raise_for_status(response)
                    return self._read_stream(response)
        except ProviderRequestError:
            raise
        except httpx.ConnectTimeout as exc:
            raise ProviderRequestError(
                "PROVIDER_CONNECT_TIMEOUT", "连接 DeepSeek 超时，请检查网络后重试。", 504, True
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderRequestError(
                "PROVIDER_READ_TIMEOUT", "等待 DeepSeek 响应超时，请稍后重试。", 504, True
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderRequestError(
                "PROVIDER_TIMEOUT", "DeepSeek 请求超时，请稍后重试。", 504, True
            ) from exc
        except httpx.NetworkError as exc:
            raise ProviderRequestError(
                "PROVIDER_NETWORK_ERROR", "无法连接 DeepSeek，请检查网络后重试。", 502, True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(
                "PROVIDER_NETWORK_ERROR", "DeepSeek 网络请求失败，请稍后重试。", 502, True
            ) from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code in {401, 403}:
            code = "PROVIDER_AUTHENTICATION_FAILED" if status_code == 401 else "PROVIDER_FORBIDDEN"
            detail = "DeepSeek API Key 无效或已被拒绝。" if status_code == 401 else "DeepSeek 拒绝了这次请求。"
            raise ProviderRequestError(code, detail, 401 if status_code == 401 else 403)
        if status_code == 402:
            raise ProviderRequestError(
                "PROVIDER_QUOTA_EXCEEDED", "DeepSeek 账户额度或余额不足，连接测试未完成。", 402
            )
        if status_code == 429:
            raise ProviderRequestError(
                "PROVIDER_RATE_LIMITED", "DeepSeek 请求过于频繁，请稍后重试。", 429, True
            )
        if 500 <= status_code <= 599:
            raise ProviderRequestError(
                "PROVIDER_SERVER_ERROR", "DeepSeek 服务暂时不可用，请稍后重试。", 502, True
            )
        raise ProviderRequestError(
            "PROVIDER_REQUEST_REJECTED", "DeepSeek 拒绝了连接测试请求。", 502
        )

    def _read_stream(self, response: httpx.Response) -> ProviderProbeResult:
        resolved_model: str | None = None
        provider_request_id: str | None = None
        usage: dict[str, int] | None = None
        event_count = 0
        response_bytes = 0
        saw_done = False
        saw_json = False
        saw_content = False
        finish_reasons: list[str] = []
        for line in response.iter_lines():
            response_bytes += len(line.encode("utf-8")) + 1
            if response_bytes > 64 * 1024 or len(line) > 16 * 1024:
                raise ProviderRequestError(
                    "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回的连接测试响应超过安全上限。", 502
                )
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            if data == "[DONE]":
                saw_done = True
                continue
            try:
                payload = json.loads(data)
            except (TypeError, ValueError) as exc:
                raise ProviderRequestError(
                    "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回了无法识别的连接测试响应。", 502
                ) from exc
            if not isinstance(payload, dict):
                raise ProviderRequestError(
                    "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回了无法识别的连接测试响应。", 502
                )
            saw_json = True
            event_count += 1
            model = payload.get("model")
            if isinstance(model, str) and model:
                resolved_model = model[:200]
            response_id = payload.get("id")
            if isinstance(response_id, str) and response_id and len(response_id) <= 128:
                provider_request_id = response_id
            raw_usage = payload.get("usage")
            if isinstance(raw_usage, dict):
                normalized = {
                    key: value
                    for key, value in raw_usage.items()
                    if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(value) is int
                    and value >= 0
                }
                if normalized:
                    usage = normalized
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    delta = first_choice.get("delta")
                    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                        saw_content = saw_content or bool(delta["content"])
                    finish_reason = first_choice.get("finish_reason")
                    if isinstance(finish_reason, str):
                        finish_reasons.append(finish_reason[:80])
        if not saw_json or not saw_content or not saw_done:
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回了不完整的连接测试响应。", 502
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
            raise ProviderRequestError("PROVIDER_KEY_MISSING", "尚未配置 DeepSeek API Key。", 409)
        messages = [{"role": "system", "content": request.system_instructions}]
        messages.extend(
            {"role": message["role"], "content": message["content"]}
            for message in request.messages
            if message.get("role") in {"user", "assistant"}
        )
        payload = {
            "model": request.model_profile,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = client.post("/chat/completions", headers=headers, json=payload)
                if response.status_code != 200:
                    self._raise_for_status(response)
                if len(response.content) > MAX_GENERATION_RESPONSE_BYTES:
                    raise ProviderRequestError(
                        "PROVIDER_RESPONSE_TOO_LARGE",
                        "DeepSeek 返回的普通聊天响应超过本地安全上限。",
                        502,
                    )
                try:
                    body = response.json()
                except (TypeError, ValueError) as exc:
                    raise ProviderRequestError(
                        "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回了无法识别的生成响应。", 502
                    ) from exc
        except ProviderRequestError:
            raise
        except httpx.ConnectTimeout as exc:
            raise ProviderRequestError(
                "PROVIDER_CONNECT_TIMEOUT", "连接 DeepSeek 超时，请检查网络后重试。", 504, True
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderRequestError(
                "PROVIDER_READ_TIMEOUT", "等待 DeepSeek 响应超时，请稍后重试。", 504, True
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderRequestError(
                "PROVIDER_TIMEOUT", "DeepSeek 请求超时，请稍后重试。", 504, True
            ) from exc
        except httpx.NetworkError as exc:
            raise ProviderRequestError(
                "PROVIDER_NETWORK_ERROR", "无法连接 DeepSeek，请检查网络后重试。", 502, True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(
                "PROVIDER_NETWORK_ERROR", "DeepSeek 网络请求失败，请稍后重试。", 502, True
            ) from exc

        if not isinstance(body, dict):
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回了无法识别的生成响应。", 502
            )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回的生成响应缺少回答内容。", 502
            )
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ProviderRequestError(
                "PROVIDER_INVALID_RESPONSE", "DeepSeek 返回的生成响应缺少回答内容。", 502
            )
        finish_reason = choices[0].get("finish_reason")
        finish_reason = finish_reason[:80] if isinstance(finish_reason, str) else None
        usage = self._normalize_usage(body.get("usage"))
        resolved_model = body.get("model")
        resolved_model = resolved_model[:200] if isinstance(resolved_model, str) else None
        provider_request_id = body.get("id")
        provider_request_id = (
            provider_request_id[:128] if isinstance(provider_request_id, str) else None
        )
        return ChatResponse(
            request_id=request.request_id,
            status="completed",
            content=content,
            finish_reason=finish_reason,
            provider=self.provider_name,
            requested_model=request.model_profile,
            resolved_model=resolved_model,
            usage=usage,
            provider_request_id=provider_request_id,
        )

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

__all__ = [
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DeepSeekChatProvider",
    "MAX_GENERATION_RESPONSE_BYTES",
    "PROBE_MAX_OUTPUT_TOKENS",
    "PROBE_TEXT",
]
