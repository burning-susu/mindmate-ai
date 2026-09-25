from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import numpy as np
import pytest
from fastapi.testclient import TestClient
from numpy.typing import NDArray
from sqlalchemy import delete, select, update

from mindmate.ai.embeddings.model_manager import ModelManager, ModelManagerError, ModelState
from mindmate.application.chunking import enqueue_index_chunking
from mindmate.application.index_chunking_worker import IndexChunkingWorker
from mindmate.application.index_embedding import enqueue_index_embedding
from mindmate.application.index_embedding_worker import IndexEmbeddingWorker
from mindmate.application.index_preprocessing import enqueue_index_preprocessing
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.application.tasks import cancel_task, create_task
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    EmbeddingConfig,
    EmbeddingRecord,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from mindmate.infrastructure.vector_store import SqliteVecAdapter
from mindmate.main import create_app

FloatVector = NDArray[np.float32]


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


class FakeEmbeddingRuntime:
    def __init__(self, on_embed: Callable[[], None] | None = None) -> None:
        self.texts: list[str] = []
        self.on_embed = on_embed

    def embed_documents(self, texts: Sequence[str]) -> FloatVector:
        self.texts.extend(texts)
        result = np.zeros((len(texts), 512), dtype=np.float32)
        for index, value in enumerate(texts, 1):
            seed = hashlib.sha256(value.encode("utf-8")).digest()
            result[index - 1, 0] = 1.0
            result[index - 1, 1] = seed[0] / 2550
            result[index - 1] /= np.linalg.norm(result[index - 1])
        if self.on_embed is not None:
            self.on_embed()
        return result


class FakeEmbeddingFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OneFileFailureRuntime(FakeEmbeddingRuntime):
    def embed_documents(self, texts: Sequence[str]) -> FloatVector:
        if any("fail-this-file" in text for text in texts):
            self.texts.extend(texts)
            raise FakeEmbeddingFailure("FIXTURE_EMBEDDING_FAILURE")
        return super().embed_documents(texts)


class MissingModelManager:
    def ensure_installed(self, *, allow_download: bool) -> None:
        assert allow_download is False
        raise ModelManagerError("MODEL_MISSING_OFFLINE")


@pytest.fixture
def embedding_runtime(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_activation_worker_poll_seconds=60,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.post(
            "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
        ).status_code == 200
        yield client, settings, cast(Any, client.app).state.session_factory


def _create_kb(client: TestClient, key: str) -> str:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=_headers(f"kb-{key}"),
        json={"name": f"持久向量-{key}"},
    )
    assert response.status_code == 201
    return response.json()["knowledge_base_id"]


def _import_file(client: TestClient, key: str) -> str:
    content = f"持续可恢复的Embedding内容。{key}".encode()
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers(f"import-{key}"),
        files={"files": (f"{key}.txt", content, "text/plain")},
    )
    assert response.status_code == 202
    imported = _wait_task(client, response.json()["task_id"])
    assert imported["status"] == "COMPLETED"
    return str(imported["items"][0]["file_id"])


def _add_file(client: TestClient, knowledge_base_id: str, file_id: str, key: str) -> None:
    response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/files",
        headers=_headers(f"member-{key}"),
        json={"file_ids": [file_id]},
    )
    assert response.status_code == 202
    assert _wait_task(client, response.json()["task_id"])["status"] == "COMPLETED"


def _build_index(factory, settings: Settings, knowledge_base_id: str, key: str) -> str:
    with factory() as session:
        preprocessing = enqueue_index_preprocessing(
            session, knowledge_base_id, f"preprocess-{key}"
        )
        session.commit()
        preprocess_id = preprocessing.task_id
    preprocess_worker = IndexPreprocessingWorker(
        factory, settings, worker_id=f"preprocess-worker-{key}"
    )
    assert preprocess_worker._claim_one() == preprocess_id
    preprocess_worker._process(preprocess_id)

    with factory() as session:
        version = session.scalar(
            select(IndexVersion).where(IndexVersion.scope_id == knowledge_base_id)
        )
        assert version is not None
        version_id = version.index_version_id
        chunk_task = enqueue_index_chunking(session, version_id, f"chunk-{key}")
        session.commit()
        chunk_task_id = chunk_task.task_id
    chunk_worker = IndexChunkingWorker(factory, settings, worker_id=f"chunk-worker-{key}")
    assert chunk_worker._claim_one() == chunk_task_id
    chunk_worker._process(chunk_task_id)
    return version_id


