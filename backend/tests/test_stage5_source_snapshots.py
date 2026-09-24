from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select

from mindmate.application.evidence_gate import assess_evidence
from mindmate.application.hybrid_search import (
    HybridAssessmentResult,
    HybridCandidate,
    HybridCandidateQuery,
    HybridSearchResult,
)
from mindmate.application.index_preprocessing import get_or_create_default_configs
from mindmate.application.source_snapshots import (
    SourceSnapshotError,
    create_source_snapshots,
    purge_source_snapshots_for_files,
    purge_source_snapshots_for_knowledge_base,
    read_source_snapshot,
)
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Projection
from mindmate.infrastructure.models import (
    Chunk,
    ContentObject,
    EmbeddingRecord,
    FileRecord,
    FtsChunkMap,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    SourceSnapshot,
    new_id,
)
from mindmate.infrastructure.vector_store import SqliteVecAdapter
from mindmate.main import create_app


@dataclass(frozen=True)
class SnapshotData:
    knowledge_base_id: str
    index_version_id: str
    file_id: str
    membership_id: str
    chunk_id: str
    embedding_config_id: str
    vector_store_record_id: str
    query_vector: list[float]
    content: str


@pytest.fixture
def source_runtime(tmp_path: Path):
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
        factory = cast(Any, client.app).state.session_factory
        data = _seed_active_index(factory, settings)
        yield settings, factory, data


def _seed_active_index(
    factory, settings: Settings, *, with_location: bool = True
) -> SnapshotData:
    now = datetime.now(UTC)
    knowledge_base_id = new_id()
    index_version_id = new_id()
    file_id = new_id()
    membership_id = new_id()
    chunk_id = new_id()
    parse_revision_id = new_id()
    source_bytes = f"offline source file {file_id}".encode()
    content_hash = hashlib.sha256(source_bytes).hexdigest()
    content = "向量数据库是一种用于存储和检索向量数据的系统。" + ("固定离线来源内容。" * 180)
    chunk_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    query_vector = np.zeros(512, dtype=np.float32)
    query_vector[0] = 1.0
    vector_store = SqliteVecAdapter(settings.vectors_dir)
    vector_store_record_id = new_id()
    vector_hash = vector_store.vector_hash(query_vector)

    with factory() as session:
        chunking, embedding = get_or_create_default_configs(session)
        session.flush()
        content_object_id = new_id()
        session.add(
            ContentObject(
                content_object_id=content_object_id,
                sha256=content_hash,
                byte_size=len(source_bytes),
                storage_relative_path=f"objects/{file_id}.txt",
                storage_state="READY",
                reference_count=1,
                created_at=now,
                verified_at=now,
            )
        )
        session.flush()

        session.add_all(
            [
                FileRecord(
                    file_id=file_id,
                    content_object_id=content_object_id,
                    display_name="vector-notes.txt",
                    extension=".txt",
                    document_type="TXT",
                    status="PARSED",
                    source_name="vector-notes.txt",
                    content_hash=content_hash,
                    byte_size=len(source_bytes),
                    parse_revision_id=parse_revision_id,
                    created_at=now,
                    updated_at=now,
                    row_version=1,
                ),
                KnowledgeBase(
                    knowledge_base_id=knowledge_base_id,
                    name="离线快照测试",
                    status="READY",
                    active_index_version_id=index_version_id,
                    created_at=now,
                    updated_at=now,
                    row_version=1,
                ),
            ]
        )
        session.flush()
        session.add(
            IndexVersion(
                index_version_id=index_version_id,
                scope_type="KNOWLEDGE_BASE",
                scope_id=knowledge_base_id,
                parse_revision_set_hash="a" * 64,
                chunking_config_id=chunking.chunking_config_id,
                embedding_config_id=embedding.embedding_config_id,
                vector_engine="sqlite-vec",
                vector_engine_version="test",
                status="READY",
                preprocessing_status="COMPLETED",
                chunking_status="COMPLETED",
                embedding_status="COMPLETED",
                    fts_status="COMPLETED",
                input_count=1,
                prepared_count=1,
                failed_count=0,
                created_at=now,
                activated_at=now,
            )
        )
        session.flush()
        session.add(
            KnowledgeBaseFile(
                knowledge_base_file_id=membership_id,
                knowledge_base_id=knowledge_base_id,
                file_id=file_id,
                membership_status="ACTIVE",
                index_state="READY",
                added_at=now,
            )
        )
        session.flush()
        session.add_all(
            [
                Chunk(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    parse_revision_id=parse_revision_id,
                    chunking_config_id=chunking.chunking_config_id,
                    sequence_number=0,
                    heading_path=["第一章", "向量数据库"],
                    page_start=3 if with_location else None,
                    page_end=4 if with_location else None,
                    slide_number=None,
                    line_start=None,
                    line_end=None,
                    content=content,
                    content_hash=chunk_hash,
                    length_unit="UNICODE_CHARACTER",
                    length_value=len(content),
                    created_at=now,
                ),
                IndexVersionInput(
                    index_version_input_id=new_id(),
                    index_version_id=index_version_id,
                    knowledge_base_file_id=membership_id,
                    file_id=file_id,
                    content_hash=content_hash,
                    parse_revision_id=parse_revision_id,
                    membership_added_at=now,
                    ordinal=0,
                    status="PREPARED",
                    prepared_at=now,
                    chunk_status="CHUNKED",
                    chunk_count=1,
                    chunked_at=now,
                    embedding_status="EMBEDDED",
                    embedding_count=1,
                    embedded_at=now,
                    fts_status="INDEXED",
                    fts_count=1,
                    fts_indexed_at=now,
                ),
                EmbeddingRecord(
                    embedding_record_id=new_id(),
                    chunk_id=chunk_id,
                    embedding_config_id=embedding.embedding_config_id,
                    vector_store_record_id=vector_store_record_id,
                    config_fingerprint=embedding.config_fingerprint,
                    vector_hash=vector_hash,
                    status="READY",
                    created_at=now,
                ),
            ]
        )
        session.flush()
        chunk = session.get(Chunk, chunk_id)
        assert chunk is not None
        Fts5Projection().replace_file(
            session,
            index_version_id=index_version_id,
            file_id=file_id,
            parse_revision_id=parse_revision_id,
            chunking_config_id=chunking.chunking_config_id,
            chunks=[chunk],
        )
        session.commit()

    vector_store.upsert(
        embedding_config_id=embedding.embedding_config_id,
        index_version_id=index_version_id,
        vector_store_record_id=vector_store_record_id,
        chunk_id=chunk_id,
        vector=query_vector,
        expected_hash=vector_hash,
    )

    return SnapshotData(
        knowledge_base_id=knowledge_base_id,
        index_version_id=index_version_id,
        file_id=file_id,
        membership_id=membership_id,
        chunk_id=chunk_id,
        embedding_config_id=embedding.embedding_config_id,
        vector_store_record_id=vector_store_record_id,
        query_vector=query_vector.tolist(),
        content=content,
    )


