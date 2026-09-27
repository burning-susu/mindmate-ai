from __future__ import annotations

import json
import re
from threading import Lock
from typing import Any

import httpx


class LearningProviderFixture:
    """Fixed synthetic Chat Completions responses for isolated browser acceptance."""

    def __init__(self) -> None:
        self._calls: list[dict[str, Any]] = []
        self._lock = Lock()
        self._unknown_next_question: set[str] = set()

    def fail_next_question(self, provider: str) -> None:
        with self._lock:
            self._unknown_next_question.add(provider)

    def transport(self, provider: str) -> httpx.MockTransport:
        return httpx.MockTransport(lambda request: self._respond(provider, request))

    def calls(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._calls]

    def _respond(self, provider: str, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        messages = payload.get("messages", [])
        user_text = messages[-1].get("content", "") if messages else ""
        is_feedback = "用户选择" in user_text
        model = str(payload.get("model", ""))
        with self._lock:
            question_number = 1 + sum(
                item["provider"] == provider and item["request_kind"] == "question"
                for item in self._calls
            )
            self._calls.append(
                {
                    "provider": provider,
                    "host": request.url.host,
                    "requested_model": model,
                    "request_kind": "feedback" if is_feedback else "question",
                    "authorization_present": bool(request.headers.get("authorization")),
                }
            )
            request_number = len(self._calls)
            unknown_result = not is_feedback and provider in self._unknown_next_question
            if unknown_result:
                self._unknown_next_question.remove(provider)
        if unknown_result:
            raise httpx.ReadTimeout("fixture simulates an unknown provider result", request=request)
        content = self._feedback(user_text) if is_feedback else self._question(question_number)
        response_model = f"{model}-fixture"
        return httpx.Response(
            200,
            json={
                "id": f"fixture-learning-{request_number}",
                "model": response_model,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 48, "completion_tokens": 24, "total_tokens": 72},
            },
            request=request,
        )

    @staticmethod
    def _question(question_number: int = 1) -> dict[str, Any]:
        if question_number > 1:
            return {
                "prompt_text": "根据资料，Worker 租约时长是多少秒？",
                "options": ["45 秒", "18 秒", "60 秒", "72 秒"],
                "correct_index": 0,
                "knowledge_point": "Worker 租约时长",
                "difficulty": "BASIC",
                "evidence_numbers": [1],
            }
        return {
            "prompt_text": "根据资料，API 单次请求超时时间是多少？",
            "options": ["13 秒", "35 秒", "30 秒", "47 秒"],
            "correct_index": 2,
            "knowledge_point": "API 请求超时",
            "difficulty": "BASIC",
            "evidence_numbers": [1],
        }

    @staticmethod
    def _feedback(user_text: str = "") -> dict[str, Any]:
        values = re.findall(r"(\d+)\s*秒", user_text)
        value = values[-1] if values else "30"
        return {
            "explanation": f"资料明确记载该项时长为 {value} 秒。",
            "strengths": "已提交选择",
            "missing_points": "",
            "next_step": "回看超时处理规则",
            "evidence_numbers": [1],
        }
