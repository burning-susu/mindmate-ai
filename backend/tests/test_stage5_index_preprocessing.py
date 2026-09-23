from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from mindmate.ai.embeddings.manifest import MODEL_REVISION
from mindmate.application.index_preprocessing import (
    default_chunking_payload,
    default_embedding_payload,
    enqueue_index_preprocessing,
    fingerprint,
)
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.application.tasks import cancel_task
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    ChunkingConfig,
    EmbeddingConfig,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
)
from mindmate.main import create_app


@pytest.fixture
def index_runtime(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, env="test", index_worker_poll_seconds=10)
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.post(
            "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
        ).status_code == 200
        yield client, settings, cast(Any, client.app).state.session_factory


def headers(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def wait_api_task(client: TestClient, task_id: str) -> dict:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        payload = client.get(f"/api/v1/tasks/{task_id}").json()
        if payload["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return payload
        sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


def create_knowledge_base(client: TestClient, key: str = "index-kb") -> str:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=headers(key),
        json={"name": f"索引预处理-{key}"},
    )
    assert response.status_code == 201
    return response.json()["knowledge_base_id"]


def import_and_add(client: TestClient, knowledge_base_id: str, name: str, content: bytes) -> str:
    imported = client.post(
        "/api/v1/file-imports",
        headers=headers(f"import-{name}"),
        files={"files": (name, content, "text/plain")},
    )
    assert imported.status_code == 202
    import_task = wait_api_task(client, imported.json()["task_id"])
    file_id = import_task["items"][0]["file_id"]
    added = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/files",
        headers=headers(f"member-{name}"),
        json={"file_ids": [file_id]},
    )
    assert wait_api_task(client, added.json()["task_id"])["status"] == "COMPLETED"
    return file_id


def enqueue(factory, knowledge_base_id: str, key: str) -> str:
    with factory() as session:
        task = enqueue_index_preprocessing(session, knowledge_base_id, key)
        session.commit()
        return task.task_id


def run_claimed(worker: IndexPreprocessingWorker) -> str:
    task_id = worker._claim_one()
    assert task_id is not None
    worker._process(task_id)
    return task_id


def test_default_configs_are_character_based_fingerprinted_and_non_secret(index_runtime) -> None:
    _, settings, factory = index_runtime
    chunking = default_chunking_payload()
    embedding = default_embedding_payload()
    assert chunking["measurement_unit"] == "UNICODE_CHARACTER"
    assert (chunking["target_size"], chunking["overlap_size"]) == (500, 80)
    assert "token" not in " ".join(chunking)
    assert embedding == {
        "config_version": "bge-small-zh-v1",
        "provider_type": "LOCAL_ONNX",
        "model_name": "BAAI/bge-small-zh-v1.5",
        "model_revision": MODEL_REVISION,
        "vector_dimension": 512,
        "normalization": True,
        "distance_metric": "COSINE",
    }
    assert fingerprint(chunking) == fingerprint(dict(reversed(list(chunking.items()))))
    assert "key" not in str(chunking).lower() + str(embedding).lower()

    kb_id = create_knowledge_base(index_runtime[0], "config-kb")
    enqueue(factory, kb_id, "config-task")
    run_claimed(IndexPreprocessingWorker(factory, settings, worker_id="config-worker"))
    with factory() as session:
        assert session.scalar(select(ChunkingConfig)).config_fingerprint == fingerprint(chunking)
        verified_config = session.scalar(
            select(EmbeddingConfig).where(
                EmbeddingConfig.config_fingerprint == fingerprint(embedding)
            )
        )
        legacy_config = session.scalar(
            select(EmbeddingConfig).where(EmbeddingConfig.model_revision.is_(None))
        )
        assert verified_config is not None
        assert verified_config.model_revision == MODEL_REVISION
        assert legacy_config is not None


