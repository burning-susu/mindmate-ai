from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from mindmate.application.chunking import (
    ChunkingCancelled,
    chunk_parsed_document,
    enqueue_index_chunking,
)
from mindmate.application.files import read_parsed_text, write_parsed_text
from mindmate.application.index_chunking_worker import IndexChunkingWorker
from mindmate.application.index_preprocessing import enqueue_index_preprocessing, fingerprint
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    ChunkingConfig,
    FileRecord,
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
        payload = client.get(f"/api/v1/tasks/{task_id}").json()
        if payload["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return payload
        sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


def _create_kb(client: TestClient, key: str) -> str:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=_headers(key),
        json={"name": f"切片-{key}"},
    )
    assert response.status_code == 201
    return response.json()["knowledge_base_id"]


def _import_and_add(client: TestClient, kb_id: str, key: str, content: bytes) -> str:
    imported = client.post(
        "/api/v1/file-imports",
        headers=_headers(f"import-{key}"),
        files={"files": (f"{key}.txt", content, "text/plain")},
    )
    assert imported.status_code == 202
    import_task = _wait_task(client, imported.json()["task_id"])
    file_id = import_task["items"][0]["file_id"]
    added = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/files",
        headers=_headers(f"member-{key}"),
        json={"file_ids": [file_id]},
    )
    assert added.status_code == 202
    assert _wait_task(client, added.json()["task_id"])["status"] == "COMPLETED"
    return file_id


def _build_preprocessed_version(factory, settings, kb_id: str, key: str) -> str:
    with factory() as session:
        task = enqueue_index_preprocessing(session, kb_id, f"preprocess-{key}")
        session.commit()
        task_id = task.task_id
    preprocess_worker = IndexPreprocessingWorker(factory, settings, worker_id=f"preprocess-{key}")
    assert preprocess_worker._claim_one() == task_id
    preprocess_worker._process(task_id)
    with factory() as session:
        version = session.scalar(select(IndexVersion).where(IndexVersion.scope_id == kb_id).order_by(IndexVersion.created_at.desc()))
        assert version is not None
        return version.index_version_id


def _build_chunks(factory, settings, version_id: str, key: str) -> str:
    with factory() as session:
        task = enqueue_index_chunking(session, version_id, f"chunk-{key}")
        session.commit()
        task_id = task.task_id
    worker = IndexChunkingWorker(factory, settings, worker_id=f"chunk-{key}")
    assert worker._claim_one() == task_id
    worker._process(task_id)
    return task_id


def _runtime(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        index_worker_poll_seconds=10,
        index_chunk_worker_poll_seconds=10,
    )
    client = TestClient(create_app(settings), base_url="http://127.0.0.1")
    client.__enter__()
    assert client.post(
        "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
    ).status_code == 200
    return client, settings, cast(Any, client.app).state.session_factory


def test_structure_aware_chunking_uses_character_lengths_and_locations() -> None:
    parsed = {
        "text": "# 标题\n\n" + ("这是第一段内容。" * 80) + "\n\n```python\n" + "x = 1\n" * 20 + "```",
        "locations": [],
    }
    chunks = chunk_parsed_document(parsed, target_size=120, min_size=40, max_size=180, overlap_size=20)
    assert chunks
    assert all(0 < len(chunk.content) <= 180 for chunk in chunks)
    assert all(chunk.length_unit == "UNICODE_CHARACTER" for chunk in chunks)
    assert all(chunk.length_value == len(chunk.content) for chunk in chunks)
    assert all(chunk.token_count is None for chunk in chunks)
    with pytest.raises(ChunkingCancelled):
        chunk_parsed_document(
            {"text": "x" * 100_000, "locations": []}, cancel_check=lambda: True
        )
    assert chunks[0].heading_path == ["标题"]
    assert any(chunk.source_kind == "CODE" for chunk in chunks)
    assert any(chunk.line_start is not None for chunk in chunks)
    assert len(chunks) > 1
    assert chunks[0].content[-20:] in chunks[1].content
    default_chunks = chunk_parsed_document({"text": "正文。" * 500, "locations": []})
    assert 1 < len(default_chunks)
    assert len(default_chunks[0].content) <= 500
    assert default_chunks[0].content[-80:] in default_chunks[1].content
    assert chunk_parsed_document({"text": "  \n\n", "locations": []}) == []


