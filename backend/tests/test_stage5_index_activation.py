from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from typing import Any, cast

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from mindmate.application.chunking import CHUNK_GENERATION_TASK
from mindmate.application.hybrid_search import HybridCandidateQuery, HybridQueryError
from mindmate.application.index_activation import (
    IndexActivationService,
    IndexActivationWorker,
)
from mindmate.application.index_embedding import INDEX_EMBED_TASK
from mindmate.application.index_fts import INDEX_FTS_TASK
from mindmate.application.index_preprocessing import (
    INDEX_PREPROCESS_TASK,
    fingerprint,
    get_or_create_default_configs,
)
from mindmate.application.vector_search import VectorQueryError, query_vector_top_k
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Projection
from mindmate.infrastructure.models import (
    BackgroundTask,
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
from mindmate.infrastructure.vector_store import SqliteVecAdapter
from mindmate.main import create_app


@dataclass
class ActivationData:
    settings: Settings
    factory: Any
    store: SqliteVecAdapter
    knowledge_base_id: str
    active_version_id: str | None
    candidate_ids: list[str]
    embedding_config_id: str
    file_ids: list[str]
    membership_ids: list[str]
    chunk_ids: list[str]
    record_ids: list[str]
    vectors: list[np.ndarray[Any, Any]]


@pytest.fixture
def activation_runtime(tmp_path: Path):
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
        yield settings, cast(Any, client.app).state.session_factory


def _unit_vector(index: int) -> np.ndarray[Any, Any]:
    vector = np.zeros(512, dtype=np.float32)
    vector[index] = 1.0
    return vector


def _make_task(
    *, task_type: str, index_version_id: str, checkpoint: dict[str, Any], created_at: datetime
) -> BackgroundTask:
    return BackgroundTask(
        task_id=new_id(),
        task_type=task_type,
        status="COMPLETED",
        phase="COMPLETED",
        priority=0,
        idempotency_key=new_id(),
        checkpoint_version=1,
        checkpoint_json={"schema_version": 1, **checkpoint},
        created_at=created_at,
        updated_at=created_at,
        started_at=created_at,
        completed_at=created_at,
        row_version=2,
    )


def _seed_candidate(
    runtime,
    *,
    with_old_active: bool = False,
    candidate_count: int = 1,
    failed_member: str | None = None,
    empty: bool = False,
) -> ActivationData:
    settings, factory = runtime
    now = datetime.now(UTC)
    store = SqliteVecAdapter(settings.vectors_dir)
    projection = Fts5Projection()
    knowledge_base_id = new_id()
    old_version_id = new_id() if with_old_active else None
    candidate_ids = [new_id() for _ in range(candidate_count)]

    file_specs: list[tuple[str, str, str | None, str | None, str]] = []
    if not empty:
        if failed_member != "PARSED_TEXT_EMPTY":
            file_specs.append(("usable", "PARSED", f"parse-{new_id()}", None, "PREPARED"))
        if failed_member is not None:
            parse_revision = None if failed_member == "PARSE_FAILED" else f"parse-{new_id()}"
            file_specs.append(
                (
                    "failed",
                    "PARSE_FAILED" if failed_member == "PARSE_FAILED" else "PARSED",
                    parse_revision,
                    failed_member,
                    "FAILED",
                )
            )

    with factory() as session:
        chunking, embedding = get_or_create_default_configs(session)
        version_ids = ([old_version_id] if old_version_id else []) + candidate_ids
        knowledge_base = KnowledgeBase(
            knowledge_base_id=knowledge_base_id,
            name="索引激活测试",
            status="READY" if with_old_active else "PREPARING",
            active_index_version_id=old_version_id,
            created_at=now,
            updated_at=now,
            row_version=1,
        )
        session.add(knowledge_base)
        session.flush()

        file_records: list[FileRecord] = []
        content_objects: list[ContentObject] = []
        memberships: list[KnowledgeBaseFile] = []
        for ordinal, (label, file_status, parse_revision, _reason, _input_status) in enumerate(
            file_specs
        ):
            file_id = new_id()
            raw = f"源文件 {label} 的离线激活夹具。"
            content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            content_object = ContentObject(
                content_object_id=new_id(),
                sha256=content_hash,
                byte_size=len(raw.encode("utf-8")),
                storage_relative_path=f"objects/{file_id}.txt",
                storage_state="READY",
                reference_count=1,
                created_at=now,
                verified_at=now,
            )
            record = FileRecord(
                file_id=file_id,
                content_object_id=content_object.content_object_id,
                display_name=f"activation-{ordinal}.txt",
                extension=".txt",
                document_type="TXT",
                status=file_status,
                source_name=f"activation-{ordinal}.txt",
                content_hash=content_hash,
                byte_size=len(raw.encode("utf-8")),
                parse_revision_id=parse_revision,
                created_at=now,
                updated_at=now,
                row_version=1,
            )
            membership = KnowledgeBaseFile(
                knowledge_base_file_id=new_id(),
                knowledge_base_id=knowledge_base_id,
                file_id=file_id,
                membership_status="ACTIVE",
                index_state="READY" if with_old_active and label == "usable" else "PENDING",
                added_at=now + timedelta(seconds=ordinal),
            )
            content_objects.append(content_object)
            file_records.append(record)
            memberships.append(membership)
        spec_by_file = {
            file.file_id: spec for file, spec in zip(file_records, file_specs, strict=True)
        }
        pairs = sorted(
            zip(memberships, file_records, strict=True),
            key=lambda pair: pair[0].knowledge_base_file_id,
        )
        memberships = [membership for membership, _file in pairs]
        file_records = [file for _membership, file in pairs]
        session.add_all(content_objects)
        session.add_all(file_records)
        session.add_all(memberships)
        session.flush()

        snapshot_values = [
            {
                "membership_id": membership.knowledge_base_file_id,
                "file_id": file.file_id,
                "content_hash": file.content_hash,
                "parse_revision_id": file.parse_revision_id,
                "membership_added_at": membership.added_at.isoformat(),
            }
            for membership, file in zip(memberships, file_records, strict=True)
        ]
        snapshot_hash = fingerprint({"inputs": snapshot_values})

        valid_members: list[
            tuple[KnowledgeBaseFile, FileRecord, Chunk, EmbeddingRecord, np.ndarray[Any, Any]]
        ] = []
        for membership, file in zip(memberships, file_records, strict=True):
            spec = spec_by_file[file.file_id]
            label, _file_status, parse_revision, reason, input_status = spec
            if input_status != "PREPARED":
                continue
            content = f"阶段五完整性校验资料 {label}，原子激活必须保留旧版本。"
            chunk = Chunk(
                chunk_id=new_id(),
                file_id=file.file_id,
                parse_revision_id=str(parse_revision),
                chunking_config_id=chunking.chunking_config_id,
                sequence_number=0,
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                length_unit="UNICODE_CHARACTER",
                length_value=len(content),
                created_at=now,
            )
            vector = _unit_vector(len(valid_members))
            record = EmbeddingRecord(
                embedding_record_id=new_id(),
                chunk_id=chunk.chunk_id,
                embedding_config_id=embedding.embedding_config_id,
                vector_store_record_id=new_id(),
                config_fingerprint=embedding.config_fingerprint,
                vector_hash=store.vector_hash(vector),
                status="READY",
                created_at=now,
            )
            valid_members.append((membership, file, chunk, record, vector))
            session.add(chunk)
            session.add(record)
        session.flush()

        stage_status = "PARTIAL" if failed_member else "COMPLETED"
        if failed_member == "PARSED_TEXT_EMPTY":
            stage_status = "FAILED"
        for version_ordinal, version_id in enumerate(version_ids):
            is_old = old_version_id is not None and version_id == old_version_id
            is_empty = empty
            version_status = "READY" if is_old else "BUILDING"
            preprocessing_status = "COMPLETED" if is_empty else stage_status
            chunk_status = "NOT_STARTED" if is_empty or stage_status == "FAILED" else stage_status
            embedding_status = (
                "NOT_STARTED" if is_empty or stage_status == "FAILED" else stage_status
            )
            fts_status = "NOT_STARTED" if is_empty or stage_status == "FAILED" else stage_status
            version = IndexVersion(
                index_version_id=version_id,
                scope_type="KNOWLEDGE_BASE",
                scope_id=knowledge_base_id,
                parse_revision_set_hash=snapshot_hash,
                chunking_config_id=chunking.chunking_config_id,
                embedding_config_id=embedding.embedding_config_id,
                vector_engine="sqlite-vec",
                vector_engine_version=store.version,
                status=version_status,
                preprocessing_status=preprocessing_status,
                chunking_status=chunk_status,
                embedding_status=embedding_status,
                fts_status=fts_status,
                input_count=len(memberships),
                prepared_count=len(valid_members),
                failed_count=len(memberships) - len(valid_members),
                created_at=now + timedelta(seconds=version_ordinal),
                preprocessed_at=now,
                activated_at=now if is_old else None,
            )
            session.add(version)
            session.flush()

            for ordinal, (membership, file, _chunk, _record, _vector) in enumerate(valid_members):
                session.add(
                    IndexVersionInput(
                        index_version_input_id=new_id(),
                        index_version_id=version_id,
                        knowledge_base_file_id=membership.knowledge_base_file_id,
                        file_id=file.file_id,
                        content_hash=file.content_hash,
                        parse_revision_id=file.parse_revision_id,
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
                        fts_status="INDEXED",
                        fts_count=1,
                        fts_indexed_at=now,
                    )
                )
            next_ordinal = len(valid_members)
            for membership, file in zip(memberships, file_records, strict=True):
                spec = spec_by_file[file.file_id]
                if spec[4] == "PREPARED":
                    continue
                session.add(
                    IndexVersionInput(
                        index_version_input_id=new_id(),
                        index_version_id=version_id,
                        knowledge_base_file_id=membership.knowledge_base_file_id,
                        file_id=file.file_id,
                        content_hash=file.content_hash,
                        parse_revision_id=file.parse_revision_id,
                        membership_added_at=membership.added_at,
                        ordinal=next_ordinal,
                        status="FAILED",
                        reason_code=spec[3],
                    )
                )
                next_ordinal += 1
            session.flush()

            for _membership, file, chunk, _record, _vector in valid_members:
                projection.replace_file(
                    session,
                    index_version_id=version_id,
                    file_id=file.file_id,
                    parse_revision_id=str(file.parse_revision_id),
                    chunking_config_id=chunking.chunking_config_id,
                    chunks=[chunk],
                )

            if not is_old:
                prep_checkpoint = {
                    "knowledge_base_id": knowledge_base_id,
                    "index_version_id": version_id,
                    "parse_revision_set_hash": snapshot_hash,
                    "chunking_config_fingerprint": chunking.config_fingerprint,
                    "embedding_config_fingerprint": embedding.config_fingerprint,
                }
                session.add(
                    _make_task(
                        task_type=INDEX_PREPROCESS_TASK,
                        index_version_id=version_id,
                        checkpoint=prep_checkpoint,
                        created_at=now,
                    )
                )
                if not is_empty and stage_status != "FAILED":
                    session.add(
                        _make_task(
                            task_type=CHUNK_GENERATION_TASK,
                            index_version_id=version_id,
                            checkpoint={
                                "knowledge_base_id": knowledge_base_id,
                                "index_version_id": version_id,
                                "chunking_config_id": chunking.chunking_config_id,
                                "chunking_config_fingerprint": chunking.config_fingerprint,
                            },
                            created_at=now + timedelta(milliseconds=1),
                        )
                    )
                    session.add(
                        _make_task(
                            task_type=INDEX_EMBED_TASK,
                            index_version_id=version_id,
                            checkpoint={
                                "knowledge_base_id": knowledge_base_id,
                                "index_version_id": version_id,
                                "embedding_config_id": embedding.embedding_config_id,
                                "embedding_config_fingerprint": embedding.config_fingerprint,
                            },
                            created_at=now + timedelta(milliseconds=2),
                        )
                    )
                    session.add(
                        _make_task(
                            task_type=INDEX_FTS_TASK,
                            index_version_id=version_id,
                            checkpoint={
                                "knowledge_base_id": knowledge_base_id,
                                "index_version_id": version_id,
                                "chunking_config_id": chunking.chunking_config_id,
                            },
                            created_at=now + timedelta(milliseconds=3),
                        )
                    )
        session.commit()

        for version_id in version_ids:
            for _membership, _file, chunk, record, vector in valid_members:
                store.upsert(
                    embedding_config_id=embedding.embedding_config_id,
                    index_version_id=version_id,
                    vector_store_record_id=record.vector_store_record_id,
                    chunk_id=chunk.chunk_id,
                    vector=vector,
                    expected_hash=record.vector_hash or "",
                )

    return ActivationData(
        settings=settings,
        factory=factory,
        store=store,
        knowledge_base_id=knowledge_base_id,
        active_version_id=old_version_id,
        candidate_ids=candidate_ids,
        embedding_config_id=embedding.embedding_config_id,
        file_ids=[record.file_id for record in file_records],
        membership_ids=[membership.knowledge_base_file_id for membership in memberships],
        chunk_ids=[chunk.chunk_id for _, _, chunk, _, _ in valid_members],
        record_ids=[record.vector_store_record_id for _, _, _, record, _ in valid_members],
        vectors=[vector for _, _, _, _, vector in valid_members],
    )


def _service(data: ActivationData) -> IndexActivationService:
    return IndexActivationService(data.factory, data.store)


def test_first_activation_is_complete_and_idempotent(activation_runtime) -> None:
    data = _seed_candidate(activation_runtime)
    candidate_id = data.candidate_ids[0]

    assert _service(data).activate_if_ready(candidate_id) == "ACTIVE"
    with data.factory() as session:
        version = session.get(IndexVersion, candidate_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert version is not None and version.status == "READY"
        assert version.activated_at is not None and version.activation_error_code is None
        assert knowledge_base is not None
        assert knowledge_base.active_index_version_id == candidate_id
        assert knowledge_base.status == "READY"
        assert (
            session.scalar(
                select(IndexVersion.index_version_id).where(
                    IndexVersion.scope_id == data.knowledge_base_id,
                    IndexVersion.status == "READY",
                )
            )
            == candidate_id
        )

    with data.factory() as session:
        hits = query_vector_top_k(
            session,
            data.store,
            knowledge_base_id=data.knowledge_base_id,
            index_version_id=candidate_id,
            query_vector=data.vectors[0],
        )
    assert len(hits) == 1
    assert _service(data).activate_if_ready(candidate_id) == "ACTIVE"


def test_atomic_switch_preserves_old_artifacts_and_rejects_building_candidate(
    activation_runtime,
) -> None:
    data = _seed_candidate(activation_runtime, with_old_active=True)
    old_id = data.active_version_id
    candidate_id = data.candidate_ids[0]
    assert old_id is not None

    with data.factory() as session:
        old_hits = query_vector_top_k(
            session,
            data.store,
            knowledge_base_id=data.knowledge_base_id,
            index_version_id=old_id,
            query_vector=data.vectors[0],
        )
        with pytest.raises(VectorQueryError, match="INDEX_VERSION_NOT_AVAILABLE"):
            query_vector_top_k(
                session,
                data.store,
                knowledge_base_id=data.knowledge_base_id,
                index_version_id=candidate_id,
                query_vector=data.vectors[0],
            )
        with pytest.raises(HybridQueryError, match="INDEX_VERSION_NOT_AVAILABLE"):
            HybridCandidateQuery(data.store).search(
                session,
                knowledge_base_id=data.knowledge_base_id,
                index_version_id=candidate_id,
                query_text="阶段五完整性校验",
                query_vector=data.vectors[0],
            )
    assert len(old_hits) == 1

    assert _service(data).activate_if_ready(candidate_id) == "ACTIVE"
    with data.factory() as session:
        old = session.get(IndexVersion, old_id)
        current = session.get(IndexVersion, candidate_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert old is not None and old.status == "RETIRED" and old.retired_at is not None
        assert current is not None and current.status == "READY"
        assert knowledge_base is not None
        assert knowledge_base.active_index_version_id == candidate_id
        assert (
            session.scalar(
                select(IndexVersion.index_version_id).where(
                    IndexVersion.scope_id == data.knowledge_base_id,
                    IndexVersion.status == "READY",
                )
            )
            == candidate_id
        )
        assert Fts5Projection.count(session, old_id) == 1
        assert Fts5Projection.count(session, candidate_id) == 1
    assert (
        data.store.get(
            embedding_config_id=data.embedding_config_id,
            index_version_id=old_id,
            vector_store_record_id=data.record_ids[0],
        )
        is not None
    )


@pytest.mark.parametrize(
    ("corruption", "expected_code"),
    [
        ("chunk", "ACTIVATION_CHUNK_COUNT_MISMATCH"),
        ("vector", "VECTOR_STORE_RECORD_MISSING"),
        ("fts", "ACTIVATION_FTS_MAPPING_MISMATCH"),
        ("dimension", "ACTIVATION_EMBEDDING_CONFIG_INVALID"),
    ],
)
def test_incomplete_artifacts_fail_candidate_and_keep_old_version(
    activation_runtime, corruption: str, expected_code: str
) -> None:
    data = _seed_candidate(activation_runtime, with_old_active=True)
    old_id = data.active_version_id
    candidate_id = data.candidate_ids[0]
    assert old_id is not None
    if corruption == "chunk":
        with data.factory() as session:
            item = session.scalar(
                select(IndexVersionInput).where(IndexVersionInput.index_version_id == candidate_id)
            )
            assert item is not None
            item.chunk_count += 1
            session.commit()
    elif corruption == "vector":
        assert data.store.delete(
            embedding_config_id=data.embedding_config_id,
            index_version_id=candidate_id,
            vector_store_record_id=data.record_ids[0],
        )
    elif corruption == "fts":
        with data.factory() as session:
            assert Fts5Projection().delete_file(session, candidate_id, data.file_ids[0]) == 1
            session.commit()
    else:
        with data.factory() as session:
            from mindmate.infrastructure.models import EmbeddingConfig

            config = session.get(EmbeddingConfig, data.embedding_config_id)
            assert config is not None
            config.vector_dimension = 256
            session.commit()

    assert _service(data).activate_if_ready(candidate_id) == "FAILED"
    with data.factory() as session:
        candidate = session.get(IndexVersion, candidate_id)
        old = session.get(IndexVersion, old_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert candidate is not None and candidate.status == "FAILED"
        assert candidate.activation_error_code == expected_code
        assert old is not None and old.status == "READY"
        assert knowledge_base is not None
        assert knowledge_base.active_index_version_id == old_id
        assert knowledge_base.status == "READY"
        assert Fts5Projection.count(session, old_id) == 1
    assert (
        data.store.get(
            embedding_config_id=data.embedding_config_id,
            index_version_id=old_id,
            vector_store_record_id=data.record_ids[0],
        )
        is not None
    )


def test_unfinished_task_waits_and_partial_files_activate_as_partial(activation_runtime) -> None:
    data = _seed_candidate(activation_runtime, failed_member="PARSE_FAILED")
    candidate_id = data.candidate_ids[0]
    with data.factory() as session:
        task = next(
            task
            for task in session.scalars(
                select(BackgroundTask).where(BackgroundTask.task_type == INDEX_FTS_TASK)
            )
            if task.checkpoint_json["index_version_id"] == candidate_id
        )
        assert task is not None
        task.status = "RUNNING"
        session.commit()
    assert _service(data).activate_if_ready(candidate_id) == "PENDING"
    with data.factory() as session:
        task = session.get(BackgroundTask, task.task_id)
        assert task is not None
        task.status = "COMPLETED"
        session.commit()

    assert _service(data).activate_if_ready(candidate_id) == "ACTIVE"
    with data.factory() as session:
        version = session.get(IndexVersion, candidate_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        states = list(
            session.scalars(
                select(KnowledgeBaseFile.index_state).where(
                    KnowledgeBaseFile.knowledge_base_id == data.knowledge_base_id
                )
            )
        )
        assert version is not None and version.status == "READY"
        assert knowledge_base is not None and knowledge_base.status == "PARTIAL"
        assert sorted(states) == ["FAILED", "READY"]
        hits = HybridCandidateQuery(data.store).search(
            session,
            knowledge_base_id=data.knowledge_base_id,
            index_version_id=candidate_id,
            query_text="阶段五完整性校验资料 usable",
            query_vector=data.vectors[0],
        )
    assert len(hits) == 1
    assert hits[0].file_id == data.file_ids[0]


def test_empty_database_and_empty_text_have_distinct_terminal_states(activation_runtime) -> None:
    empty = _seed_candidate(activation_runtime, empty=True)
    empty_id = empty.candidate_ids[0]
    assert _service(empty).activate_if_ready(empty_id) == "EMPTY"
    with empty.factory() as session:
        version = session.get(IndexVersion, empty_id)
        knowledge_base = session.get(KnowledgeBase, empty.knowledge_base_id)
        assert version is not None and version.status == "EMPTY"
        assert knowledge_base is not None
        assert knowledge_base.status == "EMPTY"
        assert knowledge_base.active_index_version_id is None

    blank = _seed_candidate(activation_runtime, failed_member="PARSED_TEXT_EMPTY")
    blank_id = blank.candidate_ids[0]
    assert _service(blank).activate_if_ready(blank_id) == "FAILED"
    with blank.factory() as session:
        version = session.get(IndexVersion, blank_id)
        knowledge_base = session.get(KnowledgeBase, blank.knowledge_base_id)
        item = session.scalar(
            select(IndexVersionInput).where(IndexVersionInput.index_version_id == blank_id)
        )
        assert version is not None and version.status == "FAILED"
        assert version.activation_error_code == "ACTIVATION_TASK_CHAIN_FAILED"
        assert knowledge_base is not None
        assert knowledge_base.status == "FAILED"
        assert knowledge_base.active_index_version_id is None
        assert item is not None and item.reason_code == "PARSED_TEXT_EMPTY"


def test_newest_candidate_wins_and_older_late_completion_is_superseded(activation_runtime) -> None:
    data = _seed_candidate(activation_runtime, candidate_count=2)
    older_id, newer_id = data.candidate_ids

    assert _service(data).activate_if_ready(older_id) == "SUPERSEDED"
    assert _service(data).activate_if_ready(newer_id) == "ACTIVE"
    with data.factory() as session:
        older = session.get(IndexVersion, older_id)
        newer = session.get(IndexVersion, newer_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert older is not None and older.status == "SUPERSEDED"
        assert older.activation_error_code == "SUPERSEDED_BY_NEWER_VERSION"
        assert newer is not None and newer.status == "READY"
        assert knowledge_base is not None
        assert knowledge_base.active_index_version_id == newer_id


def test_concurrent_activation_attempts_publish_exactly_once(activation_runtime) -> None:
    data = _seed_candidate(activation_runtime, with_old_active=True)
    candidate_id = data.candidate_ids[0]
    barrier = Barrier(2)

    class RacingService(IndexActivationService):
        def _commit_activation(self, candidate):
            barrier.wait(timeout=5)
            return super()._commit_activation(candidate)

    def activate() -> str:
        return RacingService(data.factory, data.store).activate_if_ready(candidate_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: activate(), range(2)))

    assert "ACTIVE" in results
    assert set(results).issubset({"ACTIVE", "RETRY"})
    with data.factory() as session:
        versions = list(
            session.scalars(
                select(IndexVersion).where(IndexVersion.scope_id == data.knowledge_base_id)
            )
        )
        active = session.get(KnowledgeBase, data.knowledge_base_id)
        assert active is not None and active.active_index_version_id == candidate_id
        assert sum(version.status == "READY" for version in versions) == 1


def test_candidate_created_during_audit_blocks_late_activation(activation_runtime) -> None:
    data = _seed_candidate(activation_runtime)
    candidate_id = data.candidate_ids[0]
    audited = Event()
    resume = Event()

    class PausingService(IndexActivationService):
        def _commit_activation(self, candidate):
            audited.set()
            assert resume.wait(timeout=5)
            return super()._commit_activation(candidate)

    def activate() -> str:
        return PausingService(data.factory, data.store).activate_if_ready(candidate_id)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(activate)
        assert audited.wait(timeout=5)
        with data.factory() as session:
            original = session.get(IndexVersion, candidate_id)
            assert original is not None
            newer = IndexVersion(
                index_version_id=new_id(),
                scope_type="KNOWLEDGE_BASE",
                scope_id=data.knowledge_base_id,
                parse_revision_set_hash=original.parse_revision_set_hash,
                chunking_config_id=original.chunking_config_id,
                embedding_config_id=original.embedding_config_id,
                vector_engine="sqlite-vec",
                vector_engine_version=original.vector_engine_version,
                status="BUILDING",
                preprocessing_status="RUNNING",
                chunking_status="NOT_STARTED",
                embedding_status="NOT_STARTED",
                fts_status="NOT_STARTED",
                input_count=0,
                prepared_count=0,
                created_at=original.created_at + timedelta(seconds=5),
            )
            session.add(newer)
            session.commit()
            newer_id = newer.index_version_id
        resume.set()
        assert future.result(timeout=5) == "RETRY"

    assert _service(data).activate_if_ready(candidate_id) == "SUPERSEDED"
    with data.factory() as session:
        assert session.get(IndexVersion, candidate_id).status == "SUPERSEDED"
        assert session.get(KnowledgeBase, data.knowledge_base_id).active_index_version_id is None
        assert session.get(IndexVersion, newer_id).status == "BUILDING"


def test_changed_membership_supersedes_candidate_without_replacing_old_active(
    activation_runtime,
) -> None:
    data = _seed_candidate(activation_runtime, with_old_active=True)
    old_id = data.active_version_id
    candidate_id = data.candidate_ids[0]
    assert old_id is not None
    with data.factory() as session:
        file = session.get(FileRecord, data.file_ids[0])
        assert file is not None
        raw = "新增成员用于使旧输入快照失效。"
        content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        content_object = ContentObject(
            content_object_id=new_id(),
            sha256=content_hash,
            byte_size=len(raw.encode("utf-8")),
            storage_relative_path=f"objects/{new_id()}.txt",
            storage_state="READY",
            reference_count=1,
            created_at=datetime.now(UTC),
        )
        new_file = FileRecord(
            file_id=new_id(),
            content_object_id=content_object.content_object_id,
            display_name="new-member.txt",
            extension=".txt",
            document_type="TXT",
            status="PARSED",
            source_name="new-member.txt",
            content_hash=content_hash,
            byte_size=len(raw.encode("utf-8")),
            parse_revision_id=f"parse-{new_id()}",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            row_version=1,
        )
        session.add_all([content_object, new_file])
        session.flush()
        session.add(
            KnowledgeBaseFile(
                knowledge_base_file_id=new_id(),
                knowledge_base_id=data.knowledge_base_id,
                file_id=new_file.file_id,
                membership_status="ACTIVE",
                index_state="PENDING",
                added_at=datetime.now(UTC) + timedelta(seconds=10),
            )
        )
        session.commit()

    assert _service(data).activate_if_ready(candidate_id) == "SUPERSEDED"
    with data.factory() as session:
        candidate = session.get(IndexVersion, candidate_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert candidate is not None and candidate.status == "SUPERSEDED"
        assert candidate.activation_error_code == "INPUT_SNAPSHOT_CHANGED"
        assert knowledge_base is not None
        assert knowledge_base.active_index_version_id == old_id
        assert session.get(IndexVersion, old_id).status == "READY"


def test_activation_resumes_after_interruption_and_commit_failure_rolls_back(
    activation_runtime,
) -> None:
    data = _seed_candidate(activation_runtime, with_old_active=True)
    old_id = data.active_version_id
    candidate_id = data.candidate_ids[0]
    assert old_id is not None

    class InterruptedService(IndexActivationService):
        def _commit_activation(self, candidate):
            raise RuntimeError("simulated process stop before activation transaction")

    interrupted = IndexActivationWorker(
        data.factory,
        data.settings,
        service=InterruptedService(data.factory, data.store),
    )
    with pytest.raises(RuntimeError, match="simulated process stop"):
        interrupted.run_once()
    with data.factory() as session:
        assert session.get(IndexVersion, candidate_id).status == "BUILDING"
        assert session.get(KnowledgeBase, data.knowledge_base_id).active_index_version_id == old_id

    def fail_activation_commit(session) -> None:
        if any(
            isinstance(item, IndexVersion)
            and item.index_version_id == candidate_id
            and item.status == "READY"
            for item in session.dirty
        ):
            raise RuntimeError("injected activation commit failure")

    event.listen(Session, "before_commit", fail_activation_commit)
    try:
        with pytest.raises(RuntimeError, match="injected activation commit failure"):
            IndexActivationService(data.factory, data.store).activate_if_ready(candidate_id)
    finally:
        event.remove(Session, "before_commit", fail_activation_commit)
    with data.factory() as session:
        candidate = session.get(IndexVersion, candidate_id)
        old = session.get(IndexVersion, old_id)
        knowledge_base = session.get(KnowledgeBase, data.knowledge_base_id)
        assert candidate is not None and candidate.status == "BUILDING"
        assert old is not None and old.status == "READY"
        assert knowledge_base is not None and knowledge_base.active_index_version_id == old_id

    assert _service(data).activate_if_ready(candidate_id) == "ACTIVE"
    with data.factory() as session:
        assert (
            session.get(KnowledgeBase, data.knowledge_base_id).active_index_version_id
            == candidate_id
        )
