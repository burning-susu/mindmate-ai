from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mindmate.application.index_embedding_worker import IndexEmbeddingWorker
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.application.task_concurrency import (
    read_task_concurrency,
    write_task_concurrency,
)
from mindmate.application.tasks import (
    cancel_tasks_for_targets,
    claim_task,
    create_task,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    Base,
    IndexVersion,
    IndexVersionInput,
    TaskAttempt,
)
from mindmate.main import create_app

ORIGIN = "http://127.0.0.1:5173"


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'stage71.db').as_posix()}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _claim_heavy_in_process(db_path: str, worker_id: str) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 15})
    with Session(engine) as session:
        from mindmate.application.tasks import claim_next_task

        task = claim_next_task(
            session,
            worker_id,
            task_types={"INDEX_PREPROCESS"},
            concurrency_groups="HEAVY",
        )
        if task is None:
            session.rollback()
            return None
        session.commit()
        return task.task_id



def test_trash_target_cancels_only_dependent_tasks_and_keeps_shared_work(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        file_task = create_task(
            session,
            "FILE_REPROCESS",
            "file-a",
            {"context": {"file_id": "file-a"}, "items": [{"file_id": "file-a"}]},
        )
        unrelated_file = create_task(
            session,
            "FILE_REPROCESS",
            "file-b",
            {"context": {"file_id": "file-b"}, "items": [{"file_id": "file-b"}]},
        )
        index_task = create_task(
            session,
            "INDEX_PREPROCESS",
            "index-a",
            {"knowledge_base_id": "kb-a", "index_version_id": "version-a"},
        )
        shared_kb_task = create_task(
            session,
            "KNOWLEDGE_MEMBERSHIP_ADD",
            "kb-b",
            {"knowledge_base_id": "kb-b", "items": [{"file_id": "file-a"}]},
        )
        mixed_batch = create_task(
            session,
            "KNOWLEDGE_MEMBERSHIP_ADD",
            "kb-mixed",
            {
                "knowledge_base_id": "kb-mixed",
                "items": [{"file_id": "file-a"}, {"file_id": "file-b"}],
            },
        )
        session.commit()

        claimed = claim_task(session, index_task.task_id, "index-worker")
        assert claimed is not None
        session.commit()

        cancelled = cancel_tasks_for_targets(
            session,
            file_ids={"file-a"},
            knowledge_base_ids={"kb-a"},
            reason_code="TARGET_IN_TRASH",
        )
        session.commit()

        assert set(cancelled) == {file_task.task_id, index_task.task_id, shared_kb_task.task_id}
        file_row = session.get(BackgroundTask, file_task.task_id)
        index_row = session.get(BackgroundTask, index_task.task_id)
        shared_row = session.get(BackgroundTask, shared_kb_task.task_id)
        assert file_row is not None and file_row.status == "CANCELLED"
        assert index_row is not None and index_row.status == "CANCELLED"
        assert shared_row is not None and shared_row.status == "CANCELLED"
        untouched = session.get(BackgroundTask, unrelated_file.task_id)
        assert untouched is not None and untouched.status == "QUEUED"
        mixed = session.get(BackgroundTask, mixed_batch.task_id)
        assert mixed is not None and mixed.status == "QUEUED"
        cancelled_row = session.get(BackgroundTask, index_task.task_id)
        assert cancelled_row is not None
        assert cancelled_row.cancel_reason_code == "TARGET_IN_TRASH"
        assert cancelled_row.cancel_requested_at is not None
        attempt = session.scalar(
            select(TaskAttempt).where(TaskAttempt.task_id == index_task.task_id)
        )
        assert attempt is not None and attempt.status == "CANCELLED"


def test_index_input_file_target_cancels_only_matching_index_version(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        version = IndexVersion(
            index_version_id="version-file-a",
            scope_type="KNOWLEDGE_BASE",
            scope_id="kb-a",
            parse_revision_set_hash="hash",
            chunking_config_id="chunk-config",
            embedding_config_id="embed-config",
            vector_engine="sqlite-vec",
            vector_engine_version="test",
            status="BUILDING",
            preprocessing_status="RUNNING",
            created_at=datetime.now(UTC),
        )
        session.add(version)
        session.add(
            IndexVersionInput(
                index_version_input_id="input-file-a",
                index_version_id=version.index_version_id,
                knowledge_base_file_id="member-file-a",
                file_id="file-a",
                content_hash="hash",
                parse_revision_id="parse-a",
                membership_added_at=datetime.now(UTC),
                ordinal=0,
                status="PENDING",
            )
        )
        task = create_task(
            session,
            "INDEX_PREPROCESS",
            "index-input-file-a",
            {"knowledge_base_id": "kb-a", "index_version_id": version.index_version_id},
        )
        session.commit()

        cancel_tasks_for_targets(session, file_ids={"file-a"})
        session.commit()

        row = session.get(BackgroundTask, task.task_id)
        assert row is not None and row.status == "CANCELLED"


def test_worker_claims_share_default_heavy_limit_and_persist_lowered_limit(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    settings = Settings(data_dir=tmp_path, env="test", index_worker_poll_seconds=10)
    with factory() as session:
        tasks = [
            create_task(session, "INDEX_PREPROCESS", f"heavy-{index}", {})
            for index in range(3)
        ]
        session.commit()

    first = IndexPreprocessingWorker(factory, settings, worker_id="heavy-one")
    second = IndexPreprocessingWorker(factory, settings, worker_id="heavy-two")
    third = IndexPreprocessingWorker(factory, settings, worker_id="heavy-three")
    assert first._claim_one() == tasks[0].task_id
    assert second._claim_one() == tasks[1].task_id
    assert third._claim_one() is None

    with factory() as session:
        for task in tasks:
            row = session.get(BackgroundTask, task.task_id)
            assert row is not None
            row.status = "COMPLETED"
            row.lease_owner = None
            row.lease_until = None
        write_task_concurrency(session, heavy_task_limit=1, vector_write_limit=1)
        session.commit()
        stored = read_task_concurrency(session)
        assert stored.heavy_task_limit == 1
        assert stored.vector_write_limit == 1
        assert stored.source == "stored"
        lowered = [
            create_task(session, "INDEX_PREPROCESS", f"lowered-{index}", {})
            for index in range(2)
        ]
        session.commit()

    assert first._claim_one() == lowered[0].task_id
    assert second._claim_one() is None


def test_embedding_worker_claim_obeys_vector_write_limit(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    settings = Settings(data_dir=tmp_path, env="test", index_embedding_worker_poll_seconds=10)
    with factory() as session:
        tasks = [
            create_task(session, "INDEX_EMBED", f"embed-{index}", {})
            for index in range(2)
        ]
        session.commit()

    first = IndexEmbeddingWorker(factory, settings, worker_id="embed-one")
    second = IndexEmbeddingWorker(factory, settings, worker_id="embed-two")
    assert first._claim_one() == tasks[0].task_id
    assert second._claim_one() is None


def test_heavy_limit_is_enforced_by_two_processes(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    db_path = str(tmp_path / "stage71.db")
    with factory() as session:
        write_task_concurrency(session, heavy_task_limit=1, vector_write_limit=1)
        create_task(session, "INDEX_PREPROCESS", "process-race", {})
        session.commit()

    with ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn")) as executor:
        results = list(
            executor.map(
                _claim_heavy_in_process,
                [db_path, db_path],
                ["process-one", "process-two"],
            )
        )
    assert sum(result is not None for result in results) == 1


def test_invalid_persisted_concurrency_fails_closed(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        from mindmate.infrastructure.models import AppSetting

        session.add(
            AppSetting(
                setting_key="tasks.concurrency",
                setting_value_json={"heavy_task_limit": 9, "vector_write_limit": 9},
                setting_schema_version=1,
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
        config = read_task_concurrency(session)
        assert (config.heavy_task_limit, config.vector_write_limit) == (1, 1)
        assert config.source == "invalid"
        assert config.error_code == "TASK_CONCURRENCY_INVALID"
        with pytest.raises(ValueError, match="TASK_HEAVY_LIMIT_INVALID"):
            write_task_concurrency(session, heavy_task_limit=3, vector_write_limit=1)


def test_task_concurrency_api_displays_and_persists_effective_limit(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        parse_worker_poll_seconds=10,
        knowledge_worker_poll_seconds=10,
        index_worker_poll_seconds=10,
        index_chunk_worker_poll_seconds=10,
        index_embedding_worker_poll_seconds=10,
        index_fts_worker_poll_seconds=10,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        session = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
        assert session.status_code == 200, session.text
        default = client.get("/api/v1/system/task-concurrency")
        assert default.status_code == 200
        assert default.json()["heavy_task_limit"] == 2
        assert default.json()["vector_write_limit"] == 1

        updated = client.put(
            "/api/v1/system/task-concurrency",
            headers={"Origin": ORIGIN, "Idempotency-Key": "stage71-concurrency-1"},
            json={"heavy_task_limit": 1, "vector_write_limit": 1},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["source"] == "stored"
        assert updated.json()["heavy_task_limit"] == 1
        assert client.get("/api/v1/system/task-concurrency").json()["heavy_task_limit"] == 1

        rejected = client.put(
            "/api/v1/system/task-concurrency",
            headers={"Origin": ORIGIN, "Idempotency-Key": "stage71-concurrency-2"},
            json={"heavy_task_limit": 3, "vector_write_limit": 1},
        )
        assert rejected.status_code == 422
