from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import numpy as np
from fastapi.testclient import TestClient
from numpy.typing import NDArray
from sqlalchemy import select

from mindmate.application.chunking import enqueue_index_chunking
from mindmate.application.files import resolve_storage_path, write_parsed_text
from mindmate.application.index_activation import IndexActivationService
from mindmate.application.index_chunking_worker import IndexChunkingWorker
from mindmate.application.index_embedding import enqueue_index_embedding
from mindmate.application.index_embedding_worker import IndexEmbeddingWorker
from mindmate.application.index_fts import enqueue_index_fts
from mindmate.application.index_fts_worker import IndexFtsWorker
from mindmate.application.index_preprocessing import (
    enqueue_index_preprocessing,
    fingerprint,
    reuse_source_version_id,
)
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Projection
from mindmate.infrastructure.models import (
    BackgroundTask,
    ChunkingConfig,
    ContentObject,
    EmbeddingConfig,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    new_id,
)
from mindmate.infrastructure.vector_store import SqliteVecAdapter
from mindmate.main import create_app

FloatVector = NDArray[np.float32]


class CountingEmbeddingRuntime:
    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []

    def embed_documents(self, texts: Sequence[str]) -> FloatVector:
        self.calls += 1
        self.texts.extend(texts)
        values = np.zeros((len(texts), 512), dtype=np.float32)
        for row, content in zip(values, texts, strict=True):
            row[0] = 1.0
            row[1] = hashlib.sha256(content.encode("utf-8")).digest()[0] / 2550
            row /= np.linalg.norm(row)
        return values


def _headers(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def _wait_task(client: TestClient, task_id: str) -> dict[str, Any]:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        payload = client.get(f"/api/v1/tasks/{task_id}").json()
        if payload["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return payload
        sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


def _create_kb(client: TestClient, key: str) -> str:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=_headers(f"kb-create-{key}"),
        json={"name": f"incremental-{key}"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["knowledge_base_id"])


def _import_file(client: TestClient, key: str, content: bytes) -> str:
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers(f"import-{key}"),
        files={"files": (f"{key}.txt", content, "text/plain")},
    )
    assert response.status_code == 202
    task = _wait_task(client, response.json()["task_id"])
    assert task["status"] == "COMPLETED"
    return str(task["items"][0]["file_id"])


def _add_file(client: TestClient, kb_id: str, file_id: str, key: str) -> None:
    response = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/files",
        headers=_headers(f"member-{key}"),
        json={"file_ids": [file_id]},
    )
    assert response.status_code == 202
    assert _wait_task(client, response.json()["task_id"])["status"] == "COMPLETED"


def _run_preprocess(factory: Any, settings: Settings, kb_id: str, key: str) -> str:
    with factory() as session:
        task = enqueue_index_preprocessing(session, kb_id, f"preprocess-{key}")
        session.commit()
        task_id = task.task_id
    worker = IndexPreprocessingWorker(factory, settings, worker_id=f"preprocess-{key}")
    assert worker._claim_one() == task_id
    worker._process(task_id)
    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        assert task is not None and task.status == "COMPLETED"
        return str(task.checkpoint_json["index_version_id"])


def _run_chunk(factory: Any, settings: Settings, version_id: str, key: str) -> None:
    with factory() as session:
        task = enqueue_index_chunking(session, version_id, f"chunk-{key}")
        session.commit()
        task_id = task.task_id
    worker = IndexChunkingWorker(factory, settings, worker_id=f"chunk-{key}")
    assert worker._claim_one() == task_id
    worker._process(task_id)


def _run_embedding(
    factory: Any, settings: Settings, version_id: str, key: str, runtime: CountingEmbeddingRuntime
) -> None:
    with factory() as session:
        task = enqueue_index_embedding(session, version_id, f"embed-{key}")
        session.commit()
        task_id = task.task_id
    worker = IndexEmbeddingWorker(
        factory,
        settings,
        worker_id=f"embed-{key}",
        embedding_runtime_factory=lambda: runtime,
    )
    assert worker._claim_one() == task_id
    worker._process(task_id)


def _run_fts(factory: Any, settings: Settings, version_id: str, key: str) -> None:
    with factory() as session:
        task = enqueue_index_fts(session, version_id, f"fts-{key}")
        session.commit()
        task_id = task.task_id
    worker = IndexFtsWorker(factory, settings, worker_id=f"fts-{key}")
    assert worker._claim_one() == task_id
    worker._process(task_id)


