"""Audit real local retrieval and Mock Provider calls in prepared stage 5 demo data."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from mindmate.ai.embeddings.model_manager import ModelManager, ModelState
from mindmate.ai.providers.mock import MockChatProvider
from mindmate.config import Settings
from mindmate.main import create_app

POSITIVE_QUESTION = "API 单次请求超时时间是多少秒？"
NEGATIVE_QUESTION = "南极冰芯中氮同位素的具体丰度百分比是多少？"
ORIGIN = "http://127.0.0.1:5173"


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def wait_operation(client: TestClient, operation_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/ai-operations/{operation_id}")
        require(response.status_code == 200, response.text)
        operation = response.json()
        if operation["status"] not in {"QUEUED", "RUNNING", "STOPPING"}:
            return operation
        time.sleep(0.05)
    raise RuntimeError(f"Operation 未在 30 秒内完成：{operation_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    require((data_dir / ".mindmate-stage5-fixed-ready-owner").is_file(), "缺少固定 Demo 目录所有权标记。")
    prepared = json.loads((data_dir / "stage5-fixed-ready-report.json").read_text(encoding="utf-8"))
    knowledge_base = prepared["knowledge_bases"]["primary"]
    knowledge_base_id = knowledge_base["knowledge_base_id"]
    index_version_id = knowledge_base["index_version_id"]
    model_status = ModelManager(data_dir / "models").status(offline=True)
    require(model_status.state is ModelState.READY, f"模型不可用：{model_status.error_code}")

    settings = Settings(data_dir=data_dir, env="development", provider_mode="mock")
    app = create_app(settings)
    provider = MockChatProvider()
    app.state.chat_provider = provider
    with TestClient(app, base_url="http://127.0.0.1") as client:
        session = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        require(session.status_code == 200, session.text)
        retrievals = {}
        for key, question in (("positive", POSITIVE_QUESTION), ("negative", NEGATIVE_QUESTION)):
            response = client.post(
                f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests",
                headers={"Origin": ORIGIN, "Idempotency-Key": f"stage35-retrieval-{uuid4()}"},
                json={"question": question},
            )
            require(response.status_code == 200, response.text)
            retrievals[key] = response.json()
        require(retrievals["positive"]["status"] == "supported", "真实正例检索未通过证据门控。")
        require(retrievals["negative"]["status"] == "insufficient", "真实负例未被判资料不足。")
        require(retrievals["positive"]["index_version_id"] == index_version_id, "检索索引版本不一致。")

        operations = {}
        for key, question in (("positive", POSITIVE_QUESTION), ("negative", NEGATIVE_QUESTION)):
            response = client.post(
                "/api/v1/conversations",
                headers={"Origin": ORIGIN, "Idempotency-Key": f"stage35-real-{uuid4()}"},
                json={
                    "mode": "KNOWLEDGE_CHAT",
                    "source_scope": {"scope_type": "KNOWLEDGE_BASE", "knowledge_base_id": knowledge_base_id},
                    "first_message": question,
                    "client_request_id": f"stage35-real-{uuid4()}",
                },
            )
            require(response.status_code == 202, response.text)
            operations[key] = wait_operation(client, response.json()["operation_id"])
            if key == "positive":
                require(len(provider.calls) == 1, "正例未调用一次 Mock Provider。")
            else:
                require(len(provider.calls) == 1, "负例错误调用了 Mock Provider。")

    positive = operations["positive"]
    negative = operations["negative"]
    require(positive["status"] == "COMPLETED", "正例 Operation 未完成。")
    require(len(positive["answer_version"]["citations"]) > 0, "正例没有 Citation。")
    require(negative["status"] == "COMPLETED", "负例 Operation 未完成。")
    require(negative["error_code"] == "EVIDENCE_INSUFFICIENT", "负例状态不是资料不足。")
    require(negative["answer_version"]["citations"] == [], "负例错误产生 Citation。")
    output = {
        "model_state": model_status.state.value,
        "artifact_fingerprint": model_status.artifact_fingerprint,
        "knowledge_base_id": knowledge_base_id,
        "index_version_id": index_version_id,
        "provider": "MockChatProvider",
        "provider_calls_after_positive": 1,
        "provider_calls_after_negative": len(provider.calls),
        "retrieval": {
            key: {
                "status": value["status"],
                "index_version_id": value["index_version_id"],
                "reason_codes": value["reason_codes"],
                "candidates": [
                    {
                        "file_name": candidate["file_name"],
                        "chunk_id": candidate["chunk_id"],
                        "fts_rank": candidate["fts_rank"],
                        "vector_rank": candidate["vector_rank"],
                        "location": candidate["location"],
                    }
                    for candidate in value["candidates"]
                ],
            }
            for key, value in retrievals.items()
        },
        "positive": {
            "operation_status": positive["status"],
            "citation_count": len(positive["answer_version"]["citations"]),
        },
        "negative": {
            "operation_status": negative["status"],
            "error_code": negative["error_code"],
            "citation_count": 0,
            "provider_calls_for_negative": 0,
        },
    }
    path = data_dir / "evidence" / "controlled-provider-audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "report": str(path), **output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