def _supported_result(data: SnapshotData) -> HybridAssessmentResult:
    candidate = HybridCandidate(
        chunk_id=data.chunk_id,
        file_id=data.file_id,
        index_version_id=data.index_version_id,
        fts_rank=1,
        vector_rank=1,
        vector_distance=0.08,
        vector_score=0.92,
        content=data.content,
        sources=("fts", "vector"),
        ranking_rank=1,
        file_title="vector-notes.txt",
    )
    assessment = assess_evidence([candidate], query_text="什么是向量数据库？")
    assert assessment.status == "supported"
    return HybridAssessmentResult(
        retrieval=HybridSearchResult((candidate,), ranking_algorithm="test"),
        assessment=assessment,
    )


def _create(factory, data: SnapshotData, result: HybridAssessmentResult | None = None):
    return create_source_snapshots(
        factory,
        knowledge_base_id=data.knowledge_base_id,
        expected_index_version_id=data.index_version_id,
        result=result or _supported_result(data),
    )


def test_source_snapshot_uses_database_values_and_reloads_after_restart(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
        index_activation_worker_poll_seconds=60,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as first_app:
        factory = cast(Any, first_app.app).state.session_factory
        data = _seed_active_index(factory, settings)
        with factory() as session:
            result = HybridCandidateQuery(
                SqliteVecAdapter(settings.vectors_dir)
            ).search_and_assess_with_status(
                session,
                knowledge_base_id=data.knowledge_base_id,
                index_version_id=data.index_version_id,
                    query_text="向量数据库是一种用于存储和检索向量数据的系统",
                query_vector=data.query_vector,
            )
        assert result.assessment.status == "supported", (
            result.assessment.reason_codes,
            result.assessment.signals,
            result.retrieval.candidates if result.retrieval else None,
        )
        assert result.retrieval is not None
        candidate = replace(
            result.retrieval.candidates[0],
            file_title="C:\\private\\forged.txt",
        )
        forged = replace(
            result,
            retrieval=replace(result.retrieval, candidates=(candidate,)),
        )
        with pytest.raises(SourceSnapshotError, match="RETRIEVAL_EVIDENCE_INVALID"):
            _create(factory, data, forged)

        created = _create(factory, data)
        assert len(created) == 1
        assert created[0].binding_status == "UNBOUND"

        with factory() as session:
            record = session.get(SourceSnapshot, created[0].source_snapshot_id)
            assert record is not None
            assert record.file_name_snapshot == "vector-notes.txt"
            assert record.chunk_id == data.chunk_id
            assert record.index_version_id == data.index_version_id
            assert record.excerpt == data.content[:1200]
            assert len(record.excerpt) == 1200
            assert record.excerpt_sha256 == hashlib.sha256(record.excerpt.encode()).hexdigest()
            assert record.chunk_content_sha256 == hashlib.sha256(data.content.encode()).hexdigest()
            assert record.page_start == 3
            assert record.page_end == 4
            assert record.slide_number is None
            assert record.line_start is None
            assert not hasattr(record, "file_path")
            snapshot_id = record.source_snapshot_id

    with TestClient(create_app(settings), base_url="http://127.0.0.1") as restarted:
        restarted_factory = cast(Any, restarted.app).state.session_factory
        with restarted_factory() as session:
            view = read_source_snapshot(session, snapshot_id)
            assert view.source_status == "AVAILABLE"
            assert view.can_open_source
            assert view.excerpt == data.content[:1200]
            assert view.file_name == "vector-notes.txt"


def test_repeated_creation_is_idempotent_and_missing_location_stays_empty(source_runtime) -> None:
    settings, factory, data = source_runtime
    first = _create(factory, data)
    second = _create(factory, data)
    assert first[0].source_snapshot_id == second[0].source_snapshot_id

    no_location_data = _seed_active_index(factory, settings, with_location=False)
    no_location = _create(factory, no_location_data)[0]

    with factory() as session:
        count = session.scalar(select(func.count()).select_from(SourceSnapshot))
        assert count == 2
        view = read_source_snapshot(session, no_location.source_snapshot_id)
        assert view.page_start is None
        assert view.page_end is None
        assert view.slide_number is None
        assert view.line_start is None
        assert view.line_end is None


def test_non_supported_or_fabricated_candidate_cannot_create_snapshot(source_runtime) -> None:
    _settings, factory, data = source_runtime
    result = _supported_result(data)
    assert result.retrieval is not None
    with pytest.raises(SourceSnapshotError, match="EVIDENCE_NOT_SUPPORTED"):
        _create(factory, data, replace(result, assessment=replace(result.assessment, status="insufficient")))

    candidate = replace(result.retrieval.candidates[0], chunk_id=new_id())
    fabricated_assessment = assess_evidence([candidate], query_text="什么是向量数据库？")
    fabricated_result = HybridAssessmentResult(
        retrieval=HybridSearchResult((candidate,)), assessment=fabricated_assessment
    )
    with pytest.raises(SourceSnapshotError, match="SOURCE_INVALID"):
        _create(factory, data, fabricated_result)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceSnapshot)) == 0


