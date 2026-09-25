from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
SAMPLE_ROOT = REPOSITORY_ROOT / "docs" / "test-data" / "stage5-fixed-ready"
DEFAULT_DATA_DIR = Path(__import__("tempfile").gettempdir()) / "mindmate-ai-stage5-fixed-ready"
DEFAULT_MODEL_CACHE = BACKEND_ROOT / "model-cache" / "manager-validation"
OWNER_MARKER = ".mindmate-stage5-fixed-ready-owner"
OWNER_MARKER_VALUE = "MindMate AI stage 5 fixed READY validation data v1\n"
ORIGIN = "http://127.0.0.1:5173"
TERMINAL_TASK_STATES = {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED"}
EXPECTED_FILES = {
    "服务超时策略.txt": SAMPLE_ROOT / "服务超时策略.txt",
    "相似服务超时策略.txt": SAMPLE_ROOT / "相似服务超时策略.txt",
    "回收站范围验证.txt": SAMPLE_ROOT / "回收站范围验证.txt",
    "阶段5评测_参数记录.txt": SAMPLE_ROOT / "阶段5评测_参数记录.txt",
    "阶段5评测_组件记录.txt": SAMPLE_ROOT / "阶段5评测_组件记录.txt",
    "阶段5评测_冲突甲.txt": SAMPLE_ROOT / "阶段5评测_冲突甲.txt",
    "阶段5评测_冲突乙.txt": SAMPLE_ROOT / "阶段5评测_冲突乙.txt",
    "阶段5评测_短词干扰.txt": SAMPLE_ROOT / "阶段5评测_短词干扰.txt",
    "阶段5评测_回收站.txt": SAMPLE_ROOT / "阶段5评测_回收站.txt",
}
KNOWLEDGE_BASES = {
    "primary": ("第二十五批·固定资料主库", ["服务超时策略.txt", "回收站范围验证.txt"]),
    "decoy": ("第二十五批·相似干扰库", ["相似服务超时策略.txt"]),
    "evaluation": (
        "第二十六批·证据门控评测库",
        [
            "阶段5评测_参数记录.txt",
            "阶段5评测_组件记录.txt",
            "阶段5评测_冲突甲.txt",
            "阶段5评测_冲突乙.txt",
            "阶段5评测_短词干扰.txt",
            "阶段5评测_回收站.txt",
        ],
    ),
    "not_ready_probe": ("第二十五批·未就绪诊断库", []),
}
PRIMARY_QUESTION = "API 单次请求超时时间是多少秒？"
OUT_OF_SCOPE_QUESTION = "南极冰芯中氮同位素的具体丰度百分比是多少？"
TRASH_QUESTION = "回收站范围过滤专属校验编号是什么？"
DECOY_QUESTION = "演练系统 API 单次请求超时时间是多少秒？"


def _require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _headers(key: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Idempotency-Key": key}


def _request_json(response: Any, expected: set[int] | None = None) -> dict[str, Any]:
    allowed_statuses = expected if expected is not None else {200}
    if response.status_code not in allowed_statuses:
        raise RuntimeError(
            f"API {response.request.method} {response.request.url} 返回 {response.status_code}: {response.text[:800]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"API 响应不是 JSON 对象: {response.request.url}")
    return payload


def _ensure_owned_data_dir(data_dir: Path) -> None:
    resolved = data_dir.expanduser().resolve()
    default_user_data = (Path.home() / "AppData" / "Local" / "MindMateAI").resolve()
    _require(
        resolved != default_user_data, "拒绝使用默认用户数据目录；请提供独立的 %TEMP% 数据目录。"
    )
    if resolved.exists():
        marker = resolved / OWNER_MARKER
        if marker.exists():
            _require(
                marker.read_text(encoding="utf-8") == OWNER_MARKER_VALUE,
                "隔离数据目录所有权标记不匹配。",
            )
        else:
            _require(
                not any(resolved.iterdir()),
                "目标目录非空且无本批所有权标记；为保护现有数据，拒绝接管。",
            )
            marker.write_text(OWNER_MARKER_VALUE, encoding="utf-8")
    else:
        resolved.mkdir(parents=True)
        (resolved / OWNER_MARKER).write_text(OWNER_MARKER_VALUE, encoding="utf-8")


def _install_verified_model(data_dir: Path, source_root: Path) -> dict[str, Any]:
    from mindmate.ai.embeddings.manifest import MODEL_DIRECTORY_NAME, MODEL_MANIFEST
    from mindmate.ai.embeddings.model_manager import ModelManager, ModelState

    source = ModelManager(source_root).status(offline=True)
    _require(
        source.state == ModelState.READY
        and source.artifact_fingerprint == MODEL_MANIFEST.fingerprint,
        f"固定模型源不可用或 manifest 校验失败：state={source.state}, error={source.error_code}。未下载模型。",
    )
    model_root = data_dir / "models"
    destination = model_root / MODEL_DIRECTORY_NAME / MODEL_MANIFEST.fingerprint
    if destination.exists():
        copied = ModelManager(model_root).status(offline=True)
        _require(
            copied.state == ModelState.READY, f"隔离数据根中的模型校验失败：{copied.error_code}。"
        )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ModelManager(source_root).install_directory, destination)
        copied = ModelManager(model_root).status(offline=True)
        _require(copied.state == ModelState.READY, f"模型复制后校验失败：{copied.error_code}。")
    return {
        "state": "READY",
        "base_model_id": MODEL_MANIFEST.base_model_id,
        "base_revision": MODEL_MANIFEST.base_revision,
        "artifact_repository_id": MODEL_MANIFEST.artifact_repository_id,
        "artifact_revision": MODEL_MANIFEST.artifact_revision,
        "license": MODEL_MANIFEST.license,
        "artifact_fingerprint": MODEL_MANIFEST.fingerprint,
        "total_size_bytes": MODEL_MANIFEST.total_size_bytes,
        "source_cache": "backend/model-cache/manager-validation",
        "network_required": False,
        "download_performed": False,
        "isolated_copy_verified": True,
        "inference": "real ONNX Runtime CPU; no Mock embedding injection",
    }


def _wait_for_task(
    client: TestClient, task_id: str, *, timeout_seconds: float = 60
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        task = _request_json(client.get(f"/api/v1/tasks/{task_id}"))
        if task.get("status") in TERMINAL_TASK_STATES:
            _require(
                task["status"] == "COMPLETED",
                f"持久任务失败：{json.dumps(task, ensure_ascii=False)}",
            )
            return task
        time.sleep(0.1)
    raise RuntimeError(f"等待任务 {task_id} 超时。")


def _ensure_knowledge_base(client: TestClient, name: str) -> dict[str, Any]:
    listed = _request_json(client.get("/api/v1/knowledge-bases"))
    matches = [item for item in listed.get("items", []) if item.get("name") == name]
    _require(len(matches) <= 1, f"隔离目录中发现重复知识库名称：{name}")
    if matches:
        return matches[0]
    created = client.post(
        "/api/v1/knowledge-bases",
        headers=_headers(f"stage5-ready-kb-{hashlib.sha256(name.encode()).hexdigest()[:20]}"),
        json={
            "name": name,
            "description": "固定合成资料的阶段 5 本地验收",
            "icon": "book-open",
            "color": "#176b87",
        },
    )
    return _request_json(created, {201})


def _list_files(client: TestClient) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active = _request_json(client.get("/api/v1/files?sort=name")).get("items", [])
    trash = _request_json(client.get("/api/v1/trash")).get("files", [])
    return active, trash


def _verify_file(app: Any, file_id: str, name: str, content: bytes) -> None:
    from mindmate.infrastructure.models import FileRecord

    with app.state.session_factory() as session:
        record = session.get(FileRecord, file_id)
        _require(record is not None, f"文件记录不存在：{name}")
        _require(record.display_name == name, f"文件名与固定样本不符：{record.display_name}")
        _require(
            record.content_hash == hashlib.sha256(content).hexdigest(),
            f"固定文件内容哈希不符：{name}",
        )


def _ensure_file(client: TestClient, app: Any, name: str, source: Path) -> dict[str, Any]:
    expected = source.read_bytes()
    active, trash = _list_files(client)
    matches = [item for item in [*active, *trash] if item.get("display_name") == name]
    _require(len(matches) <= 1, f"隔离目录中发现重复文件名：{name}")
    if matches:
        record = matches[0]
        _verify_file(app, str(record["file_id"]), name, expected)
        return record

    response = client.post(
        "/api/v1/file-imports",
        headers=_headers(f"stage5-ready-import-{hashlib.sha256(name.encode()).hexdigest()[:20]}"),
        files={"files": (name, expected, "text/plain")},
    )
    body = _request_json(response, {202})
    _wait_for_task(client, str(body["task_id"]))
    imported = _request_json(client.get(f"/api/v1/file-imports/{body['import_id']}"))
    items = imported.get("items", [])
    _require(len(items) == 1 and items[0].get("file_id"), f"固定资料未成功导入：{name}; {items}")
    file_id = str(items[0]["file_id"])
    deadline = time.monotonic() + 60
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = _request_json(client.get(f"/api/v1/files/{file_id}"))
        if detail.get("status") in {"PARSED", "PARSE_FAILED", "IN_TRASH"}:
            break
        time.sleep(0.1)
    _require(
        detail.get("status") == "PARSED",
        f"固定资料解析未成功：{json.dumps(detail, ensure_ascii=False)}",
    )
    _verify_file(app, file_id, name, expected)
    return detail


def _ensure_membership(
    client: TestClient, app: Any, knowledge_base_id: str, file_names: list[str]
) -> None:
    active, trash = _list_files(client)
    records_by_name = {item["display_name"]: item for item in [*active, *trash]}
    member_payload = _request_json(client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/files"))
    member_ids = {str(item["file_id"]) for item in member_payload.get("items", [])}
    missing: list[str] = []
    for name in file_names:
        record = records_by_name.get(name)
        if record is None:
            raise RuntimeError(f"固定资料没有导入：{name}")
        file_id = str(record["file_id"])
        _verify_file(app, file_id, name, EXPECTED_FILES[name].read_bytes())
        if file_id not in member_ids:
            _require(record.get("status") != "IN_TRASH", f"回收站文件尚未进入初次索引：{name}")
            missing.append(file_id)
    if not missing:
        return
    response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/files",
        headers=_headers(
            f"stage5-ready-members-{hashlib.sha256(knowledge_base_id.encode()).hexdigest()[:20]}"
        ),
        json={"file_ids": missing},
    )
    task = _request_json(response, {202})
    _wait_for_task(client, str(task["task_id"]))


def _create_preprocessing_task(app: Any, knowledge_base_id: str) -> str:
    from mindmate.application.index_preprocessing import enqueue_index_preprocessing

    key = f"stage5-fixed-ready-index-{hashlib.sha256(knowledge_base_id.encode()).hexdigest()[:24]}"
    with app.state.session_factory() as session:
        task = enqueue_index_preprocessing(session, knowledge_base_id, key)
        session.commit()
        return str(task.task_id)


def _wait_persisted_task(app: Any, task_id: str, *, timeout_seconds: float = 600) -> dict[str, Any]:
    from mindmate.infrastructure.models import BackgroundTask

    deadline = time.monotonic() + timeout_seconds
    last_print = 0.0
    while time.monotonic() < deadline:
        with app.state.session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None:
                raise RuntimeError(f"持久任务不存在：{task_id}")
            payload = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status,
                "phase": task.phase,
                "progress": task.progress,
                "error_summary": task.error_summary,
                "checkpoint_version": task.checkpoint_version,
                "checkpoint_json": task.checkpoint_json,
            }
        if payload["status"] in TERMINAL_TASK_STATES:
            _require(
                payload["status"] == "COMPLETED",
                f"持久索引任务失败：{json.dumps(payload, ensure_ascii=False)}",
            )
            return payload
        now = time.monotonic()
        if now - last_print > 10:
            print(
                json.dumps(
                    {
                        "waiting_for_task": payload["task_type"],
                        "status": payload["status"],
                        "phase": payload["phase"],
                        "progress": payload["progress"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            last_print = now
        time.sleep(0.2)
    raise RuntimeError(f"等待持久任务超时：{task_id}")


def _find_version_task(app: Any, task_type: str, version_id: str) -> str | None:
    from mindmate.infrastructure.models import BackgroundTask

    with app.state.session_factory() as session:
        tasks = list(
            session.scalars(
                select(BackgroundTask)
                .where(BackgroundTask.task_type == task_type)
                .order_by(BackgroundTask.created_at.desc())
            )
        )
        for task in tasks:
            if isinstance(task.checkpoint_json, dict) and _contains(
                task.checkpoint_json, version_id
            ):
                return str(task.task_id)
    return None


def _enqueue_and_wait_index_stage(
    app: Any,
    knowledge_base_id: str,
    version_id: str,
    *,
    task_type: str,
    status_field: str,
    enqueue: Any,
    key_suffix: str,
) -> None:
    from mindmate.infrastructure.models import IndexVersion

    task_id = _find_version_task(app, task_type, version_id)
    with app.state.session_factory() as session:
        version = session.get(IndexVersion, version_id)
        if version is None:
            raise RuntimeError(f"索引候选不存在：{version_id}")
        stage_status = getattr(version, status_field)
        if stage_status == "COMPLETED":
            return
        if stage_status in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"索引阶段已失败：{task_type}/{stage_status}")
        if task_id is None:
            task = enqueue(
                session,
                version_id,
                f"index-stage:{version_id}:{key_suffix}",
            )
            task_id = str(task.task_id)
            session.commit()
    if task_id is None:
        raise RuntimeError(f"未能建立持久索引任务：{task_type}")
    print(
        json.dumps(
            {"stage_enqueued": task_type, "index_version_id": version_id, "task_id": task_id},
            ensure_ascii=False,
        ),
        flush=True,
    )
    _wait_persisted_task(app, task_id)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        with app.state.session_factory() as session:
            version = session.get(IndexVersion, version_id)
            stage_status = getattr(version, status_field) if version is not None else None
        if stage_status == "COMPLETED":
            return
        if stage_status in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"索引阶段检查点未成功：{task_type}/{stage_status}")
        time.sleep(0.1)
    raise RuntimeError(f"任务完成但阶段检查点未完成：{task_type}/{stage_status}")


def _index_state(app: Any, knowledge_base_id: str) -> dict[str, Any]:
    from mindmate.infrastructure.models import IndexVersion, KnowledgeBase

    with app.state.session_factory() as session:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None:
            raise RuntimeError(f"知识库不存在：{knowledge_base_id}")
        active_version_id = knowledge_base.active_index_version_id
        version = session.get(IndexVersion, active_version_id) if active_version_id else None
        return {
            "status": knowledge_base.status,
            "active_index_version_id": knowledge_base.active_index_version_id,
            "version_status": version.status if version else None,
            "preprocessing_status": version.preprocessing_status if version else None,
            "chunking_status": version.chunking_status if version else None,
            "embedding_status": version.embedding_status if version else None,
            "fts_status": version.fts_status if version else None,
        }


def _index_diagnostics(app: Any, knowledge_base_id: str) -> dict[str, Any]:
    from mindmate.infrastructure.models import (
        BackgroundTask,
        IndexVersion,
        IndexVersionInput,
        KnowledgeBase,
    )

    with app.state.session_factory() as session:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        version = (
            session.get(IndexVersion, knowledge_base.active_index_version_id)
            if knowledge_base and knowledge_base.active_index_version_id
            else None
        )
        tasks = list(session.scalars(select(BackgroundTask).order_by(BackgroundTask.created_at)))
        task_rows = [
            {
                "task_type": task.task_type,
                "status": task.status,
                "phase": task.phase,
                "progress": task.progress,
                "error_summary": task.error_summary,
                "checkpoint_version": task.checkpoint_version,
            }
            for task in tasks
            if isinstance(task.checkpoint_json, dict)
            and (
                task.checkpoint_json.get("knowledge_base_id") == knowledge_base_id
                or task.checkpoint_json.get("index_version_id")
                == (version.index_version_id if version else None)
            )
        ]
        inputs = (
            list(
                session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == version.index_version_id
                    )
                )
            )
            if version
            else []
        )
        return {
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_status": knowledge_base.status if knowledge_base else None,
            "version": {
                "id": version.index_version_id,
                "status": version.status,
                "preprocessing": version.preprocessing_status,
                "chunking": version.chunking_status,
                "embedding": version.embedding_status,
                "fts": version.fts_status,
                "activation_error_code": version.activation_error_code,
            }
            if version
            else None,
            "inputs": [
                {
                    "file_id": item.file_id,
                    "status": item.status,
                    "reason": item.reason_code,
                    "chunk_status": item.chunk_status,
                    "chunk_reason": item.chunk_reason_code,
                    "chunk_count": item.chunk_count,
                    "embedding_status": item.embedding_status,
                    "embedding_reason": item.embedding_reason_code,
                    "embedding_count": item.embedding_count,
                    "fts_status": item.fts_status,
                    "fts_reason": item.fts_reason_code,
                    "fts_count": item.fts_count,
                }
                for item in inputs
            ],
            "tasks": task_rows,
        }


def _ensure_index_ready(
    app: Any, knowledge_base_id: str, *, timeout_seconds: float = 600
) -> dict[str, Any]:
    from mindmate.application.chunking import enqueue_index_chunking
    from mindmate.application.index_embedding import enqueue_index_embedding
    from mindmate.application.index_fts import enqueue_index_fts

    state = _index_state(app, knowledge_base_id)
    if state["status"] == "READY" and state["version_status"] == "READY":
        return state

    preprocess_task_id = _create_preprocessing_task(app, knowledge_base_id)
    preprocess = _wait_persisted_task(app, preprocess_task_id)
    checkpoint = preprocess.get("checkpoint_json")
    version_id = checkpoint.get("index_version_id") if isinstance(checkpoint, dict) else None
    if not isinstance(version_id, str):
        raise RuntimeError(f"预处理任务没有候选版本检查点：{preprocess_task_id}")
    _enqueue_and_wait_index_stage(
        app,
        knowledge_base_id,
        version_id,
        task_type="INDEX_CHUNK",
        status_field="chunking_status",
        enqueue=enqueue_index_chunking,
        key_suffix="chunk",
    )
    _enqueue_and_wait_index_stage(
        app,
        knowledge_base_id,
        version_id,
        task_type="INDEX_EMBED",
        status_field="embedding_status",
        enqueue=enqueue_index_embedding,
        key_suffix="embedding",
    )
    _enqueue_and_wait_index_stage(
        app,
        knowledge_base_id,
        version_id,
        task_type="INDEX_FTS",
        status_field="fts_status",
        enqueue=enqueue_index_fts,
        key_suffix="fts",
    )
    deadline = time.monotonic() + timeout_seconds
    last_print = 0.0
    while time.monotonic() < deadline:
        state = _index_state(app, knowledge_base_id)
        if state["status"] == "READY" and state["version_status"] == "READY":
            return state
        now = time.monotonic()
        if now - last_print > 10:
            print(json.dumps({"waiting_for_ready": knowledge_base_id, **state}, ensure_ascii=False))
            last_print = now
        time.sleep(0.2)
    raise RuntimeError(
        f"READY 等待超时：{json.dumps(_index_diagnostics(app, knowledge_base_id), ensure_ascii=False)}"
    )


def _contains(value: Any, needle: str) -> bool:
    if value == needle:
        return True
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _verify_artifacts(app: Any, knowledge_base_id: str) -> dict[str, Any]:
    from mindmate.ai.embeddings.manifest import MODEL_REVISION
    from mindmate.application.index_embedding import validate_embedding_config
    from mindmate.infrastructure.fts5 import Fts5Projection
    from mindmate.infrastructure.models import (
        BackgroundTask,
        Chunk,
        EmbeddingConfig,
        EmbeddingRecord,
        FtsChunkMap,
        IndexVersion,
        IndexVersionInput,
        KnowledgeBase,
    )
    from mindmate.infrastructure.vector_store import SqliteVecAdapter

    vector_store = SqliteVecAdapter(app.state.settings.vectors_dir)
    with app.state.session_factory() as session:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None or knowledge_base.active_index_version_id is None:
            raise RuntimeError("缺少活动索引版本。")
        version = session.get(IndexVersion, knowledge_base.active_index_version_id)
        if version is None or version.status != "READY":
            raise RuntimeError("活动版本不是 READY。")
        config = session.get(EmbeddingConfig, version.embedding_config_id)
        if config is None or not validate_embedding_config(config):
            raise RuntimeError("Embedding 配置未通过验证。")
        if config.model_revision != MODEL_REVISION:
            raise RuntimeError("活动索引模型 revision 与固定 manifest 不一致。")
        projection = Fts5Projection()
        projection.integrity_check(session)
        projection.consistency_check(session, version.index_version_id)

        inputs = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version.index_version_id
                )
            )
        )
        if not inputs or len(inputs) != version.input_count:
            raise RuntimeError("活动版本输入快照数量不匹配。")
        expected_vector_ids: set[str] = set()
        chunk_total = embedding_total = fts_total = 0
        per_input: list[dict[str, Any]] = []
        for item in inputs:
            _require(
                item.status == "PREPARED",
                f"输入未完成预处理：{item.file_id}/{item.status}/{item.reason_code}",
            )
            _require(
                item.chunk_status == "CHUNKED",
                f"输入未完成 Chunk：{item.file_id}/{item.chunk_status}/{item.chunk_reason_code}",
            )
            _require(
                item.embedding_status == "EMBEDDED",
                f"输入未完成 Embedding：{item.file_id}/{item.embedding_status}/{item.embedding_reason_code}",
            )
            _require(
                item.fts_status == "INDEXED",
                f"输入未完成 FTS：{item.file_id}/{item.fts_status}/{item.fts_reason_code}",
            )
            chunks = list(
                session.scalars(
                    select(Chunk).where(
                        Chunk.file_id == item.file_id,
                        Chunk.parse_revision_id == item.parse_revision_id,
                        Chunk.chunking_config_id == version.chunking_config_id,
                        Chunk.invalidated_at.is_(None),
                    )
                )
            )
            _require(len(chunks) == item.chunk_count, f"Chunk 数量不匹配：{item.file_id}")
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            records = (
                list(
                    session.scalars(
                        select(EmbeddingRecord).where(
                            EmbeddingRecord.chunk_id.in_(chunk_ids),
                            EmbeddingRecord.embedding_config_id == version.embedding_config_id,
                            EmbeddingRecord.invalidated_at.is_(None),
                        )
                    )
                )
                if chunk_ids
                else []
            )
            _require(
                len(records) == item.embedding_count
                and all(record.status == "READY" for record in records),
                f"Embedding 数量或状态不匹配：{item.file_id}",
            )
            for record in records:
                actual = vector_store.get(
                    embedding_config_id=version.embedding_config_id,
                    index_version_id=version.index_version_id,
                    vector_store_record_id=record.vector_store_record_id,
                )
                if actual is None:
                    raise RuntimeError(f"sqlite-vec 向量缺失：{record.vector_store_record_id}")
                vector, actual_chunk_id, actual_hash = actual
                if actual_hash != record.vector_hash:
                    raise RuntimeError(
                        f"sqlite-vec 向量哈希不一致：{record.vector_store_record_id}"
                    )
                vector_is_valid = bool(
                    actual_chunk_id in set(chunk_ids)
                    and vector.shape == (512,)
                    and np.isfinite(vector).all()
                    and abs(float(np.linalg.norm(vector)) - 1.0) < 1e-4
                )
                _require(
                    vector_is_valid,
                    f"sqlite-vec 向量维度、值或范数错误：{record.vector_store_record_id}",
                )
                expected_vector_ids.add(record.vector_store_record_id)
            mappings = list(
                session.scalars(
                    select(FtsChunkMap).where(
                        FtsChunkMap.index_version_id == version.index_version_id,
                        FtsChunkMap.file_id == item.file_id,
                    )
                )
            )
            _require(
                len(mappings) == item.fts_count == len(chunks),
                f"FTS 映射数量不匹配：{item.file_id}",
            )
            chunk_total += len(chunks)
            embedding_total += len(records)
            fts_total += len(mappings)
            per_input.append(
                {
                    "file_id": item.file_id,
                    "prepared": item.status,
                    "chunk_status": item.chunk_status,
                    "chunk_count": len(chunks),
                    "embedding_status": item.embedding_status,
                    "embedding_count": len(records),
                    "fts_status": item.fts_status,
                    "fts_count": len(mappings),
                }
            )

        actual_vector_ids = vector_store.list_record_ids(
            version.embedding_config_id, version.index_version_id
        )
        _require(
            actual_vector_ids == expected_vector_ids,
            "sqlite-vec 记录集合与活动版本 EmbeddingRecord 不一致。",
        )
        tasks = list(session.scalars(select(BackgroundTask).order_by(BackgroundTask.created_at)))
        stage_tasks = [
            task
            for task in tasks
            if isinstance(task.checkpoint_json, dict)
            and _contains(task.checkpoint_json, version.index_version_id)
            and task.task_type in {"INDEX_PREPROCESS", "INDEX_CHUNK", "INDEX_EMBED", "INDEX_FTS"}
        ]
        task_types = {task.task_type for task in stage_tasks}
        _require(
            {"INDEX_PREPROCESS", "INDEX_CHUNK", "INDEX_EMBED", "INDEX_FTS"}.issubset(task_types),
            f"阶段任务检查点缺失：{task_types}",
        )
        _require(
            all(task.status == "COMPLETED" for task in stage_tasks),
            "存在未完成或失败的阶段任务检查点。",
        )
        checkpoints = [
            {
                "task_type": task.task_type,
                "status": task.status,
                "phase": task.phase,
                "progress": task.progress,
                "checkpoint_version": task.checkpoint_version,
            }
            for task in stage_tasks
        ]
        return {
            "index_version_id": version.index_version_id,
            "version_status": version.status,
            "preprocessing_status": version.preprocessing_status,
            "chunking_status": version.chunking_status,
            "embedding_status": version.embedding_status,
            "fts_status": version.fts_status,
            "input_count": len(inputs),
            "chunk_count": chunk_total,
            "embedding_count": embedding_total,
            "vector_record_count": len(actual_vector_ids),
            "fts_mapping_count": fts_total,
            "fts_integrity_check": "passed",
            "fts_scope_consistency_check": "passed",
            "vector_hash_dimension_finite_value_and_unit_norm_checks": "passed",
            "inputs": per_input,
            "task_checkpoints": checkpoints,
        }