def test_preprocessing_freezes_inputs_and_never_activates_or_marks_ready(index_runtime) -> None:
    client, settings, factory = index_runtime
    knowledge_base_id = create_knowledge_base(client, "happy-kb")
    file_id = import_and_add(client, knowledge_base_id, "prepared.txt", b"prepared knowledge")
    first_task_id = enqueue(factory, knowledge_base_id, "same-preprocess-request")
    assert enqueue(factory, knowledge_base_id, "same-preprocess-request") == first_task_id

    run_claimed(IndexPreprocessingWorker(factory, settings, worker_id="happy-worker"))
    with factory() as session:
        task = session.get(BackgroundTask, first_task_id)
        version = session.scalar(select(IndexVersion))
        item = session.scalar(select(IndexVersionInput))
        kb = session.get(KnowledgeBase, knowledge_base_id)
        assert task.status == "COMPLETED"
        assert task.checkpoint_json["summary"] == {
            "prepared": 1,
            "skipped": 0,
            "failed": 0,
            "index_status": "BUILDING",
            "preprocessing_status": "COMPLETED",
            "index_ready": False,
        }
        assert version.status == "BUILDING"
        assert version.preprocessing_status == "COMPLETED"
        assert version.parse_revision_set_hash == task.checkpoint_json["parse_revision_set_hash"]
        assert item.file_id == file_id and item.status == "PREPARED"
        assert kb.active_index_version_id is None
        assert kb.status == "PREPARING"


def test_mixed_inputs_and_snapshot_races_have_stable_per_file_results(index_runtime) -> None:
    client, settings, factory = index_runtime
    knowledge_base_id = create_knowledge_base(client, "mixed-kb")
    prepared_id = import_and_add(client, knowledge_base_id, "good.txt", b"good")
    failed_id = import_and_add(client, knowledge_base_id, "failed.txt", b"failed")
    removed_id = import_and_add(client, knowledge_base_id, "removed.txt", b"removed")
    with factory() as session:
        failed = session.get(FileRecord, failed_id)
        failed.status = "PARSE_FAILED"
        failed.parse_revision_id = None
        session.commit()

    task_id = enqueue(factory, knowledge_base_id, "mixed-preprocess")
    worker = IndexPreprocessingWorker(factory, settings, worker_id="mixed-worker")
    assert worker._claim_one() == task_id
    version_id = worker._ensure_snapshot(task_id)
    assert version_id is not None
    removed = client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/files/{removed_id}",
        headers=headers("remove-after-snapshot"),
    )
    assert removed.status_code == 200
    with factory() as session:
        prepared = session.get(FileRecord, prepared_id)
        prepared.parse_revision_id = "changed-after-snapshot"
        session.commit()
    worker._process(task_id)

    with factory() as session:
        results = {
            item.file_id: (item.status, item.reason_code)
            for item in session.scalars(
                select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
            )
        }
        version = session.get(IndexVersion, version_id)
        assert results == {
            prepared_id: ("SKIPPED", "SOURCE_VERSION_CHANGED"),
            failed_id: ("FAILED", "PARSE_FAILED"),
            removed_id: ("SKIPPED", "MEMBERSHIP_REMOVED"),
        }
        assert version.preprocessing_status == "FAILED"
        assert (version.prepared_count, version.skipped_count, version.failed_count) == (0, 2, 1)
        assert session.get(KnowledgeBase, knowledge_base_id).active_index_version_id is None


def test_expired_lease_resumes_from_persisted_snapshot_with_another_worker(index_runtime) -> None:
    client, settings, factory = index_runtime
    knowledge_base_id = create_knowledge_base(client, "resume-kb")
    first_id = import_and_add(client, knowledge_base_id, "first.txt", b"first")
    second_id = import_and_add(client, knowledge_base_id, "second.txt", b"second")
    task_id = enqueue(factory, knowledge_base_id, "resume-preprocess")
    first_worker = IndexPreprocessingWorker(factory, settings, worker_id="worker-one")
    assert first_worker._claim_one() == task_id
    version_id = first_worker._ensure_snapshot(task_id)
    assert version_id is not None
    with factory() as session:
        first = session.scalar(
            select(IndexVersionInput)
            .where(IndexVersionInput.index_version_id == version_id)
            .order_by(IndexVersionInput.ordinal)
        )
        first.status = "PREPARED"
        first.prepared_at = datetime.now(UTC)
        task = session.get(BackgroundTask, task_id)
        task.checkpoint_json = {
            **task.checkpoint_json,
            "next_ordinal": 1,
            "results": [{"file_id": first.file_id, "status": "PREPARED", "reason": None}],
        }
        session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.task_id == task_id)
            .values(lease_until=datetime(2000, 1, 1, tzinfo=UTC))
        )
        session.commit()

    second_worker = IndexPreprocessingWorker(factory, settings, worker_id="worker-two")
    assert second_worker._claim_one() == task_id
    second_worker._process(task_id)
    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        inputs = list(
            session.scalars(
                select(IndexVersionInput)
                .where(IndexVersionInput.index_version_id == version_id)
                .order_by(IndexVersionInput.ordinal)
            )
        )
        assert task.status == "COMPLETED"
        assert [item.status for item in inputs] == ["PREPARED", "PREPARED"]
        assert {item.file_id for item in inputs} == {first_id, second_id}
        assert session.get(IndexVersion, version_id).prepared_count == 2


