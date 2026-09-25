from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.application.chunking import CHUNK_GENERATION_TASK, enqueue_index_chunking
from mindmate.application.index_embedding import (
    INDEX_EMBED_TASK,
    enqueue_index_embedding,
    validate_embedding_config,
)
from mindmate.application.index_fts import INDEX_FTS_TASK, enqueue_index_fts
from mindmate.application.index_preprocessing import (
    INDEX_PREPROCESS_TASK,
    fingerprint,
)
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Error, Fts5Projection
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    ChunkingConfig,
    EmbeddingConfig,
    EmbeddingRecord,
    FileRecord,
    FtsChunkMap,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from mindmate.infrastructure.vector_store import SqliteVecAdapter, VectorStoreError

_TERMINAL_STAGE_STATUSES = {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"}
_SUCCESS_STAGE_STATUSES = {"COMPLETED", "PARTIAL"}
_TASK_TYPES = (
    INDEX_PREPROCESS_TASK,
    CHUNK_GENERATION_TASK,
    INDEX_EMBED_TASK,
    INDEX_FTS_TASK,
)
logger = logging.getLogger(__name__)


class IndexActivationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _Candidate:
    version_id: str
    knowledge_base_id: str
    expected_active_id: str | None
    knowledge_base_row_version: int
    input_fingerprint: str
    task_signature: tuple[tuple[str, str, str, int], ...]
    usable_membership_ids: frozenset[str]
    partial: bool
    empty: bool


class IndexActivationService:
    """Recheck persisted index outputs and atomically publish a complete version."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        vector_store: SqliteVecAdapter,
        *,
        projection: Fts5Projection | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._vector_store = vector_store
        self._projection = projection or Fts5Projection()

    def activate_if_ready(self, index_version_id: str) -> str:
        """Return ACTIVE, EMPTY, FAILED, SUPERSEDED, PENDING, RETRY, or IGNORED."""
        with self._session_factory() as session:
            version = session.get(IndexVersion, index_version_id)
            if version is None:
                return "IGNORED"
            knowledge_base = session.get(KnowledgeBase, version.scope_id)
            if (
                version.status == "READY"
                and knowledge_base is not None
                and knowledge_base.active_index_version_id == version.index_version_id
            ):
                return "ACTIVE"
            if version.status != "BUILDING" or knowledge_base is None:
                return "IGNORED"
            if knowledge_base.deleted_at is not None:
                session.rollback()
                return self._mark_superseded(index_version_id, "KNOWLEDGE_BASE_IN_TRASH")
            inputs = list(
                session.scalars(
                    select(IndexVersionInput)
                    .where(IndexVersionInput.index_version_id == index_version_id)
                    .order_by(IndexVersionInput.ordinal)
                )
            )
            snapshot = self._snapshot_hash(session, knowledge_base.knowledge_base_id)
            if (
                len(inputs) != version.input_count
                or self._inputs_hash(inputs) != version.parse_revision_set_hash
                or snapshot != version.parse_revision_set_hash
            ):
                session.rollback()
                return self._mark_superseded(index_version_id, "INPUT_SNAPSHOT_CHANGED")
            source_state = self._prepared_sources_state(session, inputs)
            if source_state == "PENDING":
                return "PENDING"
            if source_state != "CURRENT":
                session.rollback()
                return self._mark_superseded(index_version_id, "INPUT_SOURCE_CHANGED")

            task_state = self._task_state(session, version, inputs)
            if task_state == "PENDING":
                return "PENDING"
            if self._newest_version_id(session, version.scope_id) != version.index_version_id:
                session.rollback()
                return self._mark_superseded(index_version_id, "SUPERSEDED_BY_NEWER_VERSION")
            if isinstance(task_state, str):
                session.rollback()
                return self._mark_failed(index_version_id, task_state)
            task_signature = task_state
            if version.input_count == 0:
                try:
                    self._audit_empty(session, version)
                except IndexActivationError as error:
                    session.rollback()
                    return self._mark_failed(
                        index_version_id, error.code, expected_task_signature=task_signature
                    )
                except Fts5Error as error:
                    session.rollback()
                    return self._mark_failed(
                        index_version_id, error.code, expected_task_signature=task_signature
                    )
                except VectorStoreError as error:
                    session.rollback()
                    return self._mark_failed(
                        index_version_id, error.code, expected_task_signature=task_signature
                    )
                candidate = _Candidate(
                    index_version_id,
                    version.scope_id,
                    knowledge_base.active_index_version_id,
                    knowledge_base.row_version,
                    version.parse_revision_set_hash,
                    task_signature,
                    frozenset(),
                    False,
                    True,
                )
            else:
                try:
                    candidate = self._audit_artifacts(
                        session, version, knowledge_base, inputs, task_signature
                    )
                except IndexActivationError as error:
                    session.rollback()
                    return self._mark_failed(
                        index_version_id, error.code, expected_task_signature=task_signature
                    )
                except Fts5Error as error:
                    session.rollback()
                    return self._mark_failed(
                        index_version_id, error.code, expected_task_signature=task_signature
                    )
                except VectorStoreError as error:
                    session.rollback()
                    return self._mark_failed(
                        index_version_id, error.code, expected_task_signature=task_signature
                    )

        if candidate.empty:
            return self._commit_empty(candidate)
        return self._commit_activation(candidate)

    @staticmethod
    def _newest_version_id(session: Session, knowledge_base_id: str) -> str | None:
        return session.scalar(
            select(IndexVersion.index_version_id)
            .where(
                IndexVersion.scope_type == "KNOWLEDGE_BASE",
                IndexVersion.scope_id == knowledge_base_id,
            )
            .order_by(IndexVersion.created_at.desc(), IndexVersion.index_version_id.desc())
            .limit(1)
        )

    @staticmethod
    def _snapshot_values(session: Session, knowledge_base_id: str) -> list[dict[str, Any]]:
        rows = session.execute(
            select(KnowledgeBaseFile, FileRecord)
            .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
            .where(
                KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseFile.membership_status == "ACTIVE",
            )
            .order_by(KnowledgeBaseFile.knowledge_base_file_id)
        ).all()
        return [
            {
                "membership_id": membership.knowledge_base_file_id,
                "file_id": record.file_id,
                "content_hash": record.content_hash,
                "parse_revision_id": record.parse_revision_id,
                "membership_added_at": IndexActivationService._as_utc(
                    membership.added_at
                ).isoformat(),
            }
            for membership, record in rows
        ]

    @classmethod
    def _snapshot_hash(cls, session: Session, knowledge_base_id: str) -> str:
        return fingerprint({"inputs": cls._snapshot_values(session, knowledge_base_id)})

    @staticmethod
    def _prepared_sources_state(session: Session, inputs: list[IndexVersionInput]) -> str:
        for item in inputs:
            if item.status != "PREPARED":
                continue
            membership = session.get(KnowledgeBaseFile, item.knowledge_base_file_id)
            record = session.get(FileRecord, item.file_id)
            if record is not None and (
                record.deleted_at is not None or record.status in {"IMPORTED", "QUEUED", "PARSING"}
            ):
                return "PENDING"
            if (
                membership is None
                or membership.membership_status != "ACTIVE"
                or membership.file_id != item.file_id
                or IndexActivationService._as_utc(membership.added_at)
                != IndexActivationService._as_utc(item.membership_added_at)
                or record is None
                or record.status != "PARSED"
                or record.content_hash != item.content_hash
                or record.parse_revision_id != item.parse_revision_id
            ):
                return "CHANGED"
        return "CURRENT"

    @classmethod
    def _inputs_hash(cls, inputs: list[IndexVersionInput]) -> str:
        values = [
            {
                "membership_id": item.knowledge_base_file_id,
                "file_id": item.file_id,
                "content_hash": item.content_hash,
                "parse_revision_id": item.parse_revision_id,
                "membership_added_at": cls._as_utc(item.membership_added_at).isoformat(),
            }
            for item in inputs
        ]
        return fingerprint({"inputs": values})

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _configurations_current(session: Session, version: IndexVersion) -> bool:
        chunking = session.get(ChunkingConfig, version.chunking_config_id)
        embedding = session.get(EmbeddingConfig, version.embedding_config_id)
        if chunking is None or embedding is None:
            return False
        chunking_fingerprint = fingerprint(
            {
                "config_version": chunking.config_version,
                "algorithm_id": chunking.algorithm_id,
                "measurement_unit": chunking.measurement_unit,
                "target_size": chunking.target_size,
                "min_size": chunking.min_size,
                "max_size": chunking.max_size,
                "overlap_size": chunking.overlap_size,
                "structure_rules_hash": chunking.structure_rules_hash,
            }
        )
        embedding_fingerprint = fingerprint(
            {
                "config_version": embedding.config_version,
                "provider_type": embedding.provider_type,
                "model_name": embedding.model_name,
                "model_revision": embedding.model_revision,
                "vector_dimension": embedding.vector_dimension,
                "normalization": embedding.normalization,
                "distance_metric": embedding.distance_metric,
            }
        )
        return (
            chunking_fingerprint == chunking.config_fingerprint
            and embedding_fingerprint == embedding.config_fingerprint
            and validate_embedding_config(embedding)
        )

    def _task_state(
        self,
        session: Session,
        version: IndexVersion,
        inputs: list[IndexVersionInput],
    ) -> tuple[tuple[str, str, str, int], ...] | str:
        stages = (
            (INDEX_PREPROCESS_TASK, version.preprocessing_status, True),
            (CHUNK_GENERATION_TASK, version.chunking_status, bool(inputs)),
            (INDEX_EMBED_TASK, version.embedding_status, bool(inputs)),
            (INDEX_FTS_TASK, version.fts_status, bool(inputs)),
        )
        task_rows = list(
            session.scalars(select(BackgroundTask).where(BackgroundTask.task_type.in_(_TASK_TYPES)))
        )
        by_type: dict[str, list[BackgroundTask]] = {task_type: [] for task_type in _TASK_TYPES}
        chunking = session.get(ChunkingConfig, version.chunking_config_id)
        embedding = session.get(EmbeddingConfig, version.embedding_config_id)
        for task in task_rows:
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            if checkpoint.get("index_version_id") == version.index_version_id:
                by_type[task.task_type].append(task)

        for task_type, stage_status, required in stages:
            if required and stage_status in {"FAILED", "CANCELLED"}:
                if any(task.status in {"QUEUED", "RUNNING"} for task in by_type[task_type]):
                    return "PENDING"
                return "ACTIVATION_TASK_CHAIN_FAILED"
        if any(
            required and stage_status not in _TERMINAL_STAGE_STATUSES
            for _, stage_status, required in stages
        ):
            return "PENDING"

        signature: list[tuple[str, str, str, int]] = []
        for task_type, stage_status, required in stages:
            matching = by_type[task_type]
            if not required and not matching:
                continue
            if stage_status not in _TERMINAL_STAGE_STATUSES:
                return "PENDING"
            if not matching:
                return "ACTIVATION_TASK_CHAIN_INCOMPLETE"
            if any(task.status in {"QUEUED", "RUNNING"} for task in matching):
                return "PENDING"
            latest = max(
                matching,
                key=lambda task: (
                    self._as_utc(task.created_at),
                    task.task_id,
                ),
            )
            if latest.status != "COMPLETED":
                return "ACTIVATION_TASK_CHAIN_FAILED"
            signature.append((task_type, latest.task_id, latest.status, latest.checkpoint_version))

        if any(status in {"FAILED", "CANCELLED"} for _, status, required in stages if required):
            return "ACTIVATION_TASK_CHAIN_FAILED"
        if any(status not in _SUCCESS_STAGE_STATUSES for _, status, required in stages if required):
            return "PENDING"

        configs = {
            "chunking_config_id": version.chunking_config_id,
            "embedding_config_id": version.embedding_config_id,
        }
        for task_type, task_id, _status, _checkpoint_version in signature:
            task = next(task for task in by_type[task_type] if task.task_id == task_id)
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            if checkpoint.get("index_version_id") != version.index_version_id:
                return "ACTIVATION_TASK_SCOPE_MISMATCH"
            if task_type == INDEX_PREPROCESS_TASK:
                if (
                    checkpoint.get("parse_revision_set_hash") != version.parse_revision_set_hash
                    or not isinstance(checkpoint.get("chunking_config_fingerprint"), str)
                    or not isinstance(checkpoint.get("embedding_config_fingerprint"), str)
                ):
                    return "ACTIVATION_TASK_SNAPSHOT_MISMATCH"
            elif task_type == CHUNK_GENERATION_TASK and (
                checkpoint.get("chunking_config_id") != configs["chunking_config_id"]
                or chunking is None
                or checkpoint.get("chunking_config_fingerprint") != chunking.config_fingerprint
            ):
                return "ACTIVATION_TASK_CONFIG_MISMATCH"
            elif task_type == INDEX_EMBED_TASK and (
                checkpoint.get("embedding_config_id") != configs["embedding_config_id"]
                or embedding is None
                or checkpoint.get("embedding_config_fingerprint") != embedding.config_fingerprint
            ):
                return "ACTIVATION_TASK_CONFIG_MISMATCH"
            elif (
                task_type == INDEX_FTS_TASK
                and checkpoint.get("chunking_config_id") != configs["chunking_config_id"]
            ):
                return "ACTIVATION_TASK_CONFIG_MISMATCH"
        return tuple(signature)

    def _audit_artifacts(
        self,
        session: Session,
        version: IndexVersion,
        knowledge_base: KnowledgeBase,
        inputs: list[IndexVersionInput],
        task_signature: tuple[tuple[str, str, str, int], ...],
    ) -> _Candidate:
        chunking = session.get(ChunkingConfig, version.chunking_config_id)
        embedding = session.get(EmbeddingConfig, version.embedding_config_id)
        if chunking is None or embedding is None:
            raise IndexActivationError("ACTIVATION_CONFIG_MISSING")
        tasks = {
            task_type: session.get(BackgroundTask, task_id)
            for task_type, task_id, _, _ in task_signature
        }
        preprocessing = tasks.get(INDEX_PREPROCESS_TASK)
        if preprocessing is None:
            raise IndexActivationError("ACTIVATION_TASK_CHAIN_INCOMPLETE")
        preprocessing_checkpoint = preprocessing.checkpoint_json or {}
        if (
            preprocessing_checkpoint.get("chunking_config_fingerprint")
            != chunking.config_fingerprint
            or preprocessing_checkpoint.get("embedding_config_fingerprint")
            != embedding.config_fingerprint
        ):
            raise IndexActivationError("ACTIVATION_CONFIG_MISMATCH")
        if (
            version.vector_engine != "sqlite-vec"
            or version.vector_engine_version != self._vector_store.version
        ):
            raise IndexActivationError("ACTIVATION_VECTOR_ENGINE_MISMATCH")
        if embedding.vector_dimension != 512 or not self._configurations_current(session, version):
            raise IndexActivationError("ACTIVATION_EMBEDDING_CONFIG_INVALID")

        input_counts: dict[str, int] = {}
        for item in inputs:
            input_counts[item.status] = input_counts.get(item.status, 0) + 1
        if (
            input_counts.get("PREPARED", 0) != version.prepared_count
            or input_counts.get("SKIPPED", 0) != version.skipped_count
            or input_counts.get("FAILED", 0) != version.failed_count
        ):
            raise IndexActivationError("ACTIVATION_INPUT_COUNT_MISMATCH")

        allowed_vector_records: dict[str, tuple[str, str]] = {}
        required_vector_ids: set[str] = set()
        expected_fts_rows: set[tuple[str, str, str, str, str]] = set()
        usable_membership_ids: set[str] = set()
        total_usable = 0

        for item in inputs:
            if item.status != "PREPARED":
                if item.chunk_count or item.embedding_count or item.fts_count:
                    raise IndexActivationError("ACTIVATION_SKIPPED_INPUT_HAS_OUTPUT")
                continue
            if item.chunk_status not in {"CHUNKED", "FAILED", "SKIPPED"}:
                raise IndexActivationError("ACTIVATION_CHUNK_CHECKPOINT_INCOMPLETE")
            if item.chunk_status != "CHUNKED":
                if item.chunk_count or item.embedding_count or item.fts_count:
                    raise IndexActivationError("ACTIVATION_FAILED_INPUT_HAS_OUTPUT")
                continue

            chunks = list(
                session.scalars(
                    select(Chunk)
                    .where(
                        Chunk.file_id == item.file_id,
                        Chunk.parse_revision_id == item.parse_revision_id,
                        Chunk.chunking_config_id == version.chunking_config_id,
                        Chunk.invalidated_at.is_(None),
                    )
                    .order_by(Chunk.sequence_number)
                )
            )
            if not chunks or len(chunks) != item.chunk_count:
                raise IndexActivationError("ACTIVATION_CHUNK_COUNT_MISMATCH")
            for chunk in chunks:
                if hashlib.sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.content_hash:
                    raise IndexActivationError("ACTIVATION_CHUNK_HASH_MISMATCH")
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            records = list(
                session.scalars(
                    select(EmbeddingRecord).where(
                        EmbeddingRecord.chunk_id.in_(chunk_ids),
                        EmbeddingRecord.embedding_config_id == version.embedding_config_id,
                    )
                )
            )
            ready_by_chunk: dict[str, EmbeddingRecord] = {}
            for record in records:
                if record.status != "READY" or record.invalidated_at is not None:
                    continue
                if (
                    record.config_fingerprint != embedding.config_fingerprint
                    or not record.vector_hash
                ):
                    raise IndexActivationError("ACTIVATION_EMBEDDING_MAPPING_INVALID")
                allowed_vector_records[record.vector_store_record_id] = (
                    record.chunk_id,
                    record.vector_hash,
                )
                ready_by_chunk[record.chunk_id] = record
            if item.embedding_status == "EMBEDDED":
                if item.embedding_count != len(chunks) or set(ready_by_chunk) != set(chunk_ids):
                    raise IndexActivationError("ACTIVATION_EMBEDDING_COUNT_MISMATCH")
                required_vector_ids.update(
                    ready_by_chunk[chunk_id].vector_store_record_id for chunk_id in chunk_ids
                )
            elif item.embedding_status not in {"FAILED", "SKIPPED"}:
                raise IndexActivationError("ACTIVATION_EMBEDDING_CHECKPOINT_INCOMPLETE")
            elif item.embedding_count:
                raise IndexActivationError("ACTIVATION_EMBEDDING_COUNT_MISMATCH")

            if item.fts_status == "INDEXED":
                if item.fts_count != len(chunks):
                    raise IndexActivationError("ACTIVATION_FTS_COUNT_MISMATCH")
                expected_fts_rows.update(
                    (
                        chunk.chunk_id,
                        chunk.file_id,
                        chunk.parse_revision_id,
                        chunk.chunking_config_id,
                        chunk.content_hash,
                    )
                    for chunk in chunks
                )
            elif item.fts_status not in {"FAILED", "SKIPPED"}:
                raise IndexActivationError("ACTIVATION_FTS_CHECKPOINT_INCOMPLETE")
            elif item.fts_count:
                raise IndexActivationError("ACTIVATION_FTS_COUNT_MISMATCH")

            if item.embedding_status == "EMBEDDED" and item.fts_status == "INDEXED":
                total_usable += 1
                usable_membership_ids.add(item.knowledge_base_file_id)

        self._projection.integrity_check(session)
        self._projection.consistency_check(session, version.index_version_id)
        actual_fts_rows = {
            (
                row.chunk_id,
                row.file_id,
                row.parse_revision_id,
                row.chunking_config_id,
                row.content_hash,
            )
            for row in session.scalars(
                select(FtsChunkMap).where(FtsChunkMap.index_version_id == version.index_version_id)
            )
        }
        if actual_fts_rows != expected_fts_rows:
            raise IndexActivationError("ACTIVATION_FTS_MAPPING_MISMATCH")

        try:
            self._vector_store.validate_version(
                version.embedding_config_id,
                version.index_version_id,
                allowed_records=allowed_vector_records,
                required_record_ids=required_vector_ids,
            )
        except VectorStoreError:
            raise

        if total_usable == 0:
            raise IndexActivationError("ACTIVATION_NO_USABLE_INPUTS")
        partial = (
            total_usable != len(inputs)
            or version.preprocessing_status == "PARTIAL"
            or version.chunking_status == "PARTIAL"
            or version.embedding_status == "PARTIAL"
            or version.fts_status == "PARTIAL"
        )
        return _Candidate(
            version.index_version_id,
            knowledge_base.knowledge_base_id,
            knowledge_base.active_index_version_id,
            knowledge_base.row_version,
            version.parse_revision_set_hash,
            task_signature,
            frozenset(usable_membership_ids),
            partial,
            False,
        )

    def _reserve_knowledge_base(
        self, session: Session, candidate: _Candidate
    ) -> KnowledgeBase | None:
        now = datetime.now(UTC)
        locked_id = session.scalar(
            update(KnowledgeBase)
            .where(
                KnowledgeBase.knowledge_base_id == candidate.knowledge_base_id,
                KnowledgeBase.row_version == candidate.knowledge_base_row_version,
                KnowledgeBase.active_index_version_id.is_(None)
                if candidate.expected_active_id is None
                else KnowledgeBase.active_index_version_id == candidate.expected_active_id,
            )
            .values(row_version=KnowledgeBase.row_version + 1, updated_at=now)
            .returning(KnowledgeBase.knowledge_base_id)
        )
        if locked_id != candidate.knowledge_base_id:
            session.rollback()
            return None
        session.expire_all()
        return session.get(KnowledgeBase, candidate.knowledge_base_id)

    def _state_unchanged(self, session: Session, candidate: _Candidate) -> bool:
        version = session.get(IndexVersion, candidate.version_id)
        knowledge_base = session.get(KnowledgeBase, candidate.knowledge_base_id)
        if (
            version is None
            or knowledge_base is None
            or version.scope_type != "KNOWLEDGE_BASE"
            or version.scope_id != candidate.knowledge_base_id
            or version.status != "BUILDING"
            or version.parse_revision_set_hash != candidate.input_fingerprint
            or version.vector_engine != "sqlite-vec"
            or version.vector_engine_version != self._vector_store.version
            or knowledge_base.deleted_at is not None
            or knowledge_base.active_index_version_id != candidate.expected_active_id
            or self._newest_version_id(session, candidate.knowledge_base_id) != candidate.version_id
            or not self._configurations_current(session, version)
            or self._snapshot_hash(session, candidate.knowledge_base_id)
            != candidate.input_fingerprint
        ):
            return False
        inputs = list(
            session.scalars(
                select(IndexVersionInput)
                .where(IndexVersionInput.index_version_id == candidate.version_id)
                .order_by(IndexVersionInput.ordinal)
            )
        )
        return (
            len(inputs) == version.input_count
            and self._inputs_hash(inputs) == candidate.input_fingerprint
            and self._prepared_sources_state(session, inputs) == "CURRENT"
            and self._task_state(session, version, inputs) == candidate.task_signature
        )

    def _audit_empty(self, session: Session, version: IndexVersion) -> None:
        if version.prepared_count or version.skipped_count or version.failed_count:
            raise IndexActivationError("ACTIVATION_EMPTY_VERSION_HAS_INPUTS")
        if (
            session.scalar(
                select(FtsChunkMap.fts_row_id)
                .where(FtsChunkMap.index_version_id == version.index_version_id)
                .limit(1)
            )
            is not None
        ):
            raise IndexActivationError("ACTIVATION_EMPTY_VERSION_HAS_FTS")
        self._projection.integrity_check(session)
        self._projection.consistency_check(session, version.index_version_id)
        self._vector_store.validate_version(
            version.embedding_config_id,
            version.index_version_id,
            allowed_records={},
            required_record_ids=set(),
        )

    def _commit_activation(self, candidate: _Candidate) -> str:
        with self._session_factory() as session:
            knowledge_base = self._reserve_knowledge_base(session, candidate)
            if knowledge_base is None:
                return "RETRY"
            if not self._state_unchanged(session, candidate):
                session.rollback()
                return "RETRY"
            version = session.get(IndexVersion, candidate.version_id)
            if version is None:
                session.rollback()
                return "RETRY"
            old_version = None
            if candidate.expected_active_id is not None:
                old_version = session.get(IndexVersion, candidate.expected_active_id)
                if (
                    old_version is None
                    or old_version.scope_id != candidate.knowledge_base_id
                    or old_version.status != "READY"
                ):
                    session.rollback()
                    return self._mark_failed(candidate.version_id, "ACTIVE_INDEX_STATE_INVALID")
            ready_versions = select(IndexVersion.index_version_id).where(
                IndexVersion.scope_id == candidate.knowledge_base_id,
                IndexVersion.status == "READY",
            )
            if candidate.expected_active_id is not None:
                ready_versions = ready_versions.where(
                    IndexVersion.index_version_id != candidate.expected_active_id
                )
            other_ready = session.scalar(ready_versions.limit(1))
            if other_ready is not None:
                session.rollback()
                return self._mark_failed(candidate.version_id, "MULTIPLE_READY_INDEX_VERSIONS")

            now = datetime.now(UTC)
            if old_version is not None:
                old_version.status = "RETIRED"
                old_version.retired_at = now
            version.status = "READY"
            version.activated_at = now
            version.retired_at = None
            version.activation_error_code = None
            knowledge_base.active_index_version_id = version.index_version_id
            knowledge_base.status = "PARTIAL" if candidate.partial else "READY"
            knowledge_base.updated_at = now
            for membership in session.scalars(
                select(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.knowledge_base_id == candidate.knowledge_base_id,
                    KnowledgeBaseFile.membership_status == "ACTIVE",
                )
            ):
                membership.index_state = (
                    "READY"
                    if membership.knowledge_base_file_id in candidate.usable_membership_ids
                    else "FAILED"
                )
            session.commit()
            return "ACTIVE"

    def _commit_empty(self, candidate: _Candidate) -> str:
        with self._session_factory() as session:
            knowledge_base = self._reserve_knowledge_base(session, candidate)
            if knowledge_base is None:
                return "RETRY"
            if not self._state_unchanged(session, candidate):
                session.rollback()
                return "RETRY"
            version = session.get(IndexVersion, candidate.version_id)
            old_version = (
                session.get(IndexVersion, candidate.expected_active_id)
                if candidate.expected_active_id is not None
                else None
            )
            if version is None or (candidate.expected_active_id and old_version is None):
                session.rollback()
                return "RETRY"
            if old_version is not None:
                old_version.status = "RETIRED"
                old_version.retired_at = datetime.now(UTC)
            version.status = "EMPTY"
            version.activated_at = None
            version.activation_error_code = None
            knowledge_base.active_index_version_id = None
            knowledge_base.status = "EMPTY"
            knowledge_base.updated_at = datetime.now(UTC)
            session.commit()
            return "EMPTY"

    def _mark_failed(
        self,
        version_id: str,
        code: str,
        *,
        expected_task_signature: tuple[tuple[str, str, str, int], ...] | None = None,
    ) -> str:
        with self._session_factory() as session:
            version = session.get(IndexVersion, version_id)
            if version is None or version.status != "BUILDING":
                return "IGNORED"
            knowledge_base = session.get(KnowledgeBase, version.scope_id)
            if knowledge_base is None:
                version.status = "FAILED"
                version.activation_error_code = code
                session.commit()
                return "FAILED"
            snapshot = _Candidate(
                version.index_version_id,
                knowledge_base.knowledge_base_id,
                knowledge_base.active_index_version_id,
                knowledge_base.row_version,
                version.parse_revision_set_hash,
                (),
                frozenset(),
                False,
                False,
            )
            locked = self._reserve_knowledge_base(session, snapshot)
            if locked is None:
                return "RETRY"
            version = session.get(IndexVersion, version_id)
            if (
                version is None
                or version.status != "BUILDING"
                or self._newest_version_id(session, version.scope_id) != version_id
            ):
                session.rollback()
                return "RETRY"
            inputs = list(
                session.scalars(
                    select(IndexVersionInput)
                    .where(IndexVersionInput.index_version_id == version_id)
                    .order_by(IndexVersionInput.ordinal)
                )
            )
            task_state = self._task_state(session, version, inputs)
            if task_state == "PENDING" or (
                expected_task_signature is not None and task_state != expected_task_signature
            ):
                session.rollback()
                return "RETRY"
            version.status = "FAILED"
            version.activation_error_code = code
            active_id = knowledge_base.active_index_version_id
            if active_id is None:
                knowledge_base.status = "FAILED"
            else:
                active = session.get(IndexVersion, active_id)
                knowledge_base.status = self._active_fallback_status(session, active)
            knowledge_base.updated_at = datetime.now(UTC)
            session.commit()
            return "FAILED"

    def _mark_superseded(self, version_id: str, code: str) -> str:
        with self._session_factory() as session:
            version = session.get(IndexVersion, version_id)
            if version is None or version.status != "BUILDING":
                return "IGNORED"
            version.status = "SUPERSEDED"
            version.activation_error_code = code
            knowledge_base = session.get(KnowledgeBase, version.scope_id)
            if (
                knowledge_base is not None
                and self._newest_version_id(session, version.scope_id) == version_id
            ):
                if knowledge_base.active_index_version_id is None:
                    knowledge_base.status = "NEEDS_REBUILD"
                else:
                    active = session.get(IndexVersion, knowledge_base.active_index_version_id)
                    knowledge_base.status = self._active_fallback_status(session, active)
                knowledge_base.updated_at = datetime.now(UTC)
                knowledge_base.row_version += 1
            session.commit()
        return "SUPERSEDED"

    def _active_fallback_status(self, session: Session, active: IndexVersion | None) -> str:
        if active is None or active.status != "READY":
            return "NEEDS_REBUILD"
        inputs = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == active.index_version_id
                )
            )
        )
        input_by_membership = {item.knowledge_base_file_id: item for item in inputs}
        current_members = session.execute(
            select(KnowledgeBaseFile, FileRecord)
            .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
            .where(
                KnowledgeBaseFile.knowledge_base_id == active.scope_id,
                KnowledgeBaseFile.membership_status == "ACTIVE",
            )
        ).all()
        usable = 0
        for membership, record in current_members:
            item = input_by_membership.get(membership.knowledge_base_file_id)
            if (
                item is not None
                and item.status == "PREPARED"
                and item.chunk_status == "CHUNKED"
                and item.embedding_status == "EMBEDDED"
                and item.fts_status == "INDEXED"
                and self._as_utc(item.membership_added_at) == self._as_utc(membership.added_at)
                and record.status == "PARSED"
                and record.deleted_at is None
                and item.content_hash == record.content_hash
                and item.parse_revision_id == record.parse_revision_id
            ):
                usable += 1
        current_snapshot_hash = self._snapshot_hash(session, active.scope_id)
        if usable == 0:
            return "NEEDS_REBUILD"
        if (
            usable != len(current_members)
            or current_snapshot_hash != active.parse_revision_set_hash
        ):
            return "PARTIAL"
        return "READY"


class IndexActivationWorker:
    """Restart-safe scanner for finished candidates awaiting activation."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
        service: IndexActivationService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"index-activation-{uuid7()}"
        self._service = service or IndexActivationService(
            session_factory, SqliteVecAdapter(settings.vectors_dir)
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run, name="mindmate-index-activation-worker", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout))

    def run_once(self) -> list[tuple[str, str]]:
        with self._session_factory() as session:
            version_ids = list(
                session.scalars(
                    select(IndexVersion.index_version_id)
                    .where(IndexVersion.status == "BUILDING")
                    .order_by(IndexVersion.created_at, IndexVersion.index_version_id)
                )
            )
        results = []
        for version_id in version_ids:
            self._enqueue_next_stages(version_id)
            results.append((version_id, self._service.activate_if_ready(version_id)))
        return results

    def _enqueue_next_stages(self, index_version_id: str) -> None:
        with self._session_factory() as session:
            version = session.get(IndexVersion, index_version_id)
            if version is None or version.status != "BUILDING":
                return
            knowledge_base = session.get(KnowledgeBase, version.scope_id)
            if (
                knowledge_base is None
                or knowledge_base.deleted_at is not None
                or version.input_count == 0
            ):
                return

            tasks = list(
                session.scalars(
                    select(BackgroundTask).where(BackgroundTask.task_type.in_(_TASK_TYPES))
                )
            )
            by_type = {task_type: [] for task_type in _TASK_TYPES}
            for task in tasks:
                checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
                if checkpoint.get("index_version_id") == index_version_id:
                    by_type[task.task_type].append(task)

            if version.preprocessing_status in _SUCCESS_STAGE_STATUSES:
                if version.chunking_status == "NOT_STARTED" and not by_type[CHUNK_GENERATION_TASK]:
                    try:
                        enqueue_index_chunking(
                            session,
                            index_version_id,
                            f"index-stage:{index_version_id}:chunk",
                        )
                    except ValueError:
                        version.chunking_status = "FAILED"
                        for item in session.scalars(
                            select(IndexVersionInput).where(
                                IndexVersionInput.index_version_id == index_version_id,
                                IndexVersionInput.status == "PREPARED",
                            )
                        ):
                            item.chunk_status = "FAILED"
                            item.chunk_reason_code = "CHUNKING_CONFIG_INVALID"

            if version.chunking_status in _SUCCESS_STAGE_STATUSES:
                if version.embedding_status == "NOT_STARTED" and not by_type[INDEX_EMBED_TASK]:
                    try:
                        enqueue_index_embedding(
                            session,
                            index_version_id,
                            f"index-stage:{index_version_id}:embedding",
                        )
                    except ValueError:
                        version.embedding_status = "FAILED"
                        for item in session.scalars(
                            select(IndexVersionInput).where(
                                IndexVersionInput.index_version_id == index_version_id,
                                IndexVersionInput.status == "PREPARED",
                                IndexVersionInput.chunk_status == "CHUNKED",
                            )
                        ):
                            item.embedding_status = "FAILED"
                            item.embedding_reason_code = "EMBEDDING_CONFIG_INVALID"
                if version.fts_status == "NOT_STARTED" and not by_type[INDEX_FTS_TASK]:
                    try:
                        enqueue_index_fts(
                            session,
                            index_version_id,
                            f"index-stage:{index_version_id}:fts",
                        )
                    except ValueError:
                        version.fts_status = "FAILED"
                        for item in session.scalars(
                            select(IndexVersionInput).where(
                                IndexVersionInput.index_version_id == index_version_id,
                                IndexVersionInput.status == "PREPARED",
                                IndexVersionInput.chunk_status == "CHUNKED",
                            )
                        ):
                            item.fts_status = "FAILED"
                            item.fts_reason_code = "FTS_CONFIGURATION_INVALID"
            session.commit()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Index activation scan failed")
            self._stop_event.wait(max(0.02, self._settings.index_activation_worker_poll_seconds))