def _query(client: TestClient, knowledge_base_id: str, question: str, key: str) -> dict[str, Any]:
    return _request_json(
        client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests",
            headers=_headers(f"stage5-ready-query-{key}"),
            json={"question": question},
        )
    )


def _assert_no_answer_or_citation(payload: dict[str, Any]) -> None:
    _require(
        not any(key in payload for key in ("answer", "citations", "citation_ids")),
        "只读检索 API 不应生成回答或引用编号。",
    )


def _resource_counts(app: Any) -> dict[str, Any]:
    from mindmate.infrastructure.models import BackgroundTask, FileRecord, KnowledgeBase

    with app.state.session_factory() as session:
        task_types = session.execute(
            select(BackgroundTask.task_type, func.count()).group_by(BackgroundTask.task_type)
        ).all()
        return {
            "files": int(session.scalar(select(func.count()).select_from(FileRecord)) or 0),
            "knowledge_bases": int(
                session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
            ),
            "tasks": int(session.scalar(select(func.count()).select_from(BackgroundTask)) or 0),
            "tasks_by_type": {str(task_type): int(count) for task_type, count in task_types},
        }


def _ensure_dataset(client: TestClient, app: Any) -> dict[str, Any]:
    kb_rows = {
        key: _ensure_knowledge_base(client, name) for key, (name, _files) in KNOWLEDGE_BASES.items()
    }
    file_rows = {
        name: _ensure_file(client, app, name, path) for name, path in EXPECTED_FILES.items()
    }
    for key, (_name, file_names) in KNOWLEDGE_BASES.items():
        _ensure_membership(client, app, str(kb_rows[key]["knowledge_base_id"]), file_names)
    return {"knowledge_bases": kb_rows, "files": file_rows}


