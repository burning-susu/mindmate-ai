from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.ai.embeddings.manifest import MODEL_ARTIFACT_FINGERPRINT, MODEL_REVISION
from mindmate.ai.embeddings.model_manager import ModelManager, ModelManagerError
from mindmate.application.index_embedding import (
    INDEX_EMBED_TASK,
    validate_embedding_config,
)
from mindmate.application.tasks import (
    add_event,
    checkpoint_task,
    claim_next_serial_task,
    finish_attempt,
    interrupt_owned_tasks,
    renew_task_lease,
)
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
    new_id,
)
from mindmate.infrastructure.vector_store import (
    VECTOR_DIMENSION,
    SqliteVecAdapter,
    VectorStoreError,
)

FloatVector = NDArray[np.float32]


class EmbeddingRuntime(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> FloatVector: ...


class WorkerFailure(RuntimeError):
    def __init__(self, code: str, *, model_failure: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.model_failure = model_failure


class IndexEmbeddingWorker:
    """Durable single-concurrency worker for verified local 512-dimensional embeddings."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
        vector_store: SqliteVecAdapter | None = None,
        model_manager: ModelManager | None = None,
        embedding_runtime_factory: Callable[[], EmbeddingRuntime] | None = None,
        batch_size: int = 16,
    ) -> None:
        if not 1 <= batch_size <= 16:
            raise ValueError("Embedding batch size must be between 1 and 16.")
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"index-embed-{uuid7()}"
        self._vector_store = vector_store or SqliteVecAdapter(settings.vectors_dir)
        self._model_manager = model_manager or ModelManager(settings.model_dir)
        self._runtime_factory = embedding_runtime_factory
        self._batch_size = batch_size
        self._runtime: EmbeddingRuntime | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-index-embedding-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout))

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                task_id = self._claim_one()
                if task_id is None:
                    self._stop_event.wait(
                        max(0.02, self._settings.index_embedding_worker_poll_seconds)
                    )
                    continue
                try:
                    self._process(task_id)
                except Exception:
                    self._fail(task_id, "EMBEDDING_TASK_FAILED")
        finally:
            with self._session_factory() as session:
                interrupt_owned_tasks(session, self.worker_id)
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            task = claim_next_serial_task(
                session,
                INDEX_EMBED_TASK,
                self.worker_id,
                self._settings.index_embedding_worker_lease_seconds,
            )
            if task is None:
                return None
            task.phase = "EMBEDDING"
            session.commit()
            return task.task_id

    def _process(self, task_id: str) -> None:
        index_version_id = self._prepare_task(task_id)
        if index_version_id is None:
            return
        self._reset_in_progress_inputs(task_id, index_version_id)
        while not self._stop_event.is_set():
            with self._session_factory() as session:
                task = session.get(BackgroundTask, task_id)
                version = session.get(IndexVersion, index_version_id)
                if task is None or version is None:
                    return
                if task.status == "CANCELLED":
                    self._mark_cancelled(session, version)
                    return
                if task.status != "RUNNING" or task.lease_owner != self.worker_id:
                    return
                item = session.scalar(
                    select(IndexVersionInput)
                    .where(
                        IndexVersionInput.index_version_id == index_version_id,
                        IndexVersionInput.status == "PREPARED",
                        IndexVersionInput.chunk_status == "CHUNKED",
                        IndexVersionInput.embedding_status.in_(
                            ["PENDING", "RUNNING"]
                        ),
                    )
                    .order_by(IndexVersionInput.ordinal)
                    .limit(1)
                )
                if item is None:
                    self._complete(session, task, version)
                    return
                item.embedding_status = "RUNNING"
                item.embedding_reason_code = None
                session.commit()
                input_id = item.index_version_input_id

            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(
                target=self._lease_heartbeat,
                args=(task_id, heartbeat_stop),
                name="mindmate-index-embedding-lease",
                daemon=True,
            )
            heartbeat.start()
            try:
                try:
                    outcome, count, reason = self._embed_input(
                        task_id, index_version_id, input_id
                    )
                except WorkerFailure as error:
                    if error.model_failure:
                        self._fail_all_pending(task_id, index_version_id, error.code)
                        return
                    outcome, count, reason = "FAILED", 0, error.code
                except VectorStoreError:
                    outcome, count, reason = "FAILED", 0, "VECTOR_STORE_UNAVAILABLE"
                except Exception:
                    outcome, count, reason = "FAILED", 0, "EMBEDDING_ITEM_FAILED"
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=1)

            if outcome == "CANCELLED":
                self._mark_cancelled_by_id(task_id, index_version_id)
                return
            self._record_input_result(
                task_id, index_version_id, input_id, outcome, reason, count
            )

    def _prepare_task(self, task_id: str) -> str | None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None:
                return None
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            index_version_id = checkpoint.get("index_version_id")
            version = (
                session.get(IndexVersion, index_version_id)
                if isinstance(index_version_id, str)
                else None
            )
            if task.status == "CANCELLED":
                if version is not None:
                    self._mark_cancelled(session, version)
                return None
            if task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return None
            if version is None or version.status != "BUILDING":
                self._finish_task(session, task, "FAILED", "INDEX_VERSION_NOT_BUILDING")
                return None
            config = session.get(EmbeddingConfig, version.embedding_config_id)
            if config is None or not validate_embedding_config(config):
                self._finish_task(session, task, "FAILED", "EMBEDDING_CONFIG_UNVERIFIED")
                version.embedding_status = "FAILED"
                session.commit()
                return None
            if (
                checkpoint.get("embedding_config_id") != version.embedding_config_id
                or checkpoint.get("embedding_config_fingerprint") != config.config_fingerprint
                or checkpoint.get("model_revision") != MODEL_REVISION
                or checkpoint.get("tokenizer_fingerprint") != MODEL_ARTIFACT_FINGERPRINT
            ):
                version.embedding_status = "FAILED"
                self._finish_task(session, task, "FAILED", "EMBEDDING_SNAPSHOT_MISMATCH")
                return None
            if version.chunking_status not in {"COMPLETED", "PARTIAL"}:
                version.embedding_status = "FAILED"
                self._finish_task(session, task, "FAILED", "CHUNKING_NOT_COMPLETED")
                return None

            inputs = list(
                session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == index_version_id
                    )
                )
            )
            for item in inputs:
                if item.status != "PREPARED" or item.chunk_status != "CHUNKED":
                    item.embedding_status = "SKIPPED"
                    item.embedding_reason_code = "CHUNKS_NOT_AVAILABLE"
                    item.embedding_count = 0
                    item.embedded_at = datetime.now(UTC)
                elif item.embedding_status == "RUNNING" or (
                    checkpoint.get("retry_failed") is True
                    and item.embedding_status == "FAILED"
                ):
                    item.embedding_status = "PENDING"
                    item.embedding_reason_code = None
                    item.embedding_count = 0
                    item.embedded_at = None
            version.embedding_status = "RUNNING"
            version.status = "BUILDING"
            version.vector_engine_version = self._vector_store.version
            version.artifact_relative_path = (
                f"vectors/{version.embedding_config_id}/{version.index_version_id}"
            )
            checkpoint["next_ordinal"] = 0
            checkpoint["results"] = []
            checkpoint_task(session, task, "EMBEDDING", checkpoint, progress=0)
            session.commit()
            return version.index_version_id

    def _reset_in_progress_inputs(self, task_id: str, index_version_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING":
                return
            session.execute(
                update(IndexVersionInput)
                .where(
                    IndexVersionInput.index_version_id == index_version_id,
                    IndexVersionInput.status == "PREPARED",
                    IndexVersionInput.embedding_status == "RUNNING",
                )
                .values(embedding_status="PENDING", embedding_reason_code=None)
            )
            session.commit()

    def _embed_input(
        self, task_id: str, index_version_id: str, input_id: str
    ) -> tuple[str, int, str | None]:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if task is None or item is None or version is None:
                return "FAILED", 0, "INDEX_INPUT_NOT_FOUND"
            if not self._owns_task(task):
                return "CANCELLED", 0, None
            valid, reason = self._validate_input(session, item, version)
            if not valid:
                return self._stale_outcome(reason), 0, reason
            config = session.get(EmbeddingConfig, version.embedding_config_id)
            if config is None or not validate_embedding_config(config):
                raise WorkerFailure("EMBEDDING_CONFIG_UNVERIFIED", model_failure=True)
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
            if (
                not chunks
                or [chunk.sequence_number for chunk in chunks] != list(range(len(chunks)))
                or len(chunks) != item.chunk_count
                or any(not chunk.content.strip() for chunk in chunks)
                or any(
                    sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.content_hash
                    for chunk in chunks
                )
            ):
                return "FAILED", 0, "CHUNK_SET_UNAVAILABLE"
            chunk_data = [
                (chunk.chunk_id, chunk.content, chunk.content_hash) for chunk in chunks
            ]
            reserved = self._reserve_records(
                session, chunks, version.embedding_config_id, config.config_fingerprint
            )
            session.commit()

        resolved: dict[str, tuple[FloatVector, str]] = {}
        reserved_by_record = {row[3]: row for row in reserved}
        missing: list[tuple[str, str, str, str]] = []
        for chunk_id, content, content_hash, record_id, vector_id, vector_hash in reserved:
            current = self._vector_store.get(
                embedding_config_id=config.embedding_config_id,
                index_version_id=index_version_id,
                vector_store_record_id=vector_id,
            )
            if current is not None:
                vector, stored_chunk_id, actual_hash = current
                if stored_chunk_id != chunk_id or (vector_hash and actual_hash != vector_hash):
                    raise WorkerFailure("VECTOR_RECORD_CONFLICT")
                resolved[record_id] = (vector, actual_hash)
                self._persist_vector_hash(record_id, actual_hash)
                continue
            shared = self._find_shared_vector(
                config.embedding_config_id,
                index_version_id,
                chunk_id,
                vector_id,
                vector_hash,
            )
            if shared is not None:
                publish_state, publish_reason = self._publish_state(
                    task_id, index_version_id, input_id
                )
                if publish_state != "READY":
                    if publish_state == "STALE":
                        self._delete_version_records(
                            config.embedding_config_id,
                            index_version_id,
                            [item[4] for item in reserved],
                        )
                        return self._stale_outcome(publish_reason), 0, publish_reason
                    return "CANCELLED", 0, None
                vector, actual_hash = shared
                self._vector_store.upsert(
                    embedding_config_id=config.embedding_config_id,
                    index_version_id=index_version_id,
                    vector_store_record_id=vector_id,
                    chunk_id=chunk_id,
                    vector=vector,
                    expected_hash=actual_hash,
                )
                self._persist_vector_hash(record_id, actual_hash)
                resolved[record_id] = (vector, actual_hash)
                continue
            missing.append((chunk_id, content, content_hash, record_id))

        for offset in range(0, len(missing), self._batch_size):
            if self._stop_event.is_set() or not self._can_continue(task_id):
                return "CANCELLED", 0, None
            batch = missing[offset : offset + self._batch_size]
            runtime = self._load_runtime()
            try:
                vectors = np.asarray(
                    runtime.embed_documents([item[1] for item in batch]), dtype=np.float32
                )
            except WorkerFailure:
                raise
            except Exception as error:
                code = getattr(error, "code", None)
                stable_code = (
                    code
                    if isinstance(code, str) and code.isupper() and len(code) <= 80
                    else "EMBEDDING_INFERENCE_FAILED"
                )
                raise WorkerFailure(stable_code) from None
            if vectors.shape != (len(batch), VECTOR_DIMENSION) or not np.isfinite(vectors).all():
                raise WorkerFailure("EMBEDDING_VECTOR_INVALID")
            hashes = [self._vector_store.vector_hash(row) for row in vectors]
            if any(abs(float(np.linalg.norm(row)) - 1.0) > 1e-4 for row in vectors):
                raise WorkerFailure("EMBEDDING_NORMALIZATION_INVALID")
            publish_state, publish_reason = self._publish_state(
                task_id, index_version_id, input_id
            )
            if publish_state != "READY":
                if publish_state == "STALE":
                    self._delete_version_records(
                        config.embedding_config_id,
                        index_version_id,
                        [item[4] for item in reserved],
                    )
                    return self._stale_outcome(publish_reason), 0, publish_reason
                return "CANCELLED", 0, None
            self._persist_vector_hashes(
                [item[3] for item in batch], hashes, config.config_fingerprint
            )
            for (chunk_id, _content, _content_hash, record_id), vector, vector_hash in zip(
                batch, vectors, hashes, strict=True
            ):
                record = reserved_by_record[record_id]
                vector_id = record[4]
                self._vector_store.upsert(
                    embedding_config_id=config.embedding_config_id,
                    index_version_id=index_version_id,
                    vector_store_record_id=vector_id,
                    chunk_id=chunk_id,
                    vector=vector,
                    expected_hash=vector_hash,
                )
                resolved[record_id] = (vector.copy(), vector_hash)

        return self._finalize_input(
            task_id,
            index_version_id,
            config.embedding_config_id,
            input_id,
            chunk_data,
            reserved,
            resolved,
        )

    def _reserve_records(
        self,
        session: Session,
        chunks: list[Chunk],
        embedding_config_id: str,
        config_fingerprint: str,
    ) -> list[tuple[str, str, str, str, str, str | None]]:
        now = datetime.now(UTC)
        reserved: list[tuple[str, str, str, str, str, str | None]] = []
        for chunk in chunks:
            record = session.scalar(
                select(EmbeddingRecord).where(
                    EmbeddingRecord.chunk_id == chunk.chunk_id,
                    EmbeddingRecord.embedding_config_id == embedding_config_id,
                )
            )
            if record is None:
                record = EmbeddingRecord(
                    embedding_record_id=new_id(),
                    chunk_id=chunk.chunk_id,
                    embedding_config_id=embedding_config_id,
                    vector_store_record_id=new_id(),
                    config_fingerprint=config_fingerprint,
                    vector_hash=None,
                    status="PENDING",
                    created_at=now,
                )
                session.add(record)
                session.flush()
            elif record.config_fingerprint != config_fingerprint:
                raise WorkerFailure("EMBEDDING_CONFIG_FINGERPRINT_MISMATCH")
            elif record.invalidated_at is not None or record.status == "INVALIDATED":
                record.invalidated_at = None
                record.vector_hash = None
                record.status = "PENDING"
            reserved.append(
                (
                    chunk.chunk_id,
                    chunk.content,
                    chunk.content_hash,
                    record.embedding_record_id,
                    record.vector_store_record_id,
                    record.vector_hash,
                )
            )
        return reserved

    def _find_shared_vector(
        self,
        embedding_config_id: str,
        current_version_id: str,
        chunk_id: str,
        vector_id: str,
        expected_hash: str | None,
    ) -> tuple[FloatVector, str] | None:
        with self._session_factory() as session:
            chunk = session.get(Chunk, chunk_id)
            if chunk is None:
                return None
            candidates = list(
                session.scalars(
                    select(IndexVersion.index_version_id)
                    .join(
                        IndexVersionInput,
                        IndexVersionInput.index_version_id == IndexVersion.index_version_id,
                    )
                    .where(
                        IndexVersion.index_version_id != current_version_id,
                        IndexVersion.embedding_config_id == embedding_config_id,
                        IndexVersion.chunking_config_id == chunk.chunking_config_id,
                        IndexVersionInput.file_id == chunk.file_id,
                        IndexVersionInput.parse_revision_id == chunk.parse_revision_id,
                        IndexVersionInput.status == "PREPARED",
                        IndexVersionInput.chunk_status == "CHUNKED",
                        IndexVersionInput.embedding_status == "EMBEDDED",
                    )
                    .order_by(IndexVersion.created_at)
                )
            )
        for candidate_id in candidates:
            try:
                stored = self._vector_store.get(
                    embedding_config_id=embedding_config_id,
                    index_version_id=candidate_id,
                    vector_store_record_id=vector_id,
                )
            except VectorStoreError:
                continue
            if stored is None:
                continue
            vector, stored_chunk_id, actual_hash = stored
            if stored_chunk_id != chunk_id or (expected_hash and expected_hash != actual_hash):
                raise WorkerFailure("VECTOR_RECORD_CONFLICT")
            return vector, actual_hash
        return None

    def _persist_vector_hash(self, record_id: str, vector_hash: str) -> None:
        self._persist_vector_hashes([record_id], [vector_hash], None)

    def _persist_vector_hashes(
        self,
        record_ids: list[str],
        hashes: list[str],
        config_fingerprint: str | None,
    ) -> None:
        with self._session_factory() as session:
            for record_id, vector_hash in zip(record_ids, hashes, strict=True):
                record = session.get(EmbeddingRecord, record_id)
                if record is None:
                    raise WorkerFailure("EMBEDDING_RECORD_REMOVED")
                if config_fingerprint and record.config_fingerprint != config_fingerprint:
                    raise WorkerFailure("EMBEDDING_CONFIG_FINGERPRINT_MISMATCH")
                if record.vector_hash is not None and record.vector_hash != vector_hash:
                    raise WorkerFailure("EMBEDDING_VECTOR_HASH_CONFLICT")
                record.vector_hash = vector_hash
                record.status = "PENDING"
                record.invalidated_at = None
            session.commit()

    def _finalize_input(
        self,
        task_id: str,
        index_version_id: str,
        embedding_config_id: str,
        input_id: str,
        chunk_data: list[tuple[str, str, str]],
        reserved: list[tuple[str, str, str, str, str, str | None]],
        resolved: dict[str, tuple[FloatVector, str]],
    ) -> tuple[str, int, str | None]:
        if self._stop_event.is_set():
            return "CANCELLED", 0, None
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if task is None or item is None or version is None:
                if task is not None and self._owns_task(task):
                    self._finish_task(session, task, "FAILED", "INDEX_INPUT_REMOVED")
                self._delete_version_records(
                    embedding_config_id,
                    index_version_id,
                    [row[4] for row in reserved],
                )
                return "FAILED", 0, "INDEX_INPUT_NOT_FOUND"
            if task.status == "CANCELLED":
                self._mark_cancelled(session, version)
                self._delete_version_records(
                    embedding_config_id,
                    index_version_id,
                    [row[4] for row in reserved],
                )
                return "CANCELLED", 0, None
            if not self._owns_task(task):
                return "CANCELLED", 0, None
            valid, reason = self._validate_input(session, item, version)
            if not valid:
                outcome = self._stale_outcome(reason)
                item.embedding_status = outcome
                item.embedding_reason_code = reason
                item.embedding_count = 0
                item.embedded_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, outcome, 0)
                session.commit()
                self._delete_version_records(
                    version.embedding_config_id,
                    index_version_id,
                    [row[4] for row in reserved],
                )
                return outcome, 0, reason

        for row in reserved:
            vector_id = row[4]
            actual = self._vector_store.get(
                embedding_config_id=embedding_config_id,
                index_version_id=index_version_id,
                vector_store_record_id=vector_id,
            )
            if actual is None or actual[1] != row[0]:
                raise WorkerFailure("VECTOR_STORE_INCONSISTENT")
            expected = row[5]
            if expected is not None and actual[2] != expected:
                raise WorkerFailure("VECTOR_HASH_MISMATCH")
            resolved[row[3]] = (actual[0], actual[2])

        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if task is None or item is None or version is None:
                if task is not None and self._owns_task(task):
                    self._finish_task(session, task, "FAILED", "INDEX_INPUT_REMOVED")
                self._delete_version_records(
                    embedding_config_id,
                    index_version_id,
                    [row[4] for row in reserved],
                )
                return "FAILED", 0, "INDEX_INPUT_NOT_FOUND"
            if task.status == "CANCELLED":
                self._mark_cancelled(session, version)
                self._delete_version_records(
                    embedding_config_id,
                    index_version_id,
                    [row[4] for row in reserved],
                )
                return "CANCELLED", 0, None
            if not self._owns_task(task):
                return "CANCELLED", 0, None
            valid, reason = self._validate_input(session, item, version)
            if not valid:
                outcome = self._stale_outcome(reason)
                item.embedding_status = outcome
                item.embedding_reason_code = reason
                item.embedding_count = 0
                item.embedded_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, outcome, 0)
                session.commit()
                self._delete_version_records(
                    embedding_config_id,
                    index_version_id,
                    [row[4] for row in reserved],
                )
                return outcome, 0, reason
            chunk_ids = {chunk_id for chunk_id, _content, _hash in chunk_data}
            for record_id, (_vector, vector_hash) in resolved.items():
                record = session.get(EmbeddingRecord, record_id)
                if record is None or record.chunk_id not in chunk_ids:
                    raise WorkerFailure("EMBEDDING_RECORD_REMOVED")
                if record.vector_hash is not None and record.vector_hash != vector_hash:
                    raise WorkerFailure("EMBEDDING_VECTOR_HASH_CONFLICT")
                record.vector_hash = vector_hash
                record.status = "READY"
                record.invalidated_at = None
            item.embedding_status = "EMBEDDED"
            item.embedding_reason_code = None
            item.embedding_count = len(reserved)
            item.embedded_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, "EMBEDDED", len(reserved))
            session.commit()
        return "EMBEDDED", len(reserved), None

    def _validate_input(
        self, session: Session, item: IndexVersionInput, version: IndexVersion
    ) -> tuple[bool, str | None]:
        if item.status != "PREPARED" or item.chunk_status != "CHUNKED":
            return False, "CHUNKS_NOT_AVAILABLE"
        membership = session.get(KnowledgeBaseFile, item.knowledge_base_file_id)
        if membership is None or membership.membership_status != "ACTIVE":
            return False, "MEMBERSHIP_REMOVED"
        membership_added = membership.added_at
        snapshot_added = item.membership_added_at
        if membership_added.tzinfo is None:
            membership_added = membership_added.replace(tzinfo=UTC)
        if snapshot_added.tzinfo is None:
            snapshot_added = snapshot_added.replace(tzinfo=UTC)
        if (
            membership.file_id != item.file_id
            or membership.knowledge_base_id != version.scope_id
            or membership_added != snapshot_added
        ):
            return False, "MEMBERSHIP_CHANGED"
        record = session.get(FileRecord, item.file_id)
        if record is None:
            return False, "FILE_NOT_FOUND"
        if record.deleted_at is not None:
            return False, "FILE_IN_TRASH"
        if (
            record.content_hash != item.content_hash
            or record.parse_revision_id != item.parse_revision_id
            or record.status != "PARSED"
        ):
            return False, "SOURCE_VERSION_CHANGED"
        knowledge_base = session.get(KnowledgeBase, version.scope_id)
        if knowledge_base is None or knowledge_base.deleted_at is not None:
            return False, "KNOWLEDGE_BASE_IN_TRASH"
        if version.status != "BUILDING":
            return False, "INDEX_VERSION_NOT_BUILDING"
        config = session.get(EmbeddingConfig, version.embedding_config_id)
        if config is None or not validate_embedding_config(config):
            return False, "EMBEDDING_CONFIG_UNVERIFIED"
        return True, None

    def _can_continue(self, task_id: str) -> bool:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            return bool(task is not None and self._owns_task(task))

    def _publish_state(
        self, task_id: str, version_id: str, input_id: str
    ) -> tuple[str, str | None]:
        if self._stop_event.is_set():
            return "CANCELLED", None
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, version_id)
            if task is None or item is None or version is None:
                return "STALE", "INDEX_INPUT_NOT_FOUND"
            if task.status == "CANCELLED" or not self._owns_task(task):
                return "CANCELLED", None
            valid, reason = self._validate_input(session, item, version)
            return ("READY", None) if valid else ("STALE", reason)

    def _delete_version_records(
        self, embedding_config_id: str, index_version_id: str, record_ids: list[str]
    ) -> None:
        for record_id in record_ids:
            self._vector_store.delete(
                embedding_config_id=embedding_config_id,
                index_version_id=index_version_id,
                vector_store_record_id=record_id,
            )

    def _owns_task(self, task: BackgroundTask) -> bool:
        return (
            task.task_type == INDEX_EMBED_TASK
            and task.status == "RUNNING"
            and task.lease_owner == self.worker_id
        )

    def _load_runtime(self) -> EmbeddingRuntime:
        if self._runtime is not None:
            return self._runtime
        if self._runtime_factory is not None:
            self._runtime = self._runtime_factory()
            return self._runtime
        try:
            paths = self._model_manager.ensure_installed(allow_download=False)
        except ModelManagerError as error:
            raise WorkerFailure(error.code, model_failure=True) from None
        try:
            from mindmate.ai.embeddings.adapter import OnnxEmbeddingAdapter

            self._runtime = cast(EmbeddingRuntime, OnnxEmbeddingAdapter(paths))
        except Exception as error:
            code = getattr(error, "code", "EMBEDDING_RUNTIME_LOAD_FAILED")
            raise WorkerFailure(str(code), model_failure=True) from None
        return self._runtime

    def _record_input_result(
        self,
        task_id: str,
        index_version_id: str,
        input_id: str,
        status: str,
        reason: str | None,
        count: int,
    ) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            if task is None or item is None or task.status != "RUNNING":
                return
            if task.lease_owner != self.worker_id:
                return
            item.embedding_status = status
            item.embedding_reason_code = reason
            item.embedding_count = count
            item.embedded_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, status, count)
            session.commit()
            if not renew_task_lease(
                session,
                task_id,
                self.worker_id,
                self._settings.index_embedding_worker_lease_seconds,
            ):
                session.rollback()
                return
            session.commit()

    def _checkpoint_item(
        self,
        session: Session,
        task: BackgroundTask,
        item: IndexVersionInput,
        status: str,
        count: int,
    ) -> None:
        checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
        results = [
            result
            for result in checkpoint.get("results", [])
            if result.get("file_id") != item.file_id
        ]
        results.append(
            {
                "file_id": item.file_id,
                "status": status,
                "reason": item.embedding_reason_code,
                "embedding_count": count,
            }
        )
        total = session.scalar(
            select(func.count())
            .select_from(IndexVersionInput)
            .where(IndexVersionInput.index_version_id == item.index_version_id)
        ) or 0
        completed = session.scalar(
            select(func.count())
            .select_from(IndexVersionInput)
            .where(
                IndexVersionInput.index_version_id == item.index_version_id,
                IndexVersionInput.embedding_status.in_(
                    ["EMBEDDED", "SKIPPED", "FAILED"]
                ),
            )
        ) or 0
        checkpoint_task(
            session,
            task,
            "EMBEDDING",
            {
                **checkpoint,
                "next_ordinal": item.ordinal + 1,
                "results": sorted(results, key=lambda result: str(result.get("file_id"))),
            },
            progress=round(int(completed) * 100 / max(1, int(total))),
        )

    def _complete(
        self, session: Session, task: BackgroundTask, version: IndexVersion
    ) -> None:
        rows = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version.index_version_id
                )
            )
        )
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.embedding_status] = counts.get(row.embedding_status, 0) + 1
        embedded = counts.get("EMBEDDED", 0)
        failed = counts.get("FAILED", 0)
        skipped = counts.get("SKIPPED", 0)
        version.embedding_status = (
            "COMPLETED" if failed == 0 and skipped == 0 else "PARTIAL" if embedded else "FAILED"
        )
        version.status = "BUILDING"
        version.activated_at = None
        summary = {
            "embedded": embedded,
            "failed": failed,
            "skipped": skipped,
            "vectors": sum(row.embedding_count for row in rows),
            "retryable": failed > 0,
            "error_code": None,
            "index_status": version.status,
            "embedding_status": version.embedding_status,
            "index_ready": False,
            "available_for_retrieval": False,
        }
        task.checkpoint_json = {**(task.checkpoint_json or {}), "summary": summary}
        self._finish_task(session, task, "COMPLETED", None)

    def _fail_all_pending(self, task_id: str, version_id: str, code: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            version = session.get(IndexVersion, version_id)
            if task is None or version is None or not self._owns_task(task):
                return
            rows = list(
                session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == version_id,
                        IndexVersionInput.status == "PREPARED",
                        IndexVersionInput.chunk_status == "CHUNKED",
                        IndexVersionInput.embedding_status.in_(
                            ["PENDING", "RUNNING"]
                        ),
                    )
                )
            )
            for item in rows:
                item.embedding_status = "FAILED"
                item.embedding_reason_code = code
                item.embedding_count = 0
                item.embedded_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, "FAILED", 0)
            version.embedding_status = "FAILED"
            task.checkpoint_json = {
                **(task.checkpoint_json or {}),
                "summary": {
                    "failed": len(rows),
                    "retryable": True,
                    "error_code": code,
                    "index_ready": False,
                    "available_for_retrieval": False,
                },
            }
            self._finish_task(session, task, "FAILED", code)

    def _mark_cancelled(self, session: Session, version: IndexVersion) -> None:
        version.embedding_status = "CANCELLED"
        session.commit()

    def _mark_cancelled_by_id(self, task_id: str, version_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            version = session.get(IndexVersion, version_id)
            if task is not None and task.status == "CANCELLED" and version is not None:
                version.embedding_status = "CANCELLED"
                session.commit()

    def _lease_heartbeat(self, task_id: str, stop_event: threading.Event) -> None:
        interval = max(
            0.05,
            min(1.0, self._settings.index_embedding_worker_lease_seconds / 3),
        )
        while not stop_event.wait(interval) and not self._stop_event.is_set():
            with self._session_factory() as session:
                if not renew_task_lease(
                    session,
                    task_id,
                    self.worker_id,
                    self._settings.index_embedding_worker_lease_seconds,
                ):
                    session.rollback()
                    return
                session.commit()

    def _finish_task(
        self,
        session: Session,
        task: BackgroundTask,
        status: str,
        error: str | None,
    ) -> None:
        task.status = status
        task.phase = "EMBEDDING_COMPLETED" if status == "COMPLETED" else "EMBEDDING_FAILED"
        task.progress = 100
        task.error_summary = error
        completed_at = datetime.now(UTC)
        task.completed_at = completed_at
        task.updated_at = completed_at
        task.lease_owner = None
        task.lease_until = None
        task.row_version += 1
        finish_attempt(
            session,
            task.task_id,
            "SUCCEEDED" if status == "COMPLETED" else "FAILED",
            error,
        )
        add_event(session, task, status, (task.checkpoint_json or {}).get("summary"))
        session.commit()

    def _fail(self, task_id: str, code: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or not self._owns_task(task):
                return
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            version_id = checkpoint.get("index_version_id")
            version = (
                session.get(IndexVersion, version_id)
                if isinstance(version_id, str)
                else None
            )
            if version is not None:
                version.embedding_status = "FAILED"
            self._finish_task(session, task, "FAILED", code)

    @staticmethod
    def _stale_outcome(reason: str | None) -> str:
        return (
            "SKIPPED"
            if reason
            in {
                "MEMBERSHIP_REMOVED",
                "MEMBERSHIP_CHANGED",
                "FILE_IN_TRASH",
                "SOURCE_VERSION_CHANGED",
                "KNOWLEDGE_BASE_IN_TRASH",
                "CHUNKS_NOT_AVAILABLE",
            }
            else "FAILED"
        )
