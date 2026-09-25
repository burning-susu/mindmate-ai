from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from mindmate.application.chunking import enqueue_index_chunking
from mindmate.application.index_chunking_worker import IndexChunkingWorker
from mindmate.application.index_fts import enqueue_index_fts
from mindmate.application.index_fts_worker import IndexFtsWorker
from mindmate.application.index_preprocessing import enqueue_index_preprocessing
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.application.tasks import cancel_task
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Error, Fts5Projection, match_expression
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    EmbeddingRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    new_id,
)
from mindmate.main import create_app


def _headers(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def _wait_task(client: TestClient, task_id: str) -> dict[str, Any]:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        result = client.get(f"/api/v1/tasks/{task_id}").json()
        if result["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return result
        sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


@pytest.fixture
def fts_app(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
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
        json={"name": f"全文索引-{key}"},
    )
    assert response.status_code == 201
    return str(response.json()["knowledge_base_id"])


def _import_file(client: TestClient, key: str, content: str) -> str:
    response = client.post(
        "/api/v1/file-imports",
        headers=_headers(f"import-{key}"),
        files={"files": (f"{key}.txt", content.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 202
    result = _wait_task(client, response.json()["task_id"])
    assert result["status"] == "COMPLETED"
    return str(result["items"][0]["file_id"])


def _add_files(client: TestClient, kb_id: str, file_ids: list[str], key: str) -> None:
    response = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/files",
        headers=_headers(f"member-{key}"),
        json={"file_ids": file_ids},
    )
    assert response.status_code == 202
    assert _wait_task(client, response.json()["task_id"])["status"] == "COMPLETED"


def _build_version(factory, settings: Settings, kb_id: str, key: str) -> str:
    with factory() as session:
        task = enqueue_index_preprocessing(session, kb_id, f"preprocess-{key}")
        session.commit()
        preprocess_id = task.task_id
    preprocessing = IndexPreprocessingWorker(factory, settings, worker_id=f"pre-{key}")
    assert preprocessing._claim_one() == preprocess_id
    preprocessing._process(preprocess_id)
    with factory() as session:
        version = session.scalar(select(IndexVersion).where(IndexVersion.scope_id == kb_id))
        assert version is not None
        version_id = version.index_version_id
        task = enqueue_index_chunking(session, version_id, f"chunks-{key}")
        session.commit()
        chunk_task_id = task.task_id
    chunking = IndexChunkingWorker(factory, settings, worker_id=f"chunk-{key}")
    assert chunking._claim_one() == chunk_task_id
    chunking._process(chunk_task_id)
    return version_id


def _queue_fts(factory, version_id: str, key: str, *, rebuild: bool = False) -> str:
    with factory() as session:
        task = enqueue_index_fts(
            session, version_id, f"fts-{key}", rebuild=rebuild
        )
        session.commit()
        return task.task_id


def _run_fts(factory, settings: Settings, version_id: str, key: str) -> dict[str, Any]:
    task_id = _queue_fts(factory, version_id, key)
    worker = IndexFtsWorker(factory, settings, worker_id=f"fts-worker-{key}")
    assert worker._claim_one() == task_id
    worker._process(task_id)
    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        assert task is not None
        return task.checkpoint_json["summary"]


def _query(factory, version_id: str, query: str) -> list[dict[str, Any]]:
    with factory() as session:
        return Fts5Projection().match_version(session, version_id, query)


def test_fts5_is_versioned_chinese_short_query_bm25_and_rebuildable(fts_app) -> None:
    client, settings, factory = fts_app
    first_kb = _create_kb(client, "version-a")
    second_kb = _create_kb(client, "version-b")
    file_id = _import_file(
        client,
        "mixed-language",
        "人工智能知识检索使用SQLite索引，编号 A-12，事务保证可恢复。人工智能可以匹配短词。",
    )
    _add_files(client, first_kb, [file_id], "version-a")
    first_version = _build_version(factory, settings, first_kb, "version-a")
    _add_files(client, second_kb, [file_id], "version-b")
    second_version = _build_version(factory, settings, second_kb, "version-b")

    first_summary = _run_fts(factory, settings, first_version, "version-a")
    second_summary = _run_fts(factory, settings, second_version, "version-b")
    assert first_summary["fts_status"] == second_summary["fts_status"] == "COMPLETED"
    assert first_summary["chunks"] > 0
    assert len(_query(factory, first_version, "人工智能")) == 1
    assert len(_query(factory, first_version, "人工")) == 1
    assert len(_query(factory, first_version, "能")) == 1
    assert len(_query(factory, first_version, "sqlite")) == 1
    assert len(_query(factory, first_version, "A-12")) == 1
    assert len(_query(factory, first_version, "人工智能知识检索的编号是 A-12 吗？")) == 1
    assert len(_query(factory, first_version, "人工智能资料的编号是多少？")) == 1
    assert _query(factory, first_version, "人工智能知识检索的编号是 A-13 吗？") == []
    assert '"人工智能知识检索的编号是 A-12"' not in match_expression(
        "人工智能知识检索的编号是 A-12 吗？"
    )
    assert _query(factory, first_version, "!!!") == []
    assert _query(factory, first_version, "   \t  ") == []
    assert _query(factory, first_version, '" OR *') == []
    assert _query(factory, first_version, "不存在") == []
    assert _query(factory, second_version, "人工智能")[0]["file_id"] == file_id
    assert _query(factory, first_version, "人工智能")[0]["score"] < 0

    with factory() as session:
        first_count = Fts5Projection.count(session, first_version)
        second_count = Fts5Projection.count(session, second_version)
        assert first_count == second_count
        row_id = session.scalar(
            text(
                "SELECT fts_row_id FROM fts_chunk_map "
                "WHERE index_version_id = :version_id LIMIT 1"
            ),
            {"version_id": first_version},
        )
        session.execute(
            text("DELETE FROM index_chunk_fts WHERE rowid = :row_id"), {"row_id": row_id}
        )
        with pytest.raises(Fts5Error, match="FTS_PROJECTION_INCONSISTENT"):
            Fts5Projection().consistency_check(session, first_version)
        session.rollback()

    rebuild_task = _queue_fts(factory, first_version, "repair-first", rebuild=True)
    repair = IndexFtsWorker(factory, settings, worker_id="fts-repair")
    assert repair._claim_one() == rebuild_task
    repair._process(rebuild_task)
    with factory() as session:
        assert Fts5Projection.count(session, first_version) == first_count
        assert Fts5Projection.count(session, second_version) == second_count
        Fts5Projection().consistency_check(session, first_version)
        Fts5Projection().integrity_check(session)
        first = session.get(IndexVersion, first_version)
        kb = session.get(KnowledgeBase, first_kb)
        assert first is not None and first.status == "BUILDING"
        assert kb is not None and kb.active_index_version_id is None


def test_fts_input_failure_isolated_and_explicit_retry_recovers(fts_app) -> None:
    client, settings, factory = fts_app
    kb_id = _create_kb(client, "retry")
    broken_file = _import_file(client, "retry-broken", "错误文件仍保留权威Chunk内容用于恢复。")
    good_file = _import_file(client, "retry-good", "正常文件可以完成本地关键词投影。")
    _add_files(client, kb_id, [broken_file, good_file], "retry")
    version_id = _build_version(factory, settings, kb_id, "retry")
    with factory() as session:
        broken_chunk = session.scalar(select(Chunk).where(Chunk.file_id == broken_file))
        assert broken_chunk is not None
        original_content = broken_chunk.content
        broken_chunk.content = "被破坏的派生源快照"
        session.commit()

    task_id = _queue_fts(factory, version_id, "partial")
    worker = IndexFtsWorker(factory, settings, worker_id="fts-partial")
    assert worker._claim_one() == task_id
    worker._process(task_id)
    with factory() as session:
        failed = session.scalar(
            select(IndexVersionInput).where(
                IndexVersionInput.index_version_id == version_id,
                IndexVersionInput.file_id == broken_file,
            )
        )
        succeeded = session.scalar(
            select(IndexVersionInput).where(
                IndexVersionInput.index_version_id == version_id,
                IndexVersionInput.file_id == good_file,
            )
        )
        assert failed is not None and failed.fts_status == "FAILED"
        assert failed.fts_reason_code == "CHUNK_SET_UNAVAILABLE"
        assert succeeded is not None and succeeded.fts_status == "INDEXED"
        task = session.get(BackgroundTask, task_id)
        assert task is not None and task.checkpoint_json["summary"]["fts_status"] == "PARTIAL"
        broken_chunk = session.scalar(select(Chunk).where(Chunk.file_id == broken_file))
        assert broken_chunk is not None
        broken_chunk.content = original_content
        session.commit()

    with factory() as session:
        task = enqueue_index_fts(
            session, version_id, "fts-retry-broken", retry_failed=True
        )
        session.commit()
        retry_task = task.task_id
    retry_worker = IndexFtsWorker(factory, settings, worker_id="fts-retry")
    assert retry_worker._claim_one() == retry_task
    retry_worker._process(retry_task)
    with factory() as session:
        failed = session.scalar(
            select(IndexVersionInput).where(
                IndexVersionInput.index_version_id == version_id,
                IndexVersionInput.file_id == broken_file,
            )
        )
        assert failed is not None and failed.fts_status == "INDEXED"
        assert Fts5Projection.count(session, version_id) == failed.fts_count + 1
        Fts5Projection().consistency_check(session, version_id)
        Fts5Projection().integrity_check(session)


def test_expired_lease_resumes_running_input_without_duplicate_projection(fts_app) -> None:
    client, settings, factory = fts_app
    kb_id = _create_kb(client, "lease")
    file_id = _import_file(client, "lease", "租约过期后从持久检查点恢复关键词索引。")
    _add_files(client, kb_id, [file_id], "lease")
    version_id = _build_version(factory, settings, kb_id, "lease")
    task_id = _queue_fts(factory, version_id, "lease")
    first = IndexFtsWorker(factory, settings, worker_id="fts-expired")
    assert first._claim_one() == task_id
    with factory() as session:
        task = session.get(BackgroundTask, task_id)
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert task is not None and item is not None
        item.fts_status = "RUNNING"
        task.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    second = IndexFtsWorker(factory, settings, worker_id="fts-recovered")
    assert second._claim_one() == task_id
    second._process(task_id)
    with factory() as session:
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert item is not None and item.fts_status == "INDEXED"
        assert Fts5Projection.count(session, version_id) == item.fts_count
        Fts5Projection().consistency_check(session, version_id)
        Fts5Projection().integrity_check(session)


def test_task_progress_checkpoint_counts_each_committed_input(fts_app) -> None:
    client, settings, factory = fts_app
    kb_id = _create_kb(client, "progress")
    file_ids = [
        _import_file(client, "progress-one", "第一个逐项检查点应该推进一半。"),
        _import_file(client, "progress-two", "第二个逐项检查点应该完成进度。"),
    ]
    _add_files(client, kb_id, file_ids, "progress")
    version_id = _build_version(factory, settings, kb_id, "progress")
    task_id = _queue_fts(factory, version_id, "progress")
    worker = IndexFtsWorker(factory, settings, worker_id="fts-progress")
    assert worker._claim_one() == task_id

    original_project_input = worker._project_input
    progress_values: list[int | None] = []

    def project_and_capture_progress(
        task_id: str, version_id: str, input_id: str
    ) -> tuple[str, str | None, int]:
        outcome = original_project_input(task_id, version_id, input_id)
        with factory() as session:
            task = session.get(BackgroundTask, task_id)
            assert task is not None
            progress_values.append(task.progress)
        return outcome

    worker._project_input = project_and_capture_progress
    worker._process(task_id)
    assert progress_values == [50, 100]


def test_membership_removal_excludes_old_fts_rows_immediately(fts_app) -> None:
    client, settings, factory = fts_app
    kb_id = _create_kb(client, "member-removal")
    file_id = _import_file(client, "member-removal", "移出成员后旧FTS行仍然不能命中。")
    _add_files(client, kb_id, [file_id], "member-removal")
    version_id = _build_version(factory, settings, kb_id, "member-removal")
    task_id = _queue_fts(factory, version_id, "member-removal")
    assert client.delete(
        f"/api/v1/knowledge-bases/{kb_id}/files/{file_id}",
        headers=_headers("remove-member"),
    ).status_code == 200
    worker = IndexFtsWorker(factory, settings, worker_id="fts-stale-member")
    assert worker._claim_one() == task_id
    worker._process(task_id)
    with factory() as session:
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
        )
        assert item is not None and item.fts_status == "SKIPPED"
        assert item.fts_reason_code == "MEMBERSHIP_REMOVED"
        assert Fts5Projection.count(session, version_id) == 0
        assert Fts5Projection().match_version(session, version_id, "旧FTS") == []


def test_cancelled_task_does_not_publish_and_shared_kb_purge_is_scoped(fts_app) -> None:
    client, settings, factory = fts_app
    first_kb = _create_kb(client, "purge-a")
    second_kb = _create_kb(client, "purge-b")
    file_id = _import_file(client, "purge-shared", "两个知识库共享文件但FTS版本彼此隔离。")
    _add_files(client, first_kb, [file_id], "purge-a")
    first_version = _build_version(factory, settings, first_kb, "purge-a")
    _add_files(client, second_kb, [file_id], "purge-b")
    second_version = _build_version(factory, settings, second_kb, "purge-b")
    _run_fts(factory, settings, first_version, "purge-a")
    _run_fts(factory, settings, second_version, "purge-b")

    third_kb = _create_kb(client, "cancel")
    cancel_file = _import_file(client, "cancel", "取消中的持久任务不能发布过期FTS投影。")
    _add_files(client, third_kb, [cancel_file], "cancel")
    third_version = _build_version(factory, settings, third_kb, "cancel")
    cancel_task_id = _queue_fts(factory, third_version, "cancel")
    cancelling_worker = IndexFtsWorker(factory, settings, worker_id="fts-cancel")
    assert cancelling_worker._claim_one() == cancel_task_id
    with factory() as session:
        task = session.get(BackgroundTask, cancel_task_id)
        assert task is not None
        cancel_task(session, task)
        session.commit()
    cancelling_worker._process(cancel_task_id)
    with factory() as session:
        version = session.get(IndexVersion, third_version)
        assert version is not None and version.fts_status == "CANCELLED"
        assert Fts5Projection.count(session, third_version) == 0

    trashed = client.delete(
        f"/api/v1/knowledge-bases/{first_kb}?expected_version=2",
        headers=_headers("trash-purge-a"),
    )
    assert trashed.status_code == 200
    purged = client.delete(
        f"/api/v1/trash/knowledge-base/{first_kb}?expected_version=3&confirmed=true",
        headers=_headers("purge-a-kb"),
    )
    assert purged.status_code == 200, purged.text
    with factory() as session:
        assert Fts5Projection.count(session, first_version) == 0
        assert Fts5Projection.count(session, second_version) > 0
        assert session.get(Chunk, session.scalar(select(Chunk.chunk_id).where(Chunk.file_id == file_id)))
        assert session.get(KnowledgeBase, second_kb) is not None


def test_file_trash_excludes_and_permanent_delete_removes_only_its_fts_rows(fts_app) -> None:
    client, settings, factory = fts_app
    kb_id = _create_kb(client, "file-purge")
    removed_file = _import_file(client, "file-purge-remove", "ORCHID 单文件投影应该精准清理。")
    kept_file = _import_file(client, "file-purge-keep", "MAPLE 另一个文件的投影继续保留。")
    _add_files(client, kb_id, [removed_file, kept_file], "file-purge")
    version_id = _build_version(factory, settings, kb_id, "file-purge")
    _run_fts(factory, settings, version_id, "file-purge")
    assert _query(factory, version_id, "ORCHID")
    assert _query(factory, version_id, "MAPLE")

    current = client.get(f"/api/v1/files/{removed_file}").json()
    trashed = client.delete(
        f"/api/v1/files/{removed_file}?expected_version={current['row_version']}",
        headers=_headers("trash-fts-file"),
    )
    assert trashed.status_code == 200
    assert _query(factory, version_id, "ORCHID") == []
    assert _query(factory, version_id, "MAPLE")

    purged = client.delete(
        f"/api/v1/trash/file/{removed_file}",
        params={"confirmed": "true", "expected_version": trashed.json()["row_version"]},
        headers=_headers("purge-fts-file"),
    )
    assert purged.status_code == 200, purged.text
    with factory() as session:
        assert session.scalar(
            select(Chunk.chunk_id).where(Chunk.file_id == removed_file)
        ) is None
        assert session.scalar(
            select(Chunk.chunk_id).where(Chunk.file_id == kept_file)
        ) is not None
        assert session.scalar(
            text(
                "SELECT count(*) FROM fts_chunk_map "
                "WHERE index_version_id = :version_id AND file_id = :file_id"
            ),
            {"version_id": version_id, "file_id": removed_file},
        ) == 0
        assert session.scalar(
            text(
                "SELECT count(*) FROM fts_chunk_map "
                "WHERE index_version_id = :version_id AND file_id = :file_id"
            ),
            {"version_id": version_id, "file_id": kept_file},
        ) > 0
        version = session.get(IndexVersion, version_id)
        assert version is not None and version.status == "NEEDS_REBUILD"
        assert version.fts_status == "INVALIDATED"
        Fts5Projection().consistency_check(session, version_id)


def test_fts_migration_rollback_preserves_chunks_and_embedding_records(fts_app) -> None:
    client, settings, factory = fts_app
    kb_id = _create_kb(client, "migration")
    file_id = _import_file(client, "migration", "迁移降级只删除可重建的FTS派生投影。")
    _add_files(client, kb_id, [file_id], "migration")
    version_id = _build_version(factory, settings, kb_id, "migration")
    _run_fts(factory, settings, version_id, "before-migration")
    with factory() as session:
        version = session.get(IndexVersion, version_id)
        chunk_rows = list(session.scalars(select(Chunk).where(Chunk.file_id == file_id)))
        assert version is not None
        for chunk in chunk_rows:
            session.add(
                EmbeddingRecord(
                    embedding_record_id=new_id(),
                    chunk_id=chunk.chunk_id,
                    embedding_config_id=version.embedding_config_id,
                    vector_store_record_id=new_id(),
                    config_fingerprint="0" * 64,
                    vector_hash=None,
                    status="PENDING",
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()
        chunk_count = session.scalar(select(Chunk.chunk_id).where(Chunk.file_id == file_id))
        chunk_total = session.scalar(text("SELECT count(*) FROM chunks"))
        embedding_total = session.scalar(text("SELECT count(*) FROM embedding_records"))
        assert chunk_rows
        assert Fts5Projection.count(session, version_id) > 0

    for worker_name in (
        "parse_worker",
        "knowledge_membership_worker",
        "index_preprocessing_worker",
        "index_chunking_worker",
        "index_embedding_worker",
        "index_fts_worker",
    ):
        worker = getattr(client.app.state, worker_name)
        worker.stop()
    client.app.state.engine.dispose()

    config = Config(str(settings.alembic_ini))
    config.attributes["settings"] = settings
    command.downgrade(config, "a81f3c6d2e90")
    engine = create_engine(f"sqlite:///{settings.database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM chunks")) == chunk_total
        assert connection.scalar(text("SELECT count(*) FROM embedding_records")) == embedding_total
        assert connection.scalar(
            text("SELECT count(*) FROM sqlite_master WHERE name='index_chunk_fts'")
        ) == 0
        assert connection.scalar(text("PRAGMA quick_check")) == "ok"
    engine.dispose()

    command.upgrade(config, "head")
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM chunks")) == chunk_total
        assert session.scalar(text("SELECT count(*) FROM embedding_records")) == embedding_total
        assert Fts5Projection.count(session, version_id) == 0
        assert session.get(Chunk, chunk_count) is not None
        assert session.scalar(text("PRAGMA quick_check")) == "ok"
    task_id = _queue_fts(factory, version_id, "after-migration", rebuild=True)
    worker = IndexFtsWorker(factory, settings, worker_id="fts-after-migration")
    assert worker._claim_one() == task_id
    worker._process(task_id)
    with factory() as session:
        assert Fts5Projection.count(session, version_id) == chunk_total
        Fts5Projection().consistency_check(session, version_id)