def test_chunking_preserves_heading_page_and_slide_boundaries() -> None:
    text = "第一段\n第二段"
    parsed = {
        "text": text,
        "locations": [
            {"start": 0, "length": 3, "page": 1, "heading_path": ["甲"]},
            {"start": 4, "length": 3, "page": 2, "heading_path": ["乙"]},
        ],
    }
    chunks = chunk_parsed_document(parsed, target_size=20, max_size=40)
    assert [chunk.page_start for chunk in chunks] == [1, 2]
    assert [chunk.heading_path for chunk in chunks] == [["甲"], ["乙"]]

    slides = chunk_parsed_document(
        {
            "text": "幻灯片甲\n幻灯片乙",
            "locations": [
                {"start": 0, "length": 4, "slide": 1},
                {"start": 5, "length": 4, "slide": 2},
            ],
        },
        target_size=20,
        max_size=40,
    )
    assert [chunk.slide_number for chunk in slides] == [1, 2]
    repeated = chunk_parsed_document(
        {
            "text": "相同\n相同",
            "locations": [
                {"start": 0, "length": 2, "line": 1, "block_type": "LIST"},
                {"start": 3, "length": 2, "line": 2, "block_type": "LIST"},
            ],
        },
        target_size=2,
        max_size=10,
        overlap_size=0,
    )
    assert len(repeated) == 2
    assert [chunk.line_start for chunk in repeated] == [1, 2]
    assert all(chunk.source_kind == "LIST" for chunk in repeated)

    short_blocks = chunk_parsed_document(
        {
            "text": "甲" * 240 + "\n" + "乙" * 300,
            "locations": [
                {"start": 0, "length": 240, "heading_path": ["同章"]},
                {"start": 241, "length": 300, "heading_path": ["同章"]},
            ],
        },
        target_size=500,
        min_size=250,
        max_size=800,
        overlap_size=0,
    )
    assert len(short_blocks) == 1
    assert 500 < short_blocks[0].length_value <= 800

    table = chunk_parsed_document(
        {
            "text": "学科\t得分\n数学\t92\n语文\t88",
            "locations": [
                {"start": 0, "length": 5, "block_type": "TABLE"},
                {"start": 6, "length": 5, "block_type": "TABLE"},
                {"start": 12, "length": 5, "block_type": "TABLE"},
            ],
        },
        target_size=40,
        max_size=80,
        overlap_size=0,
    )
    assert len(table) == 1
    assert table[0].source_kind == "TABLE"
    assert table[0].content == "学科\t得分\n数学\t92\n语文\t88"


