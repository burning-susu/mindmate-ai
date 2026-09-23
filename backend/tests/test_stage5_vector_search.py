from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mindmate.application.index_preprocessing import (
    get_or_create_default_configs,
)
from mindmate.application.vector_search import (
    VectorQueryError,
    VectorTopKQuery,
    query_vector_top_k,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    Chunk,
    ContentObject,
    EmbeddingRecord,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)
from mindmate.infrastructure.vector_store import (
    SqliteVecAdapter,
    VectorStoreError,
)
from mindmate.main import create_app


@dataclass
class VectorFixture:
    client: TestClient
    settings: Settings
    factory: Any
    store: SqliteVecAdapter
    knowledge_base_id: str
    second_knowledge_base_id: str
    index_version_id: str
    second_index_version_id: str
    embedding_config_id: str
    file_ids: list[str]
    membership_ids: list[str]
    chunk_ids: list[str]
    record_ids: list[str]
    vectors: list[np.ndarray[Any, Any]]


def _unit_vector(index: int) -> np.ndarray[Any, Any]:
    result = np.zeros(512, dtype=np.float32)
    result[index] = 1.0
    return result


def _mixed_vector() -> np.ndarray[Any, Any]:
    result = np.zeros(512, dtype=np.float32)
    result[0] = 0.8
    result[1] = 0.6
    return result