def _queue_embedding(factory, version_id: str, key: str, *, retry_failed: bool = False) -> str:
    with factory() as session:
        task = enqueue_index_embedding(
            session,
            version_id,
            f"embed-{key}",
            retry_failed=retry_failed,
        )
        session.commit()
        return task.task_id


def _worker(factory, settings: Settings, runtime: FakeEmbeddingRuntime) -> IndexEmbeddingWorker:
    return IndexEmbeddingWorker(
        factory,
        settings,
        embedding_runtime_factory=lambda: runtime,
    )


def _process_embedding_task(worker: IndexEmbeddingWorker, task_id: str) -> None:
    assert worker._claim_one() == task_id
    worker._process(task_id)


def test_embedding_worker_persists_vectors_without_activating_index(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "persist")
    file_id = _import_file(client, "persist")
    _add_file(client, knowledge_base_id, file_id, "persist")
    version_id = _build_index(factory, settings, knowledge_base_id, "persist")
    runtime = FakeEmbeddingRuntime()
    task_id = _queue_embedding(factory, version_id, "persist")

    _process_embedding_task(_worker(factory, settings, runtime), task_id)

    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        version = session.get(IndexVersion, version_id)
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        record = session.scalar(select(EmbeddingRecord))
        assert task is not None and task.status == "COMPLETED"
        assert task.checkpoint_json["summary"]["available_for_retrieval"] is False
        assert task.checkpoint_json["summary"]["index_ready"] is False
        assert version is not None and version.status == "BUILDING"
        assert version.embedding_status == "COMPLETED"
        assert version.artifact_relative_path == f"vectors/{version.embedding_config_id}/{version_id}"
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        assert knowledge_base is not None and knowledge_base.active_index_version_id is None
        assert item is not None and item.embedding_status == "EMBEDDED"
        assert item.embedding_count == 1
        assert record is not None and record.status == "READY"
        config_id = record.embedding_config_id
        record_id = record.vector_store_record_id
        chunk_id = record.chunk_id

    store = SqliteVecAdapter(settings.vectors_dir)
    persisted = store.get(
        embedding_config_id=config_id,
        index_version_id=version_id,
        vector_store_record_id=record_id,
    )
    assert persisted is not None
    assert persisted[1] == chunk_id
    assert persisted[0].shape == (512,)
    assert np.isclose(np.linalg.norm(persisted[0]), 1.0)
    assert runtime.texts
    assert store.list_record_ids(config_id, version_id) == {record_id}
    member = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/files").json()["items"][0]
    assert member["available_for_retrieval"] is False
    assert member["index_state"] == "PENDING"