def test_chunk_worker_persists_reuses_and_never_activates(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "reuse-key")
        file_id = _import_and_add(client, kb_id, "reuse", ("# 章节\n\n" + "正文。" * 240).encode())
        with factory() as session:
            preprocess = enqueue_index_preprocessing(session, kb_id, "preprocess-reuse")
            session.commit()
            preprocess_id = preprocess.task_id
        preprocess_worker = IndexPreprocessingWorker(factory, settings, worker_id="preprocess-test")
        assert preprocess_worker._claim_one() == preprocess_id
        preprocess_worker._process(preprocess_id)
        with factory() as session:
            version = session.scalar(select(IndexVersion))
            assert version is not None
            version_id = version.index_version_id
            assert session.scalar(select(IndexVersionInput).where(IndexVersionInput.file_id == file_id)).status == "PREPARED"
            chunk_task = enqueue_index_chunking(session, version_id, "chunk-reuse")
            session.commit()
            chunk_task_id = chunk_task.task_id

        worker = IndexChunkingWorker(factory, settings, worker_id="chunk-test")
        assert worker._claim_one() == chunk_task_id
        worker._process(chunk_task_id)
        with factory() as session:
            task = session.get(BackgroundTask, chunk_task_id)
            version = session.get(IndexVersion, version_id)
            input_row = session.scalar(select(IndexVersionInput).where(IndexVersionInput.file_id == file_id))
            chunks = list(session.scalars(select(Chunk).where(Chunk.file_id == file_id)))
            assert task is not None and task.status == "COMPLETED"
            task_response = client.get(f"/api/v1/tasks/{chunk_task_id}")
            assert task_response.status_code == 200
            assert task_response.json()["task_type"] == "INDEX_CHUNK"
            assert task_response.json()["index_version_id"] == version_id
            assert version is not None and version.status == "BUILDING"
            assert version.chunking_status == "COMPLETED"
            assert session.get(KnowledgeBase, kb_id).active_index_version_id is None
            assert input_row is not None and input_row.chunk_status == "CHUNKED"
            assert len(chunks) == input_row.chunk_count > 0
            assert task.checkpoint_json["summary"]["index_ready"] is False
            first_count = len(chunks)
            second_task = enqueue_index_chunking(session, version_id, "chunk-reuse-second")
            session.commit()
            second_task_id = second_task.task_id
        assert worker._claim_one() == second_task_id
        worker._process(second_task_id)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Chunk).where(Chunk.file_id == file_id)) == first_count
    finally:
        client.__exit__(None, None, None)


def test_chunk_worker_cancelled_task_does_not_publish_partial_set(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "cancel-key")
        _import_and_add(client, kb_id, "cancel", b"cancel me " * 100)
        with factory() as session:
            preprocess = enqueue_index_preprocessing(session, kb_id, "preprocess-cancel")
            session.commit()
            preprocess_id = preprocess.task_id
        preprocess_worker = IndexPreprocessingWorker(factory, settings, worker_id="preprocess-cancel")
        assert preprocess_worker._claim_one() == preprocess_id
        preprocess_worker._process(preprocess_id)
        with factory() as session:
            version_id = session.scalar(select(IndexVersion)).index_version_id
            task = enqueue_index_chunking(session, version_id, "chunk-cancel")
            session.commit()
            task_id = task.task_id
        worker = IndexChunkingWorker(factory, settings, worker_id="chunk-cancel")
        assert worker._claim_one() == task_id
        cancelled = client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            headers=_headers("cancel-index-chunk-task"),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["task_type"] == "INDEX_CHUNK"
        assert cancelled.json()["index_version_id"] == version_id
        with factory() as session:
            assert session.get(BackgroundTask, task_id).status == "CANCELLED"
        worker._process(task_id)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Chunk)) == 0
            assert session.get(IndexVersion, version_id).chunking_status == "CANCELLED"
    finally:
        client.__exit__(None, None, None)