def _activate(factory: Any, settings: Settings, version_id: str) -> str:
    service = IndexActivationService(factory, SqliteVecAdapter(settings.vectors_dir))
    return service.activate_if_ready(version_id)


def _build_complete(
    client: TestClient,
    factory: Any,
    settings: Settings,
    kb_id: str,
    file_ids: list[str],
    key: str,
    runtime: CountingEmbeddingRuntime,
) -> str:
    for index, file_id in enumerate(file_ids):
        _add_file(client, kb_id, file_id, f"{key}-{index}")
    version_id = _run_preprocess(factory, settings, kb_id, key)
    _run_chunk(factory, settings, version_id, key)
    _run_embedding(factory, settings, version_id, key, runtime)
    _run_fts(factory, settings, version_id, key)
    assert _activate(factory, settings, version_id) == "ACTIVE"
    return version_id


def _runtime(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
        index_activation_worker_poll_seconds=60,
    )
    client = TestClient(create_app(settings), base_url="http://127.0.0.1")
    client.__enter__()
    assert client.post(
        "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
    ).status_code == 200
    return client, settings, cast(Any, client.app).state.session_factory


def test_incremental_add_reuses_unchanged_vectors_and_fts(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "add")
        first = _import_file(client, "add-first", b"unchanged source " * 120)
        second = _import_file(client, "add-second", b"second source " * 120)
        runtime = CountingEmbeddingRuntime()
        old_version = _build_complete(client, factory, settings, kb_id, [first, second], "old", runtime)
        old_calls = runtime.calls

        third = _import_file(client, "add-third", b"new source " * 120)
        _add_file(client, kb_id, third, "add-third")
        new_version = _run_preprocess(factory, settings, kb_id, "new")
        with factory() as session:
            task = session.scalar(
                select(BackgroundTask)
                .where(BackgroundTask.checkpoint_json["index_version_id"].as_string() == new_version)
            )
            assert task is not None
            plan = task.checkpoint_json["incremental_plan"]
            assert plan["mode"] == "INCREMENTAL"
            assert plan["counts"]["unchanged"] == 2
            assert plan["counts"]["new"] == 1
            assert plan["counts"]["reused"] == 2
            assert session.get(KnowledgeBase, kb_id).active_index_version_id == old_version
            reused = list(
                session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == new_version,
                        IndexVersionInput.file_id.in_([first, second]),
                    )
                )
            )
            assert all(reuse_source_version_id(item.reason_code) == old_version for item in reused)

        _run_chunk(factory, settings, new_version, "new")
        _run_embedding(factory, settings, new_version, "new", runtime)
        _run_fts(factory, settings, new_version, "new")
        assert runtime.calls == old_calls + 1
        assert _activate(factory, settings, new_version) == "ACTIVE"
        with factory() as session:
            assert session.get(KnowledgeBase, kb_id).active_index_version_id == new_version
    finally:
        client.__exit__(None, None, None)


def test_incremental_replace_only_recomputes_changed_file(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "replace")
        unchanged = _import_file(client, "replace-unchanged", b"stable source " * 120)
        changed = _import_file(client, "replace-changed", b"old source " * 120)
        runtime = CountingEmbeddingRuntime()
        _build_complete(client, factory, settings, kb_id, [unchanged, changed], "old", runtime)
        old_calls = runtime.calls

        replacement_bytes = b"new replacement source " * 120
        replacement_hash = hashlib.sha256(replacement_bytes).hexdigest()
        with factory() as session:
            record = session.get(FileRecord, changed)
            assert record is not None
            content = session.get(ContentObject, record.content_object_id)
            assert content is not None
            resolve_storage_path(settings, content.storage_relative_path).write_bytes(
                replacement_bytes
            )
            content.sha256 = replacement_hash
            content.byte_size = len(replacement_bytes)
            record.content_hash = replacement_hash
            record.byte_size = len(replacement_bytes)
            record.parse_revision_id = f"{record.parse_revision_id}-v2"
            session.commit()
        write_parsed_text(
            settings,
            changed,
            replacement_hash,
            replacement_bytes.decode("utf-8"),
            {"line_count": 1, "character_count": len(replacement_bytes)},
        )

        new_version = _run_preprocess(factory, settings, kb_id, "replace")
        with factory() as session:
            task = session.scalar(
                select(BackgroundTask)
                .where(BackgroundTask.checkpoint_json["index_version_id"].as_string() == new_version)
            )
            assert task is not None
            plan = task.checkpoint_json["incremental_plan"]
            assert plan["counts"]["changed"] == 1
            assert plan["counts"]["unchanged"] == 1
        _run_chunk(factory, settings, new_version, "replace")
        _run_embedding(factory, settings, new_version, "replace", runtime)
        _run_fts(factory, settings, new_version, "replace")
        assert runtime.calls == old_calls + 1
        assert _activate(factory, settings, new_version) == "ACTIVE"
        with factory() as session:
            version = session.get(IndexVersion, new_version)
            item = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == new_version,
                    IndexVersionInput.file_id == changed,
                )
            )
            assert version is not None and version.status == "READY"
            assert item is not None
            assert item.chunk_status == "CHUNKED"
            assert item.embedding_status == "EMBEDDED"
            assert item.fts_status == "INDEXED"
    finally:
        client.__exit__(None, None, None)