def test_worker_uses_verified_local_onnx_model_without_network(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    model_manager = ModelManager(
        Path(__file__).resolve().parents[1] / "model-cache" / "manager-validation"
    )
    if model_manager.status(offline=True).state is not ModelState.READY:
        pytest.skip("固定验证模型缓存不存在；离线测试不下载模型。")

    knowledge_base_id = _create_kb(client, "verified-onnx")
    file_id = _import_file(client, "verified-onnx")
    _add_file(client, knowledge_base_id, file_id, "verified-onnx")
    version_id = _build_index(factory, settings, knowledge_base_id, "verified-onnx")
    task_id = _queue_embedding(factory, version_id, "verified-onnx")
    worker = IndexEmbeddingWorker(factory, settings, model_manager=model_manager)

    _process_embedding_task(worker, task_id)

    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        record = session.scalar(select(EmbeddingRecord))
        version = session.get(IndexVersion, version_id)
        assert task is not None and task.status == "COMPLETED"
        assert record is not None and record.status == "READY"
        assert version is not None and version.status == "BUILDING"
        record_id = record.vector_store_record_id
        config_id = record.embedding_config_id
    vector = SqliteVecAdapter(settings.vectors_dir).get(
        embedding_config_id=config_id,
        index_version_id=version_id,
        vector_store_record_id=record_id,
    )
    assert vector is not None and vector[0].shape == (512,)
    assert np.isfinite(vector[0]).all()
    assert np.isclose(np.linalg.norm(vector[0]), 1.0)


def test_same_chunk_is_inferred_once_and_written_to_each_version(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    first_kb = _create_kb(client, "reuse-a")
    second_kb = _create_kb(client, "reuse-b")
    file_id = _import_file(client, "reuse")
    _add_file(client, first_kb, file_id, "reuse-a")
    first_version = _build_index(factory, settings, first_kb, "reuse-a")
    runtime = FakeEmbeddingRuntime()
    first_task = _queue_embedding(factory, first_version, "reuse-a")
    _process_embedding_task(_worker(factory, settings, runtime), first_task)
    first_inference_count = len(runtime.texts)

    _add_file(client, second_kb, file_id, "reuse-b")
    second_version = _build_index(factory, settings, second_kb, "reuse-b")
    second_task = _queue_embedding(factory, second_version, "reuse-b")
    _process_embedding_task(_worker(factory, settings, runtime), second_task)

    with factory() as session:
        record = session.scalar(select(EmbeddingRecord))
        assert record is not None
        record_id = record.vector_store_record_id
        config_id = record.embedding_config_id
        assert session.scalar(select(EmbeddingRecord.embedding_record_id).where(
            EmbeddingRecord.chunk_id == record.chunk_id,
            EmbeddingRecord.embedding_config_id == config_id,
        )) is not None
        assert session.scalar(select(Chunk.chunk_id).where(Chunk.chunk_id == record.chunk_id))
    assert len(runtime.texts) == first_inference_count
    store = SqliteVecAdapter(settings.vectors_dir)
    assert store.exists(
        embedding_config_id=config_id,
        index_version_id=first_version,
        vector_store_record_id=record_id,
    )
    assert store.exists(
        embedding_config_id=config_id,
        index_version_id=second_version,
        vector_store_record_id=record_id,
    )


def test_vector_written_before_process_interruption_is_reconciled_without_reinference(
    embedding_runtime,
) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "recover")
    file_id = _import_file(client, "recover")
    _add_file(client, knowledge_base_id, file_id, "recover")
    version_id = _build_index(factory, settings, knowledge_base_id, "recover")
    first_runtime = FakeEmbeddingRuntime()
    first_task = _queue_embedding(factory, version_id, "recover-first")
    store = SqliteVecAdapter(settings.vectors_dir)
    original_upsert = store.upsert

    def write_then_interrupt(*args, **kwargs):
        original_upsert(*args, **kwargs)
        with factory() as session:
            task = session.get(BackgroundTask, first_task)
            assert task is not None
            task.status = "INTERRUPTED"
            task.lease_owner = None
            task.lease_until = None
            session.commit()

    store.upsert = write_then_interrupt
    first_worker = IndexEmbeddingWorker(
        factory,
        settings,
        vector_store=store,
        embedding_runtime_factory=lambda: first_runtime,
    )
    _process_embedding_task(first_worker, first_task)
    assert len(first_runtime.texts) == 1

    with factory() as session:
        record = session.scalar(select(EmbeddingRecord))
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert record is not None and record.status == "PENDING"
        assert record.vector_hash is not None
        assert item is not None and item.embedding_status == "RUNNING"
        assert session.get(BackgroundTask, first_task).status == "INTERRUPTED"
        record_id = record.vector_store_record_id
        config_id = record.embedding_config_id
    assert store.exists(
        embedding_config_id=config_id,
        index_version_id=version_id,
        vector_store_record_id=record_id,
    )

    retry_runtime = FakeEmbeddingRuntime()
    _process_embedding_task(_worker(factory, settings, retry_runtime), first_task)
    assert retry_runtime.texts == []
    with factory() as session:
        record = session.scalar(select(EmbeddingRecord))
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert record is not None and record.status == "READY"
        assert item is not None and item.embedding_status == "EMBEDDED"


def test_index_version_deleted_after_vector_write_cleans_late_vector(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "purge-race")
    file_id = _import_file(client, "purge-race")
    _add_file(client, knowledge_base_id, file_id, "purge-race")
    version_id = _build_index(factory, settings, knowledge_base_id, "purge-race")
    task_id = _queue_embedding(factory, version_id, "purge-race")
    store = SqliteVecAdapter(settings.vectors_dir)
    original_upsert = store.upsert

    def write_then_remove_snapshot(*args, **kwargs):
        original_upsert(*args, **kwargs)
        with factory() as session:
            session.execute(
                delete(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version_id
                )
            )
            session.execute(delete(IndexVersion).where(IndexVersion.index_version_id == version_id))
            session.commit()

    store.upsert = write_then_remove_snapshot
    worker = IndexEmbeddingWorker(
        factory,
        settings,
        vector_store=store,
        embedding_runtime_factory=FakeEmbeddingRuntime,
    )
    _process_embedding_task(worker, task_id)

    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        record = session.scalar(select(EmbeddingRecord))
        assert task is not None and task.status == "FAILED"
        assert task.error_summary == "INDEX_INPUT_REMOVED"
        assert record is not None and record.status == "PENDING"
        config_id = record.embedding_config_id
        record_id = record.vector_store_record_id
    assert store.get(
        embedding_config_id=config_id,
        index_version_id=version_id,
        vector_store_record_id=record_id,
    ) is None


def test_missing_model_is_a_persistent_retryable_failure(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "missing-model")
    file_id = _import_file(client, "missing-model")
    _add_file(client, knowledge_base_id, file_id, "missing-model")
    version_id = _build_index(factory, settings, knowledge_base_id, "missing-model")
    task_id = _queue_embedding(factory, version_id, "missing-model")
    worker = IndexEmbeddingWorker(
        factory,
        settings,
        model_manager=cast(Any, MissingModelManager()),
    )

    _process_embedding_task(worker, task_id)

    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert task is not None and task.status == "FAILED"
        assert task.error_summary == "MODEL_MISSING_OFFLINE"
        assert task.checkpoint_json["summary"]["retryable"] is True
        assert task.checkpoint_json["summary"]["error_code"] == "MODEL_MISSING_OFFLINE"
        assert item is not None and item.embedding_status == "FAILED"
        assert item.embedding_reason_code == "MODEL_MISSING_OFFLINE"
        record = session.scalar(select(EmbeddingRecord))
        assert record is not None and record.status == "PENDING"
        assert record.vector_hash is None


def test_one_file_failure_does_not_block_other_file_embeddings(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "partial")
    failed_file_id = _import_file(client, "fail-this-file")
    good_file_id = _import_file(client, "good-file")
    _add_file(client, knowledge_base_id, failed_file_id, "partial-failed")
    _add_file(client, knowledge_base_id, good_file_id, "partial-good")
    version_id = _build_index(factory, settings, knowledge_base_id, "partial")
    task_id = _queue_embedding(factory, version_id, "partial")
    runtime = OneFileFailureRuntime()

    _process_embedding_task(_worker(factory, settings, runtime), task_id)

    with factory() as session:
        rows = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version_id
                )
            )
        )
        assert {row.embedding_status for row in rows} == {"FAILED", "EMBEDDED"}
        failed = next(row for row in rows if row.file_id == failed_file_id)
        good = next(row for row in rows if row.file_id == good_file_id)
        assert failed.embedding_reason_code == "FIXTURE_EMBEDDING_FAILURE"
        assert good.embedding_count == 1
        version = session.get(IndexVersion, version_id)
        assert version is not None and version.embedding_status == "PARTIAL"
        task = session.get(BackgroundTask, task_id)
        assert task is not None and task.status == "COMPLETED"


