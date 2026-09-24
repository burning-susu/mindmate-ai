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

from mindmate.application.hybrid_search import (
    HybridCandidate,
    HybridCandidateQuery,
    HybridQueryError,
    HybridRankingConfig,
    merge_candidates,
    rank_candidates,
)
from mindmate.application.index_preprocessing import (
    get_or_create_default_configs,
)
from mindmate.application.vector_search import (
    VectorQueryError,
    VectorTopKHit,
    VectorTopKQuery,
    query_vector_top_k,
)
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Projection
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


def _prepare_fts_for_hybrid(fixture: VectorFixture) -> None:
    with fixture.factory() as session:
        version = session.get(IndexVersion, fixture.index_version_id)
        assert version is not None
        version.fts_status = "COMPLETED"
        for file_id, chunk_id in zip(fixture.file_ids, fixture.chunk_ids, strict=True):
            chunk = session.get(Chunk, chunk_id)
            item = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == fixture.index_version_id,
                    IndexVersionInput.file_id == file_id,
                )
            )
            assert chunk is not None and item is not None
            item.fts_status = "INDEXED"
            Fts5Projection().replace_file(
                session,
                index_version_id=fixture.index_version_id,
                file_id=file_id,
                parse_revision_id=chunk.parse_revision_id,
                chunking_config_id=chunk.chunking_config_id,
                chunks=[chunk],
            )
        session.commit()


def test_hybrid_search_uses_real_fts_and_vector_scopes_and_deduplicates(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)

    with fixture.factory() as session:
        result = HybridCandidateQuery(fixture.store).search_with_status(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件",
            query_vector=fixture.vectors[0],
        )

    assert result.degraded is False
    assert len(result.candidates) == 3
    assert result.ranking_algorithm == "rrf-exact-diversity-v1"
    assert result.ranking_config == HybridRankingConfig()
    assert [candidate.ranking_rank for candidate in result.candidates] == [1, 2, 3]
    assert all(candidate.rrf_score is not None for candidate in result.candidates)
    assert all(candidate.fts_rank is not None for candidate in result.candidates)
    assert all(candidate.vector_rank is not None for candidate in result.candidates)
    assert all(candidate.sources == ("fts", "vector") for candidate in result.candidates)
    assert all(candidate.file_title for candidate in result.candidates)
    assert all("EXACT_PHRASE" in candidate.ranking_reasons for candidate in result.candidates)
    assert len({candidate.chunk_id for candidate in result.candidates}) == 3
    assert [candidate.fts_rank for candidate in result.candidates] == [1, 2, 3]
    assert [candidate.vector_rank for candidate in result.candidates] == [1, 2, 3]
    with fixture.factory() as session:
        version = session.get(IndexVersion, fixture.index_version_id)
        knowledge_base = session.get(KnowledgeBase, fixture.knowledge_base_id)
        assert version is not None and version.status == "BUILDING"
        assert knowledge_base is not None and knowledge_base.active_index_version_id is None


def test_hybrid_search_assesses_scoped_top_eight_without_activating_index(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)

    with fixture.factory() as session:
        result = HybridCandidateQuery(fixture.store).search_and_assess_with_status(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件 0",
            query_vector=fixture.vectors[0],
        )
    assert result.retrieval is not None
    assert result.assessment.status == "supported"
    assert result.assessment.rules_version == "evidence-gate-v1"
    assert result.assessment.candidate_ids
    assert not hasattr(result.assessment, "citations")
    assert all(
        identity.file_id in fixture.file_ids
        and identity.index_version_id == fixture.index_version_id
        for identity in result.assessment.candidate_ids
    )
    assert all(signal.identity == identity for signal, identity in zip(
        result.assessment.signals,
        result.assessment.candidate_ids,
        strict=True,
    ))
    with fixture.factory() as session:
        version = session.get(IndexVersion, fixture.index_version_id)
        knowledge_base = session.get(KnowledgeBase, fixture.knowledge_base_id)
        assert version is not None and version.status == "BUILDING"
        assert knowledge_base is not None and knowledge_base.active_index_version_id is None