def test_cancelled_preprocessing_does_not_publish_or_reactivate(index_runtime) -> None:
    client, settings, factory = index_runtime
    knowledge_base_id = create_knowledge_base(client, "cancel-kb")
    import_and_add(client, knowledge_base_id, "cancel.txt", b"cancel")
    task_id = enqueue(factory, knowledge_base_id, "cancel-preprocess")
    worker = IndexPreprocessingWorker(factory, settings, worker_id="cancel-worker")
    assert worker._claim_one() == task_id
    version_id = worker._ensure_snapshot(task_id)
    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        cancel_task(session, task)
        session.commit()
    worker._process(task_id)
    with factory() as session:
        assert session.get(BackgroundTask, task_id).status == "CANCELLED"
        assert session.get(IndexVersion, version_id).preprocessing_status == "CANCELLED"
        assert session.get(KnowledgeBase, knowledge_base_id).active_index_version_id is None


def test_permanent_file_delete_cleans_unbuilt_snapshot_without_deleting_other_files(
    index_runtime,
) -> None:
    client, settings, factory = index_runtime
    knowledge_base_id = create_knowledge_base(client, "purge-kb")
    file_id = import_and_add(client, knowledge_base_id, "purge.txt", b"purge")
    other_id = import_and_add(client, knowledge_base_id, "keep.txt", b"keep")
    task_id = enqueue(factory, knowledge_base_id, "purge-preprocess")
    run_claimed(IndexPreprocessingWorker(factory, settings, worker_id="purge-worker"))
    with factory() as session:
        version_id = session.get(BackgroundTask, task_id).checkpoint_json["index_version_id"]

    current = client.get(f"/api/v1/files/{file_id}").json()
    trashed = client.delete(
        f"/api/v1/files/{file_id}?expected_version={current['row_version']}",
        headers=headers("trash-preprocessed-file"),
    )
    assert trashed.status_code == 200
    purged = client.delete(
        f"/api/v1/trash/file/{file_id}",
        params={"expected_version": trashed.json()["row_version"], "confirmed": "true"},
        headers=headers("purge-preprocessed-file"),
    )
    assert purged.status_code == 200
    assert client.get(f"/api/v1/files/{other_id}").status_code == 200
    with factory() as session:
        assert session.get(IndexVersion, version_id) is None


def test_permanent_knowledge_base_delete_cleans_snapshot_and_keeps_source_file(
    index_runtime,
) -> None:
    client, settings, factory = index_runtime
    knowledge_base_id = create_knowledge_base(client, "purge-version-kb")
    file_id = import_and_add(client, knowledge_base_id, "source-kept.txt", b"source kept")
    task_id = enqueue(factory, knowledge_base_id, "purge-version-preprocess")
    run_claimed(IndexPreprocessingWorker(factory, settings, worker_id="purge-version-worker"))
    with factory() as session:
        version_id = session.get(BackgroundTask, task_id).checkpoint_json["index_version_id"]

    current = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}").json()
    trashed = client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        params={"expected_version": current["row_version"]},
        headers=headers("trash-preprocessed-kb"),
    )
    assert trashed.status_code == 200
    purged = client.delete(
        f"/api/v1/trash/knowledge-base/{knowledge_base_id}",
        params={"expected_version": trashed.json()["row_version"], "confirmed": "true"},
        headers=headers("purge-preprocessed-kb"),
    )
    assert purged.status_code == 200
    assert client.get(f"/api/v1/files/{file_id}").status_code == 200
    with factory() as session:
        assert session.get(IndexVersion, version_id) is None