def _ensure_trashed(client: TestClient, app: Any, file_id: str, name: str) -> None:
    _active, trashed = _list_files(client)
    if any(item.get("file_id") == file_id for item in trashed):
        return
    detail = _request_json(client.get(f"/api/v1/files/{file_id}"))
    response = client.delete(
        f"/api/v1/files/{file_id}?expected_version={detail['row_version']}",
        headers=_headers(f"stage5-ready-trash-{hashlib.sha256(file_id.encode()).hexdigest()[:20]}"),
    )
    trashed_file = _request_json(response)
    _require(trashed_file.get("status") == "IN_TRASH", f"回收站 API 未完成软删除：{name}")
    _verify_file(app, file_id, name, EXPECTED_FILES[name].read_bytes())


def run(data_dir: Path, model_cache: Path) -> dict[str, Any]:
    from mindmate.ai.embeddings.model_manager import ModelManager
    from mindmate.config import Settings
    from mindmate.main import create_app

    for name, path in EXPECTED_FILES.items():
        _require(path.is_file(), f"固定样本缺失：{path}")
        _require(path.suffix.lower() in {".txt", ".md"}, f"固定样本格式不支持：{name}")
    _ensure_owned_data_dir(data_dir)
    resolved_data_dir = data_dir.expanduser().resolve()
    model_report = _install_verified_model(resolved_data_dir, model_cache)
    model_status = ModelManager(resolved_data_dir / "models").status(offline=True)
    _require(str(model_status.state) == "READY", f"隔离运行模型不可用：{model_status.error_code}")

    settings = Settings(data_dir=resolved_data_dir, env="development", provider_mode="mock")
    app = create_app(settings)
    report: dict[str, Any] = {
        "schema_version": 1,
        "real_model": model_report,
        "provider_mode": "mock",
        "deepseek_called": False,
        "sample_root": "docs/test-data/stage5-fixed-ready",
        "isolated_data_dir": "%TEMP%/mindmate-ai-stage5-fixed-ready",
    }
    with TestClient(app, base_url="http://127.0.0.1") as client:
        session = _request_json(client.post("/api/v1/system/session", headers={"Origin": ORIGIN}))
        _require(session.get("status") == "ready", "无法建立隔离实例本地会话。")
        dataset = _ensure_dataset(client, app)
        primary_id = str(dataset["knowledge_bases"]["primary"]["knowledge_base_id"])
        decoy_id = str(dataset["knowledge_bases"]["decoy"]["knowledge_base_id"])
        evaluation_id = str(dataset["knowledge_bases"]["evaluation"]["knowledge_base_id"])
        not_ready_id = str(dataset["knowledge_bases"]["not_ready_probe"]["knowledge_base_id"])
        not_ready_check = _query(client, not_ready_id, PRIMARY_QUESTION, "not-ready")
        _assert_no_answer_or_citation(not_ready_check)
        _require(
            not_ready_check.get("status") == "unavailable"
            and not_ready_check.get("retrieval_error_code") == "INDEX_VERSION_NOT_AVAILABLE"
            and not_ready_check.get("candidates") == [],
            f"未就绪索引未明确失败：{not_ready_check}",
        )

        for key in ("primary", "decoy", "evaluation"):
            kb_id = str(dataset["knowledge_bases"][key]["knowledge_base_id"])
            _ensure_index_ready(app, kb_id)

        artifacts = {
            key: _verify_artifacts(app, str(dataset["knowledge_bases"][key]["knowledge_base_id"]))
            for key in ("primary", "decoy", "evaluation")
        }
        trash_id = str(dataset["files"]["回收站范围验证.txt"]["file_id"])
        _ensure_trashed(client, app, trash_id, "回收站范围验证.txt")
        evaluation_trash_id = str(dataset["files"]["阶段5评测_回收站.txt"]["file_id"])
        _ensure_trashed(client, app, evaluation_trash_id, "阶段5评测_回收站.txt")

        counts_after_first_pass = _resource_counts(app)
        dataset_second_pass = _ensure_dataset(client, app)
        for key in ("primary", "decoy", "evaluation"):
            _ensure_index_ready(
                app, str(dataset_second_pass["knowledge_bases"][key]["knowledge_base_id"])
            )
        _ensure_trashed(client, app, trash_id, "回收站范围验证.txt")
        _ensure_trashed(client, app, evaluation_trash_id, "阶段5评测_回收站.txt")
        counts_after_second_pass = _resource_counts(app)
        _require(
            counts_after_second_pass == counts_after_first_pass,
            f"重复运行创建了新记录：before={counts_after_first_pass}; after={counts_after_second_pass}",
        )
        _require(
            all(
                str(dataset_second_pass["knowledge_bases"][key]["knowledge_base_id"])
                == str(dataset["knowledge_bases"][key]["knowledge_base_id"])
                for key in ("primary", "decoy", "evaluation")
            ),
            "重复运行创建了新知识库。",
        )

        primary_result = _query(client, primary_id, PRIMARY_QUESTION, "primary")
        _assert_no_answer_or_citation(primary_result)
        _require(
            primary_result.get("index_version_id") == artifacts["primary"]["index_version_id"],
            "检索 API 未读取已核验的当前活动 READY 版本。",
        )
        primary_candidates = primary_result.get("candidates", [])
        _require(0 < len(primary_candidates) <= 8, "主库候选数量不在 1..8 范围内。")
        _require(
            primary_result.get("status") in {"supported", "insufficient"},
            f"真实检索返回了不可用状态：{primary_result}",
        )
        _require(
            all(item.get("file_name") == "服务超时策略.txt" for item in primary_candidates),
            "主库候选泄漏到其他资料或知识库。",
        )
        _require(
            any(
                "30 秒" in item.get("excerpt", "") and item.get("location", {}).get("line_start")
                for item in primary_candidates
            ),
            "候选摘录或真实行号与固定原文不符。",
        )

        decoy_result = _query(client, decoy_id, DECOY_QUESTION, "decoy")
        _assert_no_answer_or_citation(decoy_result)
        _require(
            decoy_result.get("status") in {"supported", "insufficient"}
            and decoy_result.get("candidates"),
            f"相似干扰库没有独立可验证候选：{decoy_result}",
        )
        _require(
            all(
                item.get("file_name") == "相似服务超时策略.txt"
                and "47 秒" in item.get("excerpt", "")
                for item in decoy_result["candidates"]
            ),
            "干扰库内容或候选范围错误。",
        )

        trash_result = _query(client, primary_id, TRASH_QUESTION, "trash")
        _assert_no_answer_or_citation(trash_result)
        _require(
            trash_id not in {item.get("file_id") for item in trash_result.get("candidates", [])},
            "检索 API 泄漏回收站文件。",
        )
        _require(
            all(
                item.get("file_name") != "回收站范围验证.txt"
                and "TRASH-9274" not in item.get("excerpt", "")
                for item in trash_result.get("candidates", [])
            ),
            "检索 API 泄漏回收站文件名或内容。",
        )

        outside_result = _query(client, primary_id, OUT_OF_SCOPE_QUESTION, "outside")
        _assert_no_answer_or_citation(outside_result)
        outside_candidates = outside_result.get("candidates", [])
        _require(
            outside_result.get("status") == "insufficient" and len(outside_candidates) <= 8,
            f"资料外问题未严格拒答：{outside_result}",
        )
        primary_file_id = str(dataset["files"]["服务超时策略.txt"]["file_id"])
        _require(
            all(item.get("file_id") == primary_file_id for item in outside_candidates),
            "资料外问题候选越出了当前主库范围。",
        )

        final_kbs = {
            key: _index_state(app, str(dataset["knowledge_bases"][key]["knowledge_base_id"]))
            for key in ("primary", "decoy", "evaluation")
        }
        _require(
            all(
                value["status"] == "READY" and value["version_status"] == "READY"
                for value in final_kbs.values()
            ),
            f"重复运行后活动索引不再 READY：{final_kbs}",
        )
        report.update(
            {
                "knowledge_bases": {
                    "primary": {
                        "knowledge_base_id": primary_id,
                        "index_version_id": artifacts["primary"]["index_version_id"],
                        "status": final_kbs["primary"]["status"],
                        "version_status": final_kbs["primary"]["version_status"],
                        "verified_artifacts": artifacts["primary"],
                    },
                    "decoy": {
                        "knowledge_base_id": decoy_id,
                        "index_version_id": artifacts["decoy"]["index_version_id"],
                        "status": final_kbs["decoy"]["status"],
                        "version_status": final_kbs["decoy"]["version_status"],
                        "verified_artifacts": artifacts["decoy"],
                    },
                    "evaluation": {
                        "knowledge_base_id": evaluation_id,
                        "index_version_id": artifacts["evaluation"]["index_version_id"],
                        "status": final_kbs["evaluation"]["status"],
                        "version_status": final_kbs["evaluation"]["version_status"],
                        "verified_artifacts": artifacts["evaluation"],
                    },
                    "not_ready_probe": {
                        "knowledge_base_id": not_ready_id,
                        "status": "EMPTY",
                        "indexed": False,
                    },
                },
                "files": {
                    name: {
                        "file_id": dataset["files"][name]["file_id"],
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "trashed": name
                        in {"回收站范围验证.txt", "阶段5评测_回收站.txt"},
                    }
                    for name, path in EXPECTED_FILES.items()
                },
                "not_ready_index_check": not_ready_check,
                "retrieval_checks": {
                    "primary": {
                        "question": PRIMARY_QUESTION,
                        "status": primary_result["status"],
                        "reason_codes": primary_result["reason_codes"],
                        "index_version_id": primary_result["index_version_id"],
                        "candidates": primary_candidates,
                    },
                    "decoy": {
                        "question": DECOY_QUESTION,
                        "status": decoy_result["status"],
                        "reason_codes": decoy_result["reason_codes"],
                        "candidates": decoy_result["candidates"],
                    },
                    "trash": {
                        "question": TRASH_QUESTION,
                        "status": trash_result["status"],
                        "candidate_count": len(trash_result.get("candidates", [])),
                        "trash_file_leaked": False,
                    },
                    "out_of_scope": {
                        "question": OUT_OF_SCOPE_QUESTION,
                        "status": outside_result["status"],
                        "candidate_count": len(outside_result.get("candidates", [])),
                        "reason_codes": outside_result["reason_codes"],
                        "answer_or_citations": False,
                    },
                },
                "idempotency": {
                    "second_pass": "passed",
                    "counts_unchanged": True,
                    "counts": counts_after_second_pass,
                },
            }
        )

    report_path = resolved_data_dir / "stage5-fixed-ready-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and verify isolated fixed READY retrieval data."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    args = parser.parse_args()
    try:
        report = run(args.data_dir, args.model_cache)
    except Exception as error:
        print(f"阶段 5 固定资料准备失败：{error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "report": str(args.data_dir / "stage5-fixed-ready-report.json"),
                "knowledge_bases": report["knowledge_bases"],
                "idempotency": report["idempotency"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