def test_chunk_worker_reuses_two_knowledge_bases_and_keeps_parse_versions(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        first_kb = _create_kb(client, "shared-first-key")
        second_kb = _create_kb(client, "shared-second-key")
        file_id = _import_and_add(client, first_kb, "shared", b"shared knowledge " * 120)
        added = client.post(
            f"/api/v1/knowledge-bases/{second_kb}/files",
            headers=_headers("member-shared-second-key"),
            json={"file_ids": [file_id]},
        )
        assert added.status_code == 202
        assert _wait_task(client, added.json()["task_id"])["status"] == "COMPLETED"

        first_version = _build_preprocessed_version(factory, settings, first_kb, "shared-first")
        _build_chunks(factory, settings, first_version, "shared-first")
        with factory() as session:
            first_chunks = list(
                session.scalars(
                    select(Chunk).where(Chunk.file_id == file_id).order_by(Chunk.sequence_number)
                )
            )
            assert first_chunks
            first_ids = [chunk.chunk_id for chunk in first_chunks]
            record = session.scalar(
                select(IndexVersionInput).where(IndexVersionInput.file_id == file_id)
            )
            assert record is not None
            old_parse_revision = record.parse_revision_id

        second_version = _build_preprocessed_version(factory, settings, second_kb, "shared-second")
        _build_chunks(factory, settings, second_version, "shared-second")
        with factory() as session:
            reused = list(
                session.scalars(
                    select(Chunk).where(Chunk.file_id == file_id).order_by(Chunk.sequence_number)
                )
            )
            assert [chunk.chunk_id for chunk in reused] == first_ids

            session.execute(
                update(FileRecord)
                .where(FileRecord.file_id == file_id)
                .values(parse_revision_id="parse-revision-v2")
            )
            session.commit()

        third_version = _build_preprocessed_version(factory, settings, first_kb, "shared-third-parse")
        _build_chunks(factory, settings, third_version, "shared-third-parse")
        with factory() as session:
            all_chunks = list(session.scalars(select(Chunk).where(Chunk.file_id == file_id)))
            assert old_parse_revision is not None
            assert {chunk.parse_revision_id for chunk in all_chunks} == {
                old_parse_revision,
                "parse-revision-v2",
            }
            assert len(all_chunks) > len(first_chunks)
    finally:
        client.__exit__(None, None, None)


def test_chunk_configuration_change_keeps_previous_file_level_chunks(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "config-version-key")
        file_id = _import_and_add(
            client, kb_id, "config-version", ("configuration content。" * 100).encode()
        )
        original_version_id = _build_preprocessed_version(
            factory, settings, kb_id, "config-original"
        )
        _build_chunks(factory, settings, original_version_id, "config-original")
        with factory() as session:
            original_version = session.get(IndexVersion, original_version_id)
            assert original_version is not None
            base_config = session.get(ChunkingConfig, original_version.chunking_config_id)
            assert base_config is not None
            payload = {
                "config_version": "char-v2-test",
                "algorithm_id": base_config.algorithm_id,
                "measurement_unit": base_config.measurement_unit,
                "target_size": 300,
                "min_size": 150,
                "max_size": 600,
                "overlap_size": 40,
                "structure_rules_hash": base_config.structure_rules_hash,
            }
            changed_config = ChunkingConfig(
                chunking_config_id=new_id(),
                **payload,
                config_fingerprint=fingerprint(payload),
                created_at=datetime.now(UTC),
            )
            session.add(changed_config)
            session.flush()
            new_version_id = new_id()
            new_version = IndexVersion(
                index_version_id=new_version_id,
                scope_type=original_version.scope_type,
                scope_id=original_version.scope_id,
                parse_revision_set_hash=original_version.parse_revision_set_hash,
                chunking_config_id=changed_config.chunking_config_id,
                embedding_config_id=original_version.embedding_config_id,
                vector_engine=original_version.vector_engine,
                vector_engine_version=original_version.vector_engine_version,
                status="BUILDING",
                preprocessing_status="COMPLETED",
                input_count=original_version.input_count,
                prepared_count=original_version.prepared_count,
                skipped_count=0,
                failed_count=0,
                created_at=datetime.now(UTC),
            )
            session.add(new_version)
            old_inputs = list(
                session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == original_version_id
                    )
                )
            )
            for old_input in old_inputs:
                session.add(
                    IndexVersionInput(
                        index_version_input_id=new_id(),
                        index_version_id=new_version_id,
                        knowledge_base_file_id=old_input.knowledge_base_file_id,
                        file_id=old_input.file_id,
                        content_hash=old_input.content_hash,
                        parse_revision_id=old_input.parse_revision_id,
                        membership_added_at=old_input.membership_added_at,
                        ordinal=old_input.ordinal,
                        status="PREPARED",
                    )
                )
            session.commit()

        _build_chunks(factory, settings, new_version_id, "config-changed")
        with factory() as session:
            chunks = list(session.scalars(select(Chunk).where(Chunk.file_id == file_id)))
            config_ids = {chunk.chunking_config_id for chunk in chunks}
            assert config_ids == {base_config.chunking_config_id, changed_config.chunking_config_id}
            assert session.get(IndexVersion, original_version_id).status == "BUILDING"
            assert session.get(IndexVersion, new_version_id).status == "BUILDING"
    finally:
        client.__exit__(None, None, None)