def test_cross_scope_removed_member_trash_and_damaged_mapping_fail_closed(source_runtime) -> None:
    _settings, factory, data = source_runtime
    result = _supported_result(data)
    other_knowledge_base_id = new_id()
    with factory() as session:
        now = datetime.now(UTC)
        session.add(
            KnowledgeBase(
                knowledge_base_id=other_knowledge_base_id,
                name="另一个知识库",
                status="EMPTY",
                created_at=now,
                updated_at=now,
                row_version=1,
            )
        )
        session.commit()
    with pytest.raises(SourceSnapshotError, match="RETRIEVAL_SCOPE_CHANGED"):
        create_source_snapshots(
            factory,
            knowledge_base_id=other_knowledge_base_id,
            expected_index_version_id=data.index_version_id,
            result=result,
        )

    with factory() as session:
        membership = session.get(KnowledgeBaseFile, data.membership_id)
        assert membership is not None
        membership.membership_status = "REMOVED"
        membership.index_state = "REMOVED"
        session.commit()
    with pytest.raises(SourceSnapshotError, match="RETRIEVAL_SCOPE_CHANGED"):
        _create(factory, data)

    with factory() as session:
        membership = session.get(KnowledgeBaseFile, data.membership_id)
        file_record = session.get(FileRecord, data.file_id)
        assert membership is not None and file_record is not None
        membership.membership_status = "ACTIVE"
        membership.index_state = "READY"
        file_record.deleted_at = datetime.now(UTC)
        session.commit()
    with pytest.raises(SourceSnapshotError, match="SOURCE_INVALID"):
        _create(factory, data)

    with factory() as session:
        file_record = session.get(FileRecord, data.file_id)
        assert file_record is not None
        file_record.deleted_at = None
        session.execute(
            delete(FtsChunkMap).where(
                FtsChunkMap.index_version_id == data.index_version_id,
                FtsChunkMap.chunk_id == data.chunk_id,
            )
        )
        session.commit()
    with pytest.raises(SourceSnapshotError, match="SOURCE_INVALID"):
        _create(factory, data)