def test_assessment_keeps_missing_route_and_wrong_scope_out_of_insufficient(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)
    query = HybridCandidateQuery(fixture.store)

    with fixture.factory() as session:
        one_route = query.search_and_assess_with_status(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件 0",
            query_vector=None,
        )
        wrong_scope = query.search_and_assess_with_status(
            session,
            knowledge_base_id=fixture.second_knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件 0",
            query_vector=fixture.vectors[0],
        )

    assert one_route.assessment.status == "unavailable"
    assert "VECTOR_ROUTE_NOT_REQUESTED" in one_route.assessment.reason_codes
    assert one_route.assessment.candidate_ids
    assert wrong_scope.assessment.status == "unavailable"
    assert wrong_scope.retrieval_error_code == "INDEX_VERSION_NOT_AVAILABLE"
    assert wrong_scope.assessment.local_message is None


def test_hybrid_single_route_keeps_other_signal_empty(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)
    with fixture.factory() as session:
        fts_only = HybridCandidateQuery(fixture.store).search(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件",
            query_vector=None,
        )
        vector_only = HybridCandidateQuery(fixture.store).search(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="完全不存在的词",
            query_vector=fixture.vectors[0],
        )

    assert fts_only and all(hit.vector_rank is None and hit.vector_score is None for hit in fts_only)
    assert vector_only and all(hit.fts_rank is None and hit.bm25 is None for hit in vector_only)


def test_hybrid_scope_change_between_routes_fails_closed(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)
    actual = VectorTopKQuery(fixture.store)

    class MutatingVectorQuery:
        def search(self, session, **kwargs):
            membership = session.scalar(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.knowledge_base_id == fixture.knowledge_base_id,
                    KnowledgeBaseFile.file_id == fixture.file_ids[0],
                )
            )
            assert membership is not None
            membership.membership_status = "REMOVED"
            session.commit()
            return actual.search(session, **kwargs)

    with fixture.factory() as session:
        query = HybridCandidateQuery(
            fixture.store,
            vector_query=MutatingVectorQuery(),
        )
        with pytest.raises(HybridQueryError, match="RETRIEVAL_SCOPE_CHANGED"):
            query.search(
                session,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_text="固定向量测试文件",
                query_vector=fixture.vectors[0],
            )


def test_assessment_reports_scope_change_as_unavailable(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)
    actual = VectorTopKQuery(fixture.store)

    class MutatingVectorQuery:
        def search(self, session, **kwargs):
            membership = session.scalar(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.knowledge_base_id == fixture.knowledge_base_id,
                    KnowledgeBaseFile.file_id == fixture.file_ids[0],
                )
            )
            assert membership is not None
            membership.membership_status = "REMOVED"
            session.commit()
            return actual.search(session, **kwargs)

    with fixture.factory() as session:
        result = HybridCandidateQuery(
            fixture.store,
            vector_query=MutatingVectorQuery(),
        ).search_and_assess_with_status(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件",
            query_vector=fixture.vectors[0],
        )

    assert result.retrieval is None
    assert result.assessment.status == "unavailable"
    assert result.retrieval_error_code == "RETRIEVAL_SCOPE_CHANGED"
    assert result.assessment.reason_codes == ("RETRIEVAL_SCOPE_CHANGED",)
    assert result.assessment.local_message is None