def test_chunk_worker_mixed_inputs_are_partial_and_expired_lease_resumes(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "mixed-key")
        good_id = _import_and_add(client, kb_id, "good", b"good " * 200)
        failed_id = _import_and_add(client, kb_id, "failed", b"failed")
        with factory() as session:
            failed = session.get(FileRecord, failed_id)
            assert failed is not None
            failed.status = "PARSE_FAILED"
            failed.parse_revision_id = None
            session.commit()
        version_id = _build_preprocessed_version(factory, settings, kb_id, "mixed")
        with factory() as session:
            version = session.get(IndexVersion, version_id)
            assert version is not None
            assert version.preprocessed_at is not None
            task = enqueue_index_chunking(session, version_id, "chunk-mixed")
            session.commit()
            task_id = task.task_id
        first_worker = IndexChunkingWorker(factory, settings, worker_id="chunk-mixed-one")
        assert first_worker._claim_one() == task_id
        assert first_worker._prepare_task(task_id) == version_id
        with factory() as session:
            prepared = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version_id,
                    IndexVersionInput.file_id == good_id,
                )
            )
            assert prepared is not None and prepared.status == "PREPARED"
            prepared.chunk_status = "RUNNING"
            session.execute(
                update(BackgroundTask)
                .where(BackgroundTask.task_id == task_id)
                .values(lease_until=datetime(2000, 1, 1, tzinfo=UTC))
            )
            session.commit()

        second_worker = IndexChunkingWorker(factory, settings, worker_id="chunk-mixed-two")
        assert second_worker._claim_one() == task_id
        second_worker._process(task_id)
        with factory() as session:
            task = session.get(BackgroundTask, task_id)
            version = session.get(IndexVersion, version_id)
            results = list(
                session.scalars(
                    select(IndexVersionInput).where(IndexVersionInput.index_version_id == version_id)
                )
            )
            assert task is not None and task.status == "COMPLETED"
            assert version is not None and version.chunking_status == "PARTIAL"
            assert {item.chunk_status for item in results} == {"CHUNKED", "PENDING"}
            assert task.checkpoint_json["summary"]["skipped"] == 0
            assert task.checkpoint_json["summary"]["failed"] == 1
            assert task.checkpoint_json["summary"]["chunked"] == 1
    finally:
        client.__exit__(None, None, None)


def test_chunk_worker_records_removed_members_and_explicitly_retries_failed_file(
    tmp_path: Path,
) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "retry-key")
        file_id = _import_and_add(client, kb_id, "retry", b"retry me " * 100)
        version_id = _build_preprocessed_version(factory, settings, kb_id, "retry")
        parsed = read_parsed_text(settings, file_id)
        assert parsed is not None
        (settings.resolved_data_dir / "parsed" / f"{file_id}.json").unlink()
        with factory() as session:
            task = enqueue_index_chunking(session, version_id, "chunk-fail-once")
            session.commit()
            failed_task_id = task.task_id
        worker = IndexChunkingWorker(factory, settings, worker_id="chunk-fail-once")
        assert worker._claim_one() == failed_task_id
        worker._process(failed_task_id)
        with factory() as session:
            item = session.scalar(
                select(IndexVersionInput).where(IndexVersionInput.file_id == file_id)
            )
            assert item is not None
            assert item.chunk_status == "FAILED"
            assert item.chunk_reason_code == "PARSED_CONTENT_UNAVAILABLE"
        write_parsed_text(
            settings,
            file_id,
            str(parsed["content_hash"]),
            str(parsed["text"]),
            cast(dict[str, object], parsed.get("metadata", {})),
            parser=str(parsed.get("parser", "local-text-v1")),
            locations=cast(list[dict[str, object]], parsed.get("locations", [])),
        )
        with factory() as session:
            retry_task = enqueue_index_chunking(
                session,
                version_id,
                "chunk-explicit-retry",
                retry_failed=True,
            )
            session.commit()
            retry_task_id = retry_task.task_id
        retry_worker = IndexChunkingWorker(factory, settings, worker_id="chunk-explicit-retry")
        assert retry_worker._claim_one() == retry_task_id
        retry_worker._process(retry_task_id)
        with factory() as session:
            item = session.scalar(
                select(IndexVersionInput).where(IndexVersionInput.file_id == file_id)
            )
            assert item is not None and item.chunk_status == "CHUNKED"
            assert session.scalar(select(func.count()).select_from(Chunk)) > 0
    finally:
        client.__exit__(None, None, None)