def test_changed_file_and_index_versions_are_reported_separately(source_runtime) -> None:
    _settings, factory, data = source_runtime
    with factory() as session:
        file_record = session.get(FileRecord, data.file_id)
        version = session.get(IndexVersion, data.index_version_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert file_record is not None and version is not None and knowledge_base is not None
        file_record.content_hash = "c" * 64
        file_record.parse_revision_id = new_id()
        session.commit()
    with pytest.raises(SourceSnapshotError, match="SOURCE_VERSION_CHANGED"):
        _create(factory, data)

    with factory() as session:
        file_record = session.get(FileRecord, data.file_id)
        version = session.get(IndexVersion, data.index_version_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert file_record is not None and version is not None and knowledge_base is not None
        file_record.content_hash = hashlib.sha256(
            f"offline source file {data.file_id}".encode()
        ).hexdigest()
        file_record.parse_revision_id = session.scalar(
            select(IndexVersionInput.parse_revision_id).where(
                IndexVersionInput.index_version_id == data.index_version_id
            )
        )
        version.status = "RETIRED"
        knowledge_base.active_index_version_id = new_id()
        session.commit()
    with pytest.raises(SourceSnapshotError, match="INDEX_VERSION_CHANGED"):
        _create(factory, data)


def test_transaction_rechecks_membership_after_acquiring_write_lock(source_runtime) -> None:
    _settings, factory, data = source_runtime
    engine = factory.kw["bind"]
    injected = False

    def remove_member_before_lock(_conn, _cursor, statement, _parameters, _context, _many):
        nonlocal injected
        if injected or not statement.lstrip().lower().startswith("update knowledge_bases"):
            return
        injected = True
        with factory() as competing_session:
            membership = competing_session.get(KnowledgeBaseFile, data.membership_id)
            assert membership is not None
            membership.membership_status = "REMOVED"
            competing_session.commit()

    event.listen(engine, "before_cursor_execute", remove_member_before_lock)
    try:
        with pytest.raises(SourceSnapshotError, match="RETRIEVAL_SCOPE_CHANGED"):
            _create(factory, data)
    finally:
        event.remove(engine, "before_cursor_execute", remove_member_before_lock)
    assert injected
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceSnapshot)) == 0


def test_transaction_rechecks_active_version_after_concurrent_activation(source_runtime) -> None:
    _settings, factory, data = source_runtime
    engine = factory.kw["bind"]
    injected = False

    def activate_before_lock(_conn, _cursor, statement, _parameters, _context, _many):
        nonlocal injected
        if injected or not statement.lstrip().lower().startswith("update knowledge_bases"):
            return
        injected = True
        with factory() as competing_session:
            knowledge_base = competing_session.get(KnowledgeBase, data.knowledge_base_id)
            version = competing_session.get(IndexVersion, data.index_version_id)
            assert knowledge_base is not None and version is not None
            knowledge_base.active_index_version_id = new_id()
            version.status = "RETIRED"
            competing_session.commit()

    event.listen(engine, "before_cursor_execute", activate_before_lock)
    try:
        with pytest.raises(SourceSnapshotError, match="INDEX_VERSION_CHANGED"):
            _create(factory, data)
    finally:
        event.remove(engine, "before_cursor_execute", activate_before_lock)
    assert injected
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceSnapshot)) == 0