def test_hybrid_vector_failure_is_explicit_and_optional_degrade(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    _prepare_fts_for_hybrid(fixture)

    class FailedVectorQuery:
        def search(self, session, *, knowledge_base_id, index_version_id, query_vector, k):
            raise VectorStoreError("VECTOR_STORE_UNAVAILABLE")

    with fixture.factory() as session:
        query = HybridCandidateQuery(fixture.store, vector_query=FailedVectorQuery())
        with pytest.raises(HybridQueryError, match="VECTOR_STORE_UNAVAILABLE"):
            query.search(
                session,
                knowledge_base_id=fixture.knowledge_base_id,
                index_version_id=fixture.index_version_id,
                query_text="固定向量测试文件",
                query_vector=fixture.vectors[0],
            )
        degraded = query.search_with_status(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件",
            query_vector=fixture.vectors[0],
            allow_degraded=True,
        )
        assessed = query.search_and_assess_with_status(
            session,
            knowledge_base_id=fixture.knowledge_base_id,
            index_version_id=fixture.index_version_id,
            query_text="固定向量测试文件",
            query_vector=fixture.vectors[0],
            allow_degraded=True,
        )

    assert degraded.degraded is True
    assert degraded.vector_error == "VECTOR_STORE_UNAVAILABLE"
    assert degraded.fts_error is None
    assert degraded.candidates and all(hit.vector_rank is None for hit in degraded.candidates)
    assert all(hit.degraded and hit.vector_error == "VECTOR_STORE_UNAVAILABLE" for hit in degraded.candidates)
    assert all("RRF_FTS" in hit.ranking_reasons for hit in degraded.candidates)
    assert all("RRF_VECTOR" not in hit.ranking_reasons for hit in degraded.candidates)
    assert assessed.assessment.status == "unavailable"
    assert "VECTOR_ERROR:VECTOR_STORE_UNAVAILABLE" in assessed.assessment.reason_codes
    assert assessed.assessment.local_message is None


def test_merge_candidates_has_stable_order_and_no_fake_scores(vector_fixture) -> None:
    fixture: VectorFixture = vector_fixture
    fts = [
        {
            "chunk_id": fixture.chunk_ids[1],
            "file_id": fixture.file_ids[1],
            "index_version_id": fixture.index_version_id,
            "fts_rank": 1,
            "bm25": -2.0,
        },
        {
            "chunk_id": fixture.chunk_ids[0],
            "file_id": fixture.file_ids[0],
            "index_version_id": fixture.index_version_id,
            "fts_rank": 2,
            "bm25": -1.0,
        },
    ]
    vectors = [
        # The vector-only hit must not receive an FTS score or rank.
        VectorTopKHit(
            chunk_id=fixture.chunk_ids[2],
            file_id=fixture.file_ids[2],
            index_version_id=fixture.index_version_id,
            embedding_config_id=fixture.embedding_config_id,
            vector_store_record_id=fixture.record_ids[2],
            distance=0.0,
            score=1.0,
            sqlite_distance=0.0,
            rank=1,
        )
    ]
    merged = merge_candidates(fts, vectors)
    assert [hit.chunk_id for hit in merged] == [fixture.chunk_ids[1], fixture.chunk_ids[2], fixture.chunk_ids[0]]
    assert merged[1].fts_rank is None and merged[1].bm25 is None


def _rank_candidate(
    chunk_id: str,
    file_id: str,
    *,
    fts_rank: int | None = None,
    vector_rank: int | None = None,
    sequence_number: int | None = None,
    file_title: str | None = None,
    heading_path: tuple[str, ...] = (),
    content: str = "",
) -> HybridCandidate:
    return HybridCandidate(
        chunk_id=chunk_id,
        file_id=file_id,
        index_version_id="rank-test-version",
        fts_rank=fts_rank,
        bm25=-1.0 if fts_rank is not None else None,
        vector_rank=vector_rank,
        vector_distance=0.0 if vector_rank is not None else None,
        vector_score=1.0 if vector_rank is not None else None,
        content=content,
        file_title=file_title,
        heading_path=heading_path,
        sequence_number=sequence_number,
    )


def test_rrf_fusion_only_uses_available_ranks_and_preserves_source_signals() -> None:
    fts_only = _rank_candidate("fts", "file-a", fts_rank=1, content="FTS evidence")
    vector_only = _rank_candidate("vector", "file-b", vector_rank=1, content="Vector evidence")
    both = _rank_candidate("both", "file-c", fts_rank=1, vector_rank=1, content="Dual evidence")

    ranked = rank_candidates([vector_only, fts_only, both], query_text="")
    by_id = {candidate.chunk_id: candidate for candidate in ranked}

    assert [candidate.chunk_id for candidate in ranked] == ["both", "fts", "vector"]
    assert by_id["both"].rrf_score == pytest.approx(2 / 61)
    assert by_id["fts"].rrf_score == pytest.approx(1 / 61)
    assert by_id["vector"].rrf_score == pytest.approx(1 / 61)
    assert by_id["fts"].vector_rank is None and by_id["fts"].vector_score is None
    assert by_id["vector"].fts_rank is None and by_id["vector"].bm25 is None


def test_diversity_softly_promotes_other_files_without_dropping_overlapping_chunks() -> None:
    shared = "混合检索候选融合保留原始排名并使用稳定的证据排序。"
    first = _rank_candidate(
        "a-1", "file-a", fts_rank=1, vector_rank=1, sequence_number=10, content=shared
    )
    adjacent = _rank_candidate(
        "a-2", "file-a", fts_rank=2, vector_rank=2, sequence_number=11, content=shared
    )
    other_file = _rank_candidate(
        "b-1", "file-b", fts_rank=3, vector_rank=3, sequence_number=1, content="其他来源里的独立证据。"
    )

    ranked = rank_candidates([adjacent, other_file, first], query_text="")

    assert [candidate.chunk_id for candidate in ranked] == ["a-1", "b-1", "a-2"]
    assert ranked[1].file_id == "file-b"
    assert ranked[2].diversity_adjustment < 0
    assert "adjacent_overlap" in ranked[2].diversity_reasons[1]
    assert {candidate.chunk_id for candidate in ranked} == {"a-1", "a-2", "b-1"}


def test_exact_heading_match_normalizes_case_width_and_punctuation_with_bounded_bonus() -> None:
    strongest = _rank_candidate(
        "strong", "file-a", fts_rank=1, vector_rank=1, content="强相关的检索说明。"
    )
    exact_heading = _rank_candidate(
        "exact",
        "file-b",
        fts_rank=20,
        vector_rank=20,
        file_title="ＲＦＣ－２０２６．０７",
        heading_path=("ＲＦＣ－２０２６．０７ 接口说明",),
        content="编号内容",
    )
    substring = _rank_candidate(
        "substring",
        "file-c",
        fts_rank=2,
        vector_rank=2,
        heading_path=("XRFC 02026 0700 接口说明",),
    )

    ranked = rank_candidates(
        [exact_heading, substring, strongest],
        query_text="rfc-2026/07",
    )
    by_id = {candidate.chunk_id: candidate for candidate in ranked}

    assert by_id["exact"].exact_match_bonus > 0
    assert by_id["exact"].exact_match_fields == ("file_title", "heading")
    assert "EXACT_PHRASE" in by_id["exact"].ranking_reasons
    exact_score = by_id["exact"].ranking_score
    strong_score = by_id["strong"].ranking_score
    assert exact_score is not None and strong_score is not None
    assert exact_score < strong_score
    assert by_id["substring"].exact_match_bonus == 0
    assert "rfc" not in by_id["substring"].exact_match_terms
    assert "2026" not in by_id["substring"].exact_match_terms


def test_short_ascii_term_requires_boundaries_and_never_overrides_stronger_rrf() -> None:
    strong = _rank_candidate(
        "strong", "file-a", fts_rank=1, vector_rank=1, heading_path=("其他资料",)
    )
    substring = _rank_candidate(
        "substring", "file-b", fts_rank=2, vector_rank=2, heading_path=("PRAIRIEAI-like",)
    )
    exact = _rank_candidate(
        "exact", "file-c", fts_rank=30, vector_rank=30, heading_path=("AI",)
    )

    ranked = rank_candidates([exact, substring, strong], query_text="AI")
    by_id = {candidate.chunk_id: candidate for candidate in ranked}

    assert by_id["strong"].ranking_rank == 1
    assert by_id["substring"].exact_match_bonus == 0
    assert by_id["exact"].exact_match_bonus <= HybridRankingConfig().exact_term_bonus
    exact_score = by_id["exact"].ranking_score
    strong_score = by_id["strong"].ranking_score
    assert exact_score is not None and strong_score is not None
    assert exact_score < strong_score


def test_ranking_is_input_order_independent_caps_at_eight_and_accepts_empty_input() -> None:
    candidates = [
        _rank_candidate(f"chunk-{index:02d}", f"file-{index:02d}", fts_rank=4, vector_rank=4)
        for index in range(10)
    ]

    forward = rank_candidates(candidates, query_text="")
    reversed_order = rank_candidates(reversed(candidates), query_text="")

    assert len(forward) == 8
    assert [candidate.chunk_id for candidate in forward] == [
        candidate.chunk_id for candidate in reversed_order
    ]
    assert [candidate.ranking_rank for candidate in forward] == list(range(1, 9))
    assert rank_candidates([], query_text="") == []