def test_member_removed_during_inference_is_skipped_without_publishing(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "remove-race")
    file_id = _import_file(client, "remove-race")
    _add_file(client, knowledge_base_id, file_id, "remove-race")
    version_id = _build_index(factory, settings, knowledge_base_id, "remove-race")
    task_id = _queue_embedding(factory, version_id, "remove-race")

    def remove_member() -> None:
        with factory() as session:
            member = session.scalar(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.file_id == file_id,
                )
            )
            assert member is not None
            member.membership_status = "REMOVED"
            knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
            assert knowledge_base is not None
            knowledge_base.status = "EMPTY"
            session.commit()

    worker = _worker(factory, settings, FakeEmbeddingRuntime(on_embed=remove_member))
    _process_embedding_task(worker, task_id)

    with factory() as session:
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert item is not None
        assert item.embedding_status == "SKIPPED"
        assert item.embedding_reason_code == "MEMBERSHIP_REMOVED"
    with factory() as session:
        version = session.get(IndexVersion, version_id)
        assert version is not None
        config_id = version.embedding_config_id
    assert SqliteVecAdapter(settings.vectors_dir).list_record_ids(config_id, version_id) == set()


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [("trash", "FILE_IN_TRASH"), ("parse_revision", "SOURCE_VERSION_CHANGED")],
)
def test_file_snapshot_changes_during_inference_are_not_published(
    embedding_runtime, mutation: str, expected_reason: str
) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, f"source-race-{mutation}")
    file_id = _import_file(client, f"source-race-{mutation}")
    _add_file(client, knowledge_base_id, file_id, f"source-race-{mutation}")
    version_id = _build_index(factory, settings, knowledge_base_id, f"source-race-{mutation}")
    task_id = _queue_embedding(factory, version_id, f"source-race-{mutation}")

    def mutate_file() -> None:
        with factory() as session:
            record = session.get(FileRecord, file_id)
            assert record is not None
            if mutation == "trash":
                from datetime import UTC, datetime

                record.deleted_at = datetime.now(UTC)
                record.status = "IN_TRASH"
            else:
                record.parse_revision_id = "changed-parse-revision"
            session.commit()

    _process_embedding_task(
        _worker(factory, settings, FakeEmbeddingRuntime(on_embed=mutate_file)), task_id
    )

    with factory() as session:
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert item is not None
        assert item.embedding_status == "SKIPPED"
        assert item.embedding_reason_code == expected_reason
        version = session.get(IndexVersion, version_id)
        assert version is not None
        config_id = version.embedding_config_id
    assert SqliteVecAdapter(settings.vectors_dir).list_record_ids(config_id, version_id) == set()