def test_incremental_removed_member_is_excluded_while_old_active_stays_readable(
    tmp_path: Path,
) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "remove")
        kept = _import_file(client, "remove-kept", b"keep source " * 120)
        removed = _import_file(client, "remove-target", b"remove source " * 120)
        runtime = CountingEmbeddingRuntime()
        old_version = _build_complete(
            client, factory, settings, kb_id, [kept, removed], "old", runtime
        )
        response = client.delete(
            f"/api/v1/knowledge-bases/{kb_id}/files/{removed}",
            headers=_headers("remove-member"),
        )
        assert response.status_code == 200
        with factory() as session:
            assert Fts5Projection().match_version(
                session,
                old_version,
                "remove",
                knowledge_base_id=kb_id,
                require_active_version=True,
            ) == []
            assert Fts5Projection().match_version(
                session,
                old_version,
                "keep",
                knowledge_base_id=kb_id,
                require_active_version=True,
            )

        new_version = _run_preprocess(factory, settings, kb_id, "remove")
        with factory() as session:
            task = session.scalar(
                select(BackgroundTask)
                .where(BackgroundTask.checkpoint_json["index_version_id"].as_string() == new_version)
            )
            assert task is not None
            plan = task.checkpoint_json["incremental_plan"]
            assert plan["counts"]["removed"] == 1
            assert session.get(KnowledgeBase, kb_id).active_index_version_id == old_version
            assert session.scalar(
                select(IndexVersionInput.file_id).where(
                    IndexVersionInput.index_version_id == new_version,
                    IndexVersionInput.file_id == removed,
                )
            ) is None
        _run_chunk(factory, settings, new_version, "remove")
        _run_embedding(factory, settings, new_version, "remove", runtime)
        _run_fts(factory, settings, new_version, "remove")
        assert runtime.calls == 2
        assert _activate(factory, settings, new_version) == "ACTIVE"
        with factory() as session:
            rows = list(
                session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == new_version
                    )
                )
            )
            assert [row.file_id for row in rows] == [kept]
    finally:
        client.__exit__(None, None, None)


def test_incremental_cross_kb_reuses_compatible_file_cache(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        source_kb = _create_kb(client, "cross-source")
        target_kb = _create_kb(client, "cross-target")
        file_id = _import_file(client, "cross-file", b"shared file source " * 120)
        runtime = CountingEmbeddingRuntime()
        source_version = _build_complete(
            client, factory, settings, source_kb, [file_id], "cross-source", runtime
        )
        prior_calls = runtime.calls
        _add_file(client, target_kb, file_id, "cross-target")
        target_version = _run_preprocess(factory, settings, target_kb, "cross-target")
        with factory() as session:
            task = session.scalar(
                select(BackgroundTask).where(
                    BackgroundTask.checkpoint_json["index_version_id"].as_string()
                    == target_version
                )
            )
            item = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == target_version
                )
            )
            assert task is not None and item is not None
            assert task.checkpoint_json["incremental_plan"]["mode"] == "FULL"
            assert task.checkpoint_json["incremental_plan"]["counts"]["reused"] == 1
            assert reuse_source_version_id(item.reason_code) == source_version
        _run_chunk(factory, settings, target_version, "cross-target")
        _run_embedding(factory, settings, target_version, "cross-target", runtime)
        _run_fts(factory, settings, target_version, "cross-target")
        assert runtime.calls == prior_calls
        assert _activate(factory, settings, target_version) == "ACTIVE"
        with factory() as session:
            active = session.get(KnowledgeBase, target_kb)
            assert active is not None and active.active_index_version_id == target_version
            row = session.get(
                IndexVersionInput,
                session.scalar(
                    select(IndexVersionInput.index_version_input_id).where(
                        IndexVersionInput.index_version_id == target_version
                    )
                ),
            )
            assert row is not None and row.knowledge_base_file_id
    finally:
        client.__exit__(None, None, None)