def test_read_marks_trash_stale_scope_and_preserves_original_index_identity(source_runtime) -> None:
    _settings, factory, data = source_runtime
    snapshot = _create(factory, data)[0]
    with factory() as session:
        file_record = session.get(FileRecord, data.file_id)
        assert file_record is not None
        file_record.deleted_at = datetime.now(UTC)
        view = read_source_snapshot(session, snapshot.source_snapshot_id)
        assert view.source_status == "SOURCE_IN_TRASH"
        assert not view.can_open_source
        assert view.excerpt
        file_record.deleted_at = None
        file_record.content_hash = "d" * 64
        session.flush()
        stale = read_source_snapshot(session, snapshot.source_snapshot_id)
        assert stale.source_status == "SOURCE_VERSION_STALE"
        assert not stale.can_open_source

        file_record.content_hash = hashlib.sha256(
            f"offline source file {data.file_id}".encode()
        ).hexdigest()
        session.flush()
        version = session.get(IndexVersion, data.index_version_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert version is not None and knowledge_base is not None
        replacement_id = new_id()
        session.add(
            IndexVersion(
                index_version_id=replacement_id,
                scope_type="KNOWLEDGE_BASE",
                scope_id=data.knowledge_base_id,
                parse_revision_set_hash="e" * 64,
                chunking_config_id=version.chunking_config_id,
                embedding_config_id=version.embedding_config_id,
                vector_engine="sqlite-vec",
                vector_engine_version="test",
                status="READY",
                preprocessing_status="COMPLETED",
                chunking_status="COMPLETED",
                embedding_status="COMPLETED",
                fts_status="COMPLETED",
                input_count=0,
                prepared_count=0,
                failed_count=0,
                created_at=datetime.now(UTC),
                activated_at=datetime.now(UTC),
            )
        )
        version.status = "RETIRED"
        knowledge_base.active_index_version_id = replacement_id
        session.flush()
        retired = read_source_snapshot(session, snapshot.source_snapshot_id)
        assert retired.index_version_id == data.index_version_id
        assert retired.source_status == "INDEX_VERSION_RETIRED"
        assert retired.can_open_source


def test_read_rejects_readded_member_mapping_for_an_older_active_snapshot(source_runtime) -> None:
    _settings, factory, data = source_runtime
    snapshot = _create(factory, data)[0]
    with factory() as session:
        membership = session.get(KnowledgeBaseFile, data.membership_id)
        assert membership is not None
        membership.added_at = datetime.now(UTC)
        session.flush()
        view = read_source_snapshot(session, snapshot.source_snapshot_id)
        assert view.source_status == "SOURCE_MAPPING_INVALID"
        assert not view.can_open_source


def test_permanent_file_delete_clears_body_and_historical_kb_purge_removes_unbound_rows(
    source_runtime,
) -> None:
    _settings, factory, data = source_runtime
    snapshot = _create(factory, data)[0]
    with factory() as session:
        purge_source_snapshots_for_files(session, [data.file_id])
        session.commit()
    with factory() as session:
        row = session.get(SourceSnapshot, snapshot.source_snapshot_id)
        assert row is not None
        assert row.file_id is None and row.chunk_id is None
        assert row.excerpt == ""
        assert row.file_version_snapshot is None
        assert row.chunk_content_sha256 is None
        assert row.source_deleted_at is not None
        view = read_source_snapshot(session, snapshot.source_snapshot_id)
        assert view.source_status == "SOURCE_DELETED"
        assert view.excerpt is None
        assert not view.can_open_source

        purge_source_snapshots_for_knowledge_base(session, data.knowledge_base_id)
        session.commit()
        assert session.get(SourceSnapshot, snapshot.source_snapshot_id) is None


def test_database_file_delete_trigger_sanitizes_snapshot_even_without_service_helper(
    source_runtime,
) -> None:
    _settings, factory, data = source_runtime
    snapshot = _create(factory, data)[0]
    with factory() as session:
        session.execute(delete(FtsChunkMap).where(FtsChunkMap.file_id == data.file_id))
        session.execute(delete(EmbeddingRecord).where(EmbeddingRecord.chunk_id == data.chunk_id))
        session.execute(
            delete(IndexVersionInput).where(IndexVersionInput.file_id == data.file_id)
        )
        session.execute(
            delete(KnowledgeBaseFile).where(KnowledgeBaseFile.file_id == data.file_id)
        )
        session.execute(delete(Chunk).where(Chunk.file_id == data.file_id))
        session.execute(delete(FileRecord).where(FileRecord.file_id == data.file_id))
        session.commit()

    with factory() as session:
        row = session.get(SourceSnapshot, snapshot.source_snapshot_id)
        assert row is not None
        assert row.file_id is None and row.chunk_id is None
        assert row.excerpt == ""
        assert row.source_deleted_at is not None
        view = read_source_snapshot(session, snapshot.source_snapshot_id)
        assert view.source_status == "SOURCE_DELETED"
        assert view.excerpt is None