def test_permanent_file_delete_cleans_only_its_reusable_chunks(tmp_path: Path) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "purge-chunk-key")
        deleted_id = _import_and_add(client, kb_id, "purge-chunk", b"delete this chunk " * 80)
        kept_id = _import_and_add(client, kb_id, "keep-chunk", b"keep this chunk " * 80)
        version_id = _build_preprocessed_version(factory, settings, kb_id, "purge-chunk")
        _build_chunks(factory, settings, version_id, "purge-chunk")
        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.file_id == deleted_id)
            ) > 0
            assert session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.file_id == kept_id)
            ) > 0

        current = client.get(f"/api/v1/files/{deleted_id}").json()
        trashed = client.delete(
            f"/api/v1/files/{deleted_id}?expected_version={current['row_version']}",
            headers=_headers("trash-chunk-file"),
        )
        assert trashed.status_code == 200
        purged = client.delete(
            f"/api/v1/trash/file/{deleted_id}",
            params={
                "expected_version": trashed.json()["row_version"],
                "confirmed": "true",
            },
            headers=_headers("purge-chunk-file"),
        )
        assert purged.status_code == 200
        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.file_id == deleted_id)
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.file_id == kept_id)
            ) > 0
    finally:
        client.__exit__(None, None, None)


def test_file_permanent_delete_race_fails_chunk_task_without_stranding_lease(
    tmp_path: Path,
) -> None:
    client, settings, factory = _runtime(tmp_path)
    try:
        kb_id = _create_kb(client, "purge-race-key")
        file_id = _import_and_add(client, kb_id, "purge-race", b"race this delete " * 100)
        version_id = _build_preprocessed_version(factory, settings, kb_id, "purge-race")
        with factory() as session:
            task = enqueue_index_chunking(session, version_id, "chunk-purge-race")
            session.commit()
            task_id = task.task_id
        worker = IndexChunkingWorker(factory, settings, worker_id="chunk-purge-race")
        assert worker._claim_one() == task_id
        original_build = worker._build_for_item

        def build_then_purge(task_arg, version_arg, input_arg, cancel_check):
            result = original_build(task_arg, version_arg, input_arg, cancel_check)
            current = client.get(f"/api/v1/files/{file_id}").json()
            trashed = client.delete(
                f"/api/v1/files/{file_id}?expected_version={current['row_version']}",
                headers=_headers("trash-chunk-purge-race"),
            )
            assert trashed.status_code == 200
            purged = client.delete(
                f"/api/v1/trash/file/{file_id}",
                params={
                    "expected_version": trashed.json()["row_version"],
                    "confirmed": "true",
                },
                headers=_headers("purge-chunk-purge-race"),
            )
            assert purged.status_code == 200
            return result

        cast(Any, worker)._build_for_item = build_then_purge
        worker._process(task_id)
        with factory() as session:
            task = session.get(BackgroundTask, task_id)
            assert task is not None
            assert task.status == "FAILED"
            assert task.error_summary == "INDEX_INPUT_REMOVED"
            assert task.lease_owner is None
            assert session.scalar(select(func.count()).select_from(Chunk)) == 0
    finally:
        client.__exit__(None, None, None)