def test_incompatible_embedding_dimension_forces_full_rebuild_without_reuse(
    tmp_path: Path,
) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "config-change")
        file_id = _import_file(client, "config-change", b"configuration source " * 120)
        runtime = CountingEmbeddingRuntime()
        active_version_id = _build_complete(
            client, factory, settings, kb_id, [file_id], "config-old", runtime
        )
        with factory() as session:
            active = session.get(IndexVersion, active_version_id)
            base_chunking = session.get(ChunkingConfig, active.chunking_config_id)
            base_embedding = session.get(EmbeddingConfig, active.embedding_config_id)
            assert base_chunking is not None and base_embedding is not None
            chunk_payload = {
                "config_version": "char-v2-fixture",
                "algorithm_id": base_chunking.algorithm_id,
                "measurement_unit": base_chunking.measurement_unit,
                "target_size": 400,
                "min_size": base_chunking.min_size,
                "max_size": base_chunking.max_size,
                "overlap_size": base_chunking.overlap_size,
                "structure_rules_hash": base_chunking.structure_rules_hash,
            }
            changed_chunking = ChunkingConfig(
                chunking_config_id=new_id(),
                **chunk_payload,
                config_fingerprint=fingerprint(chunk_payload),
                created_at=datetime.now(UTC),
            )
            embedding_payload = {
                "config_version": "bge-fixture-v2",
                "provider_type": "LOCAL_ONNX",
                "model_name": "fixture/model-v2",
                "model_revision": "fixture-revision-v2",
                "vector_dimension": 384,
                "normalization": True,
                "distance_metric": "COSINE",
            }
            changed_embedding = EmbeddingConfig(
                embedding_config_id=new_id(),
                **embedding_payload,
                config_fingerprint=fingerprint(embedding_payload),
                created_at=datetime.now(UTC),
            )
            session.add_all([changed_chunking, changed_embedding])
            active.chunking_config_id = changed_chunking.chunking_config_id
            active.embedding_config_id = changed_embedding.embedding_config_id
            session.commit()

        candidate_id = _run_preprocess(factory, settings, kb_id, "config-new")
        with factory() as session:
            task = session.scalar(
                select(BackgroundTask).where(
                    BackgroundTask.checkpoint_json["index_version_id"].as_string()
                    == candidate_id
                )
            )
            item = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == candidate_id
                )
            )
            assert task is not None and item is not None
            plan = task.checkpoint_json["incremental_plan"]
            assert plan["mode"] == "FULL"
            assert plan["reason"] == "CONFIG_INCOMPATIBLE"
            assert plan["counts"]["reused"] == 0
            assert reuse_source_version_id(item.reason_code) is None
            assert session.get(KnowledgeBase, kb_id).active_index_version_id == active_version_id
    finally:
        client.__exit__(None, None, None)


def test_incremental_duplicate_submission_reuses_building_candidate(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "duplicate")
        file_id = _import_file(client, "duplicate-file", b"duplicate source " * 120)
        _add_file(client, kb_id, file_id, "duplicate")
        first = _run_preprocess(factory, settings, kb_id, "duplicate-first")
        with factory() as session:
            original = session.scalar(
                select(BackgroundTask).where(
                    BackgroundTask.checkpoint_json["index_version_id"].as_string() == first
                )
            )
            assert original is not None
            duplicate = enqueue_index_preprocessing(
                session, kb_id, "duplicate-second-idempotency-key"
            )
            assert duplicate.task_id == original.task_id
            session.commit()
        with factory() as session:
            assert session.scalar(select(IndexVersion.index_version_id)) == first
            assert session.scalar(
                select(BackgroundTask.task_id).where(BackgroundTask.task_type == "INDEX_PREPROCESS")
            ) is not None
    finally:
        client.__exit__(None, None, None)