def test_explicit_cancellation_during_inference_does_not_write_vector(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "cancel-embed")
    file_id = _import_file(client, "cancel-embed")
    _add_file(client, knowledge_base_id, file_id, "cancel-embed")
    version_id = _build_index(factory, settings, knowledge_base_id, "cancel-embed")
    task_id = _queue_embedding(factory, version_id, "cancel-embed")

    def cancel_embedding() -> None:
        with factory() as session:
            task = session.get(BackgroundTask, task_id)
            assert task is not None
            cancel_task(session, task)
            session.commit()

    _process_embedding_task(
        _worker(factory, settings, FakeEmbeddingRuntime(on_embed=cancel_embedding)), task_id
    )

    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        version = session.get(IndexVersion, version_id)
        assert task is not None and task.status == "CANCELLED"
        assert version is not None and version.embedding_status == "CANCELLED"
        config_id = version.embedding_config_id
    assert SqliteVecAdapter(settings.vectors_dir).list_record_ids(config_id, version_id) == set()


def test_knowledge_base_purge_removes_only_its_version_vectors(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    first_kb = _create_kb(client, "purge-kb-a")
    second_kb = _create_kb(client, "purge-kb-b")
    file_id = _import_file(client, "purge-kb")
    _add_file(client, first_kb, file_id, "purge-kb-a")
    first_version = _build_index(factory, settings, first_kb, "purge-kb-a")
    first_task = _queue_embedding(factory, first_version, "purge-kb-a")
    _process_embedding_task(_worker(factory, settings, FakeEmbeddingRuntime()), first_task)
    _add_file(client, second_kb, file_id, "purge-kb-b")
    second_version = _build_index(factory, settings, second_kb, "purge-kb-b")
    second_task = _queue_embedding(factory, second_version, "purge-kb-b")
    _process_embedding_task(_worker(factory, settings, FakeEmbeddingRuntime()), second_task)
    store = SqliteVecAdapter(settings.vectors_dir)
    config_id = session_embedding_config_id(factory, first_version)
    knowledge_base_version = client.get(f"/api/v1/knowledge-bases/{first_kb}").json()[
        "row_version"
    ]

    trashed = client.delete(
        f"/api/v1/knowledge-bases/{first_kb}",
        params={"expected_version": knowledge_base_version},
        headers=_headers("trash-purge-kb-a"),
    )
    assert trashed.status_code == 200
    purged = client.delete(
        f"/api/v1/trash/knowledge-base/{first_kb}",
        params={"confirmed": "true", "expected_version": trashed.json()["row_version"]},
        headers=_headers("purge-kb-a"),
    )
    assert purged.status_code == 200
    assert not settings.vectors_dir.joinpath(config_id, first_version).exists()
    assert store.list_record_ids(config_id, second_version)
    with factory() as session:
        assert session.scalar(select(Chunk.chunk_id)) is not None
        assert session.scalar(select(EmbeddingRecord.embedding_record_id)) is not None


def test_file_purge_removes_its_embedding_mappings_and_vectors(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "purge-file")
    file_id = _import_file(client, "purge-file")
    _add_file(client, knowledge_base_id, file_id, "purge-file")
    version_id = _build_index(factory, settings, knowledge_base_id, "purge-file")
    task_id = _queue_embedding(factory, version_id, "purge-file")
    _process_embedding_task(_worker(factory, settings, FakeEmbeddingRuntime()), task_id)
    config_id = session_embedding_config_id(factory, version_id)
    assert SqliteVecAdapter(settings.vectors_dir).list_record_ids(config_id, version_id)

    trashed = client.post(
        "/api/v1/files/batch",
        headers=_headers("trash-file-for-purge"),
        json={"file_ids": [file_id], "action": "TRASH"},
    )
    assert trashed.status_code == 200
    with factory() as session:
        from mindmate.infrastructure.models import FileRecord

        file_record = session.get(FileRecord, file_id)
        assert file_record is not None
        expected_version = file_record.row_version
    purged = client.delete(
        f"/api/v1/trash/file/{file_id}",
        params={"confirmed": "true", "expected_version": expected_version},
        headers=_headers("purge-file"),
    )
    assert purged.status_code == 200
    assert SqliteVecAdapter(settings.vectors_dir).list_record_ids(config_id, version_id) == set()
    with factory() as session:
        assert session.scalar(select(Chunk.chunk_id)) is None
        assert session.scalar(select(EmbeddingRecord.embedding_record_id)) is None


def test_restart_resumes_running_input_without_duplicate_vector_write(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "restart")
    file_id = _import_file(client, "restart")
    _add_file(client, knowledge_base_id, file_id, "restart")
    version_id = _build_index(factory, settings, knowledge_base_id, "restart")
    task_id = _queue_embedding(factory, version_id, "restart")

    def interrupt_task() -> None:
        with factory() as session:
            task = session.get(BackgroundTask, task_id)
            assert task is not None
            task.status = "INTERRUPTED"
            task.lease_owner = None
            task.lease_until = None
            session.commit()

    first_runtime = FakeEmbeddingRuntime(on_embed=interrupt_task)
    _process_embedding_task(_worker(factory, settings, first_runtime), task_id)
    assert len(first_runtime.texts) == 1
    store = SqliteVecAdapter(settings.vectors_dir)
    assert store.list_record_ids(
        session_embedding_config_id(factory, version_id), version_id
    ) == set()

    retry_runtime = FakeEmbeddingRuntime()
    _process_embedding_task(_worker(factory, settings, retry_runtime), task_id)
    assert len(retry_runtime.texts) == 1
    with factory() as session:
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert item is not None and item.embedding_status == "EMBEDDED"
        assert session.get(BackgroundTask, task_id).status == "COMPLETED"


def test_configuration_change_during_inference_fails_closed(embedding_runtime) -> None:
    client, settings, factory = embedding_runtime
    knowledge_base_id = _create_kb(client, "config-race")
    file_id = _import_file(client, "config-race")
    _add_file(client, knowledge_base_id, file_id, "config-race")
    version_id = _build_index(factory, settings, knowledge_base_id, "config-race")
    task_id = _queue_embedding(factory, version_id, "config-race")

    def corrupt_config_fingerprint() -> None:
        with factory() as session:
            version = session.get(IndexVersion, version_id)
            assert version is not None
            config = session.get(EmbeddingConfig, version.embedding_config_id)
            assert config is not None
            config.config_fingerprint = "f" * 64
            session.commit()

    runtime = FakeEmbeddingRuntime(on_embed=corrupt_config_fingerprint)
    _process_embedding_task(_worker(factory, settings, runtime), task_id)
    with factory() as session:
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert item is not None
        assert item.embedding_status == "FAILED"
        assert item.embedding_reason_code == "EMBEDDING_CONFIG_UNVERIFIED"
    with factory() as session:
        version = session.get(IndexVersion, version_id)
        assert version is not None
        config_id = version.embedding_config_id
    assert SqliteVecAdapter(settings.vectors_dir).list_record_ids(config_id, version_id) == set()


def session_embedding_config_id(factory, version_id: str) -> str:
    with factory() as session:
        version = session.get(IndexVersion, version_id)
        assert version is not None
        return version.embedding_config_id


def test_embedding_claim_releases_only_expired_singleton_lease(embedding_runtime) -> None:
    _client, settings, factory = embedding_runtime
    with factory() as session:
        first = create_task(session, "INDEX_EMBED", "serial-one", {})
        second = create_task(session, "INDEX_EMBED", "serial-two", {})
        session.commit()
        first_id, second_id = first.task_id, second.task_id

    first_worker = IndexEmbeddingWorker(factory, settings, worker_id="serial-worker-one")
    second_worker = IndexEmbeddingWorker(factory, settings, worker_id="serial-worker-two")
    assert first_worker._claim_one() == first_id
    assert second_worker._claim_one() is None
    with factory() as session:
        session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.task_id == first_id)
            .values(lease_until=None)
        )
        session.commit()
    assert second_worker._claim_one() == first_id
    with factory() as session:
        assert session.get(BackgroundTask, second_id).status == "QUEUED"