@pytest.fixture
def vector_fixture(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        env="test",
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        factory = cast(Any, client.app).state.session_factory
        now = datetime.now(UTC)
        with factory() as session:
            chunking, embedding = get_or_create_default_configs(session)
            session.commit()
            embedding_fingerprint = embedding.config_fingerprint
        first_kb = KnowledgeBase(
            knowledge_base_id=new_id(),
            name="向量范围 A",
            status="PREPARING",
            created_at=now,
            updated_at=now,
            row_version=1,
        )
        second_kb = KnowledgeBase(
            knowledge_base_id=new_id(),
            name="向量范围 B",
            status="PREPARING",
            created_at=now,
            updated_at=now,
            row_version=1,
        )
        version = IndexVersion(
            index_version_id=new_id(),
            scope_type="KNOWLEDGE_BASE",
            scope_id=first_kb.knowledge_base_id,
            parse_revision_set_hash="a" * 64,
            chunking_config_id=chunking.chunking_config_id,
            embedding_config_id=embedding.embedding_config_id,
            vector_engine="sqlite-vec",
            vector_engine_version=SqliteVecAdapter(settings.vectors_dir).version,
            status="BUILDING",
            preprocessing_status="COMPLETED",
            chunking_status="COMPLETED",
            embedding_status="COMPLETED",
            fts_status="NOT_STARTED",
            input_count=3,
            prepared_count=3,
            created_at=now,
            preprocessed_at=now,
        )
        second_version = IndexVersion(
            index_version_id=new_id(),
            scope_type="KNOWLEDGE_BASE",
            scope_id=second_kb.knowledge_base_id,
            parse_revision_set_hash="b" * 64,
            chunking_config_id=chunking.chunking_config_id,
            embedding_config_id=embedding.embedding_config_id,
            vector_engine="sqlite-vec",
            vector_engine_version=version.vector_engine_version,
            status="BUILDING",
            preprocessing_status="COMPLETED",
            chunking_status="COMPLETED",
            embedding_status="COMPLETED",
            fts_status="NOT_STARTED",
            input_count=1,
            prepared_count=1,
            created_at=now,
            preprocessed_at=now,
        )
        files: list[FileRecord] = []
        content_objects: list[ContentObject] = []
        memberships: list[KnowledgeBaseFile] = []
        chunks: list[Chunk] = []
        inputs: list[IndexVersionInput] = []
        records: list[EmbeddingRecord] = []
        vectors = [_unit_vector(0), _mixed_vector(), _unit_vector(1)]
        for ordinal, vector in enumerate(vectors):
            file_id = new_id()
            content = f"固定向量测试文件 {ordinal}。"
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            content_object = ContentObject(
                content_object_id=new_id(),
                sha256=content_hash,
                byte_size=len(content.encode()),
                storage_relative_path=f"objects/{file_id}.txt",
                storage_state="READY",
                reference_count=1,
                created_at=now,
                verified_at=now,
            )
            file_record = FileRecord(
                file_id=file_id,
                content_object_id=content_object.content_object_id,
                display_name=f"fixed-{ordinal}.txt",
                extension=".txt",
                document_type="TXT",
                status="PARSED",
                source_name=f"fixed-{ordinal}.txt",
                content_hash=content_hash,
                byte_size=len(content.encode()),
                parse_revision_id=f"parse-{ordinal}",
                created_at=now,
                updated_at=now,
                row_version=1,
            )
            membership = KnowledgeBaseFile(
                knowledge_base_file_id=new_id(),
                knowledge_base_id=first_kb.knowledge_base_id,
                file_id=file_id,
                membership_status="ACTIVE",
                index_state="READY",
                added_at=now + timedelta(seconds=ordinal),
            )
            chunk = Chunk(
                chunk_id=new_id(),
                file_id=file_id,
                parse_revision_id=file_record.parse_revision_id,
                chunking_config_id=chunking.chunking_config_id,
                sequence_number=0,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                length_unit="UNICODE_CHARACTER",
                length_value=len(content),
                created_at=now,
            )
            input_row = IndexVersionInput(
                index_version_input_id=new_id(),
                index_version_id=version.index_version_id,
                knowledge_base_file_id=membership.knowledge_base_file_id,
                file_id=file_id,
                content_hash=file_record.content_hash,
                parse_revision_id=file_record.parse_revision_id,
                membership_added_at=membership.added_at,
                ordinal=ordinal,
                status="PREPARED",
                prepared_at=now,
                chunk_status="CHUNKED",
                chunk_count=1,
                chunked_at=now,
                embedding_status="EMBEDDED",
                embedding_count=1,
                embedded_at=now,
                fts_status="PENDING",
            )
            vector_hash = SqliteVecAdapter.vector_hash(vector)
            record = EmbeddingRecord(
                embedding_record_id=new_id(),
                chunk_id=chunk.chunk_id,
                embedding_config_id=embedding.embedding_config_id,
                vector_store_record_id=new_id(),
                config_fingerprint=embedding_fingerprint,
                vector_hash=vector_hash,
                status="READY",
                created_at=now,
            )
            files.append(file_record)
            content_objects.append(content_object)
            memberships.append(membership)
            chunks.append(chunk)
            inputs.append(input_row)
            records.append(record)

        shared_membership = KnowledgeBaseFile(
            knowledge_base_file_id=new_id(),
            knowledge_base_id=second_kb.knowledge_base_id,
            file_id=files[0].file_id,
            membership_status="ACTIVE",
            index_state="READY",
            added_at=now,
        )
        shared_input = IndexVersionInput(
            index_version_input_id=new_id(),
            index_version_id=second_version.index_version_id,
            knowledge_base_file_id=shared_membership.knowledge_base_file_id,
            file_id=files[0].file_id,
            content_hash=files[0].content_hash,
            parse_revision_id=files[0].parse_revision_id,
            membership_added_at=shared_membership.added_at,
            ordinal=0,
            status="PREPARED",
            prepared_at=now,
            chunk_status="CHUNKED",
            chunk_count=1,
            chunked_at=now,
            embedding_status="EMBEDDED",
            embedding_count=1,
            embedded_at=now,
            fts_status="PENDING",
        )

        with factory() as session:
            session.add_all([first_kb, second_kb])
            session.flush()
            session.add_all([version, second_version, *content_objects])
            session.flush()
            session.add_all([*files, *memberships, shared_membership])
            session.flush()
            session.add_all(chunks)
            session.flush()
            session.add_all([*inputs, shared_input])
            session.flush()
            session.add_all(records)
            session.commit()

        store = SqliteVecAdapter(settings.vectors_dir)
        for record, vector in zip(records, vectors, strict=True):
            store.upsert(
                embedding_config_id=embedding.embedding_config_id,
                index_version_id=version.index_version_id,
                vector_store_record_id=record.vector_store_record_id,
                chunk_id=record.chunk_id,
                vector=vector,
                expected_hash=record.vector_hash or "",
            )
        store.upsert(
            embedding_config_id=embedding.embedding_config_id,
            index_version_id=second_version.index_version_id,
            vector_store_record_id=records[0].vector_store_record_id,
            chunk_id=records[0].chunk_id,
            vector=vectors[0],
            expected_hash=records[0].vector_hash or "",
        )
        yield VectorFixture(
            client=client,
            settings=settings,
            factory=factory,
            store=store,
            knowledge_base_id=first_kb.knowledge_base_id,
            second_knowledge_base_id=second_kb.knowledge_base_id,
            index_version_id=version.index_version_id,
            second_index_version_id=second_version.index_version_id,
            embedding_config_id=embedding.embedding_config_id,
            file_ids=[file.file_id for file in files],
            membership_ids=[membership.knowledge_base_file_id for membership in memberships],
            chunk_ids=[chunk.chunk_id for chunk in chunks],
            record_ids=[record.vector_store_record_id for record in records],
            vectors=vectors,
        )


def _query(fixture: VectorFixture, **kwargs: Any):
    with fixture.factory() as session:
        return query_vector_top_k(
            session,
            fixture.store,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_vector=fixture.vectors[0],
            **kwargs,
        )


def test_vector_top_k_orders_scores_and_does_not_change_index_state(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    with fixture.factory() as session:
        before = session.get(IndexVersion, fixture.index_version_id)
        assert before is not None
        before_status = before.status
        before_active = session.get(KnowledgeBase, fixture.knowledge_base_id).active_index_version_id

    hits = _query(fixture, k=3)

    assert [hit.vector_store_record_id for hit in hits] == fixture.record_ids
    assert [hit.rank for hit in hits] == [1, 2, 3]
    assert hits[0].distance == pytest.approx(0.0)
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].distance == pytest.approx(0.2, abs=1e-5)
    assert hits[2].distance == pytest.approx(1.0, abs=1e-5)
    with fixture.factory() as session:
        after = session.get(IndexVersion, fixture.index_version_id)
        assert after is not None and after.status == before_status
        kb = session.get(KnowledgeBase, fixture.knowledge_base_id)
        assert kb is not None and kb.active_index_version_id == before_active


def test_scope_is_applied_before_top_k_and_shared_file_is_independent(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    with fixture.factory() as session:
        removed = session.get(KnowledgeBaseFile, fixture.membership_ids[0])
        assert removed is not None
        removed.membership_status = "REMOVED"
        removed.removed_at = datetime.now(UTC)
        session.commit()

    hits = _query(fixture, k=1)
    assert len(hits) == 1
    assert hits[0].vector_store_record_id == fixture.record_ids[1]

    with fixture.factory() as session:
        removed = session.get(KnowledgeBaseFile, fixture.membership_ids[0])
        assert removed is not None
        removed.membership_status = "ACTIVE"
        removed.added_at = datetime.now(UTC)
        session.commit()
    assert [hit.vector_store_record_id for hit in _query(fixture, k=3)] == [
        fixture.record_ids[1],
        fixture.record_ids[2],
    ]

    with fixture.factory() as session:
        shared_hits = VectorTopKQuery(fixture.store).search(
            session,
            knowledge_base_id=fixture.second_knowledge_base_id,
            index_version_id=fixture.second_index_version_id,
            query_vector=fixture.vectors[0],
            k=1,
        )
    assert [hit.vector_store_record_id for hit in shared_hits] == [fixture.record_ids[0]]


def test_scope_lifecycle_filters_trash_invalid_chunk_and_record(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    with fixture.factory() as session:
        file_record = session.get(FileRecord, fixture.file_ids[0])
        chunk = session.get(Chunk, fixture.chunk_ids[1])
        record = session.scalar(
            select(EmbeddingRecord).where(
                EmbeddingRecord.vector_store_record_id == fixture.record_ids[2]
            )
        )
        assert file_record is not None and chunk is not None and record is not None
        file_record.deleted_at = datetime.now(UTC)
        chunk.invalidated_at = datetime.now(UTC)
        record.status = "INVALIDATED"
        record.invalidated_at = datetime.now(UTC)
        session.commit()

    hits = _query(fixture, k=3)
    assert [hit.vector_store_record_id for hit in hits] == []


def test_query_rejects_bad_vector_k_and_cross_scope_version(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    with fixture.factory() as session:
        with pytest.raises(VectorQueryError, match="VECTOR_TOP_K_INVALID"):
            query_vector_top_k(
                session,
                fixture.store,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_vector=fixture.vectors[0],
                k=31,
            )
        with pytest.raises(VectorQueryError, match="INDEX_VERSION_NOT_AVAILABLE"):
            query_vector_top_k(
                session,
                fixture.store,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.second_index_version_id,
                query_vector=fixture.vectors[0],
            )
        with pytest.raises(VectorStoreError, match="VECTOR_QUERY_INVALID"):
            VectorTopKQuery(fixture.store).search(
                session,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_vector=[0.0, 1.0],
            )
        with pytest.raises(VectorStoreError, match="VECTOR_QUERY_NOT_NORMALIZED"):
            VectorTopKQuery(fixture.store).search(
                session,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_vector=np.zeros(512, dtype=np.float32),
            )
        with pytest.raises(VectorQueryError, match="EMBEDDING_CONFIG_MISMATCH"):
            query_vector_top_k(
                session,
                fixture.store,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                embedding_config_id=new_id(),
                query_vector=fixture.vectors[0],
            )


def test_trashed_knowledge_base_and_invalidated_version_are_unavailable(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    with fixture.factory() as session:
        knowledge_base = session.get(KnowledgeBase, fixture.knowledge_base_id)
        assert knowledge_base is not None
        knowledge_base.deleted_at = datetime.now(UTC)
        session.commit()
        with pytest.raises(VectorQueryError, match="KNOWLEDGE_BASE_NOT_AVAILABLE"):
            query_vector_top_k(
                session,
                fixture.store,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_vector=fixture.vectors[0],
            )

        knowledge_base.deleted_at = None
        version = session.get(IndexVersion, fixture.index_version_id)
        assert version is not None
        version.status = "NEEDS_REBUILD"
        session.commit()
        with pytest.raises(VectorQueryError, match="INDEX_VERSION_NOT_AVAILABLE"):
            query_vector_top_k(
                session,
                fixture.store,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_vector=fixture.vectors[0],
            )


def test_adapter_scope_ties_and_empty_vector_space_are_deterministic(tmp_path: Path) -> None:
    store = SqliteVecAdapter(tmp_path)
    config_id = new_id()
    version_id = new_id()
    vector = _unit_vector(0)
    record_ids = [new_id(), new_id()]
    for record_id, chunk_id in zip(record_ids, [new_id(), new_id()], strict=True):
        store.upsert(
            embedding_config_id=config_id,
            index_version_id=version_id,
            vector_store_record_id=record_id,
            chunk_id=chunk_id,
            vector=vector,
            expected_hash=store.vector_hash(vector),
        )
    allowed = {record_ids[1], record_ids[0]}
    first = store.search(
        embedding_config_id=config_id,
        index_version_id=version_id,
        query_vector=vector,
        allowed_record_ids=allowed,
        k=1,
    )
    second = store.search(
        embedding_config_id=config_id,
        index_version_id=version_id,
        query_vector=vector,
        allowed_record_ids=allowed,
        k=1,
    )
    assert first == second
    assert first[0].vector_store_record_id == min(record_ids)
    assert store.search(
        embedding_config_id=config_id,
        index_version_id=version_id,
        query_vector=vector,
        allowed_record_ids={new_id()},
        k=30,
    ) == []
    store.delete_version(config_id, version_id)
    assert store.search(
        embedding_config_id=config_id,
        index_version_id=version_id,
        query_vector=vector,
        k=30,
    ) == []


def test_query_propagates_vector_store_failure(vector_fixture, monkeypatch) -> None:
    fixture: VectorFixture = vector_fixture

    def fail(**_kwargs: Any):
        raise VectorStoreError("VECTOR_STORE_UNAVAILABLE")

    monkeypatch.setattr(fixture.store, "search", fail)
    with fixture.factory() as session:
        with pytest.raises(VectorStoreError, match="VECTOR_STORE_UNAVAILABLE"):
            query_vector_top_k(
                session,
                fixture.store,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_vector=fixture.vectors[0],
            )
