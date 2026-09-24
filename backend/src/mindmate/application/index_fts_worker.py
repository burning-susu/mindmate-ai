from __future__ import annotations

import threading
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.application.index_fts import INDEX_FTS_TASK, fts_summary
from mindmate.application.index_preprocessing import reuse_source_version_id
from mindmate.application.tasks import (
    add_event,
    checkpoint_task,
    claim_next_serial_task,
    finish_attempt,
    interrupt_owned_tasks,
    renew_task_lease,
)
from mindmate.config import Settings
from mindmate.infrastructure.fts5 import Fts5Error, Fts5Projection
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class IndexFtsWorker:
    """Durable per-input FTS5 projection worker for one immutable index version."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
        projection: Fts5Projection | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"index-fts-{uuid7()}"
        self._projection = projection or Fts5Projection()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run, name="mindmate-index-fts-worker", daemon=True
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
                    self._stop_event.wait(max(0.02, self._settings.index_fts_worker_poll_seconds))
                    continue
                try:
                    self._process(task_id)
                except Exception:
                    self._fail(task_id, "FTS_TASK_FAILED")
        finally:
            with self._session_factory() as session:
                interrupt_owned_tasks(session, self.worker_id)
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            task = claim_next_serial_task(
                session,
                INDEX_FTS_TASK,
                self.worker_id,
                self._settings.index_fts_worker_lease_seconds,
            )
            if task is None:
                return None
            task.phase = "FTS_INDEXING"
            session.commit()
            return task.task_id

    def _process(self, task_id: str) -> None:
        index_version_id = self._prepare_task(task_id)
        if index_version_id is None:
            return
        self._reset_running_inputs(task_id, index_version_id)
        while not self._stop_event.is_set():
            with self._session_factory() as session:
                task = session.get(BackgroundTask, task_id)
                version = session.get(IndexVersion, index_version_id)
                if task is None or version is None:
                    if task is not None and self._owns_task(task):
                        self._finish_task(session, task, "FAILED", "INDEX_VERSION_REMOVED")
                    return
                if task.status == "CANCELLED":
                    self._mark_cancelled(session, version)
                    return
                if not self._owns_task(task):
                    return
                item = session.scalar(
                    select(IndexVersionInput)
                    .where(
                        IndexVersionInput.index_version_id == index_version_id,
                        IndexVersionInput.status == "PREPARED",
                        IndexVersionInput.chunk_status == "CHUNKED",
                        IndexVersionInput.fts_status.in_(["PENDING", "RUNNING"]),
                    )
                    .order_by(IndexVersionInput.ordinal)
                    .limit(1)
                )
                if item is None:
                    self._complete(session, task, version)
                    return
                item.fts_status = "RUNNING"
                item.fts_reason_code = None
                session.commit()
                input_id = item.index_version_input_id

            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(
                target=self._lease_heartbeat,
                args=(task_id, heartbeat_stop),
                name="mindmate-index-fts-lease",
                daemon=True,
            )
            heartbeat.start()
            try:
                try:
                    outcome, reason, count = self._project_input(
                        task_id, index_version_id, input_id
                    )
                except Fts5Error as error:
                    outcome, reason, count = "FAILED", error.code, 0
                except Exception:
                    outcome, reason, count = "FAILED", "FTS_PROJECTION_FAILED", 0
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=1)

            if outcome == "CANCELLED":
                self._mark_cancelled_by_id(task_id, index_version_id)
                return
            if outcome != "INDEXED":
                self._record_result(
                    task_id, index_version_id, input_id, outcome, reason, count
                )

    def _prepare_task(self, task_id: str) -> str | None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None:
                return None
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            version_id = checkpoint.get("index_version_id")
            if not isinstance(version_id, str):
                self._finish_task(session, task, "FAILED", "FTS_SNAPSHOT_MISMATCH")
                return None
            version = session.get(IndexVersion, version_id)
            if task.status == "CANCELLED":
                if version is not None:
                    self._mark_cancelled(session, version)
                return None
            if not self._owns_task(task):
                return None
            if version is None or version.status != "BUILDING":
                self._finish_task(session, task, "FAILED", "INDEX_VERSION_NOT_BUILDING")
                return None
            if (
                checkpoint.get("schema_version") != 1
                or checkpoint.get("knowledge_base_id") != version.scope_id
                or checkpoint.get("chunking_config_id") != version.chunking_config_id
            ):
                version.fts_status = "FAILED"
                self._finish_task(session, task, "FAILED", "FTS_SNAPSHOT_MISMATCH")
                return None
            if version.chunking_status not in {"COMPLETED", "PARTIAL"}:
                version.fts_status = "FAILED"
                self._finish_task(session, task, "FAILED", "CHUNKING_NOT_COMPLETED")
                return None

            inputs = list(
                session.scalars(
                    select(IndexVersionInput)
                    .where(IndexVersionInput.index_version_id == version_id)
                    .order_by(IndexVersionInput.ordinal)
                )
            )
            rebuild = checkpoint.get("rebuild") is True
            retry_failed = checkpoint.get("retry_failed") is True
            if rebuild:
                self._projection.rebuild_version(session, version_id)
            for item in inputs:
                if item.status != "PREPARED" or item.chunk_status != "CHUNKED":
                    item.fts_status = "SKIPPED"
                    item.fts_reason_code = "CHUNKS_NOT_AVAILABLE"
                    item.fts_count = 0
                    item.fts_indexed_at = datetime.now(UTC)
                elif rebuild or item.fts_status == "RUNNING" or (
                    retry_failed and item.fts_status == "FAILED"
                ):
                    item.fts_status = "PENDING"
                    item.fts_reason_code = None
                    item.fts_count = 0
                    item.fts_indexed_at = None
            version.fts_status = "RUNNING"
            checkpoint = {**checkpoint, "next_ordinal": 0, "results": []}
            checkpoint_task(session, task, "FTS_INDEXING", checkpoint, progress=0)
            session.commit()
            return version_id

    def _reset_running_inputs(self, task_id: str, version_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or not self._owns_task(task):
                return
            for item in session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version_id,
                    IndexVersionInput.fts_status == "RUNNING",
                )
            ):
                item.fts_status = "PENDING"
                item.fts_reason_code = None
            session.commit()

    def _project_input(
        self, task_id: str, version_id: str, input_id: str
    ) -> tuple[str, str | None, int]:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, version_id)
            if task is None or item is None or version is None:
                return "FAILED", "INDEX_INPUT_NOT_FOUND", 0
            if task.status == "CANCELLED" or not self._owns_task(task):
                return "CANCELLED", None, 0
            valid, reason = self._validate_input(session, item, version)
            if not valid:
                return "SKIPPED", reason, 0
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
                or len(chunks) != item.chunk_count
                or [chunk.sequence_number for chunk in chunks] != list(range(len(chunks)))
                or any(not chunk.content.strip() for chunk in chunks)
                or any(sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.content_hash for chunk in chunks)
            ):
                return "FAILED", "CHUNK_SET_UNAVAILABLE", 0

            source_version_id = reuse_source_version_id(item.reason_code)
            copied = 0
            if source_version_id is not None:
                source = session.get(IndexVersion, source_version_id)
                if (
                    source is not None
                    and source.status in {"READY", "RETIRED"}
                    and source.chunking_config_id == version.chunking_config_id
                ):
                    copied = self._projection.copy_file(
                        session,
                        source_index_version_id=source_version_id,
                        index_version_id=version_id,
                        file_id=item.file_id,
                    )
            if copied != len(chunks):
                self._projection.replace_file(
                    session,
                    index_version_id=version_id,
                    file_id=item.file_id,
                    parse_revision_id=str(item.parse_revision_id),
                    chunking_config_id=version.chunking_config_id,
                    chunks=chunks,
                )
            if not self._owns_task(task):
                return "CANCELLED", None, 0
            item.fts_status = "INDEXED"
            item.fts_reason_code = None
            item.fts_count = len(chunks)
            item.fts_indexed_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, "INDEXED", len(chunks))
            session.commit()
            return "INDEXED", None, len(chunks)

    def _validate_input(
        self, session: Session, item: IndexVersionInput, version: IndexVersion
    ) -> tuple[bool, str | None]:
        if item.status != "PREPARED" or item.chunk_status != "CHUNKED":
            return False, "CHUNKS_NOT_AVAILABLE"
        membership = session.get(KnowledgeBaseFile, item.knowledge_base_file_id)
        if membership is None or membership.membership_status != "ACTIVE":
            return False, "MEMBERSHIP_REMOVED"
        if (
            membership.file_id != item.file_id
            or membership.knowledge_base_id != version.scope_id
            or _as_utc(membership.added_at) != _as_utc(item.membership_added_at)
        ):
            return False, "MEMBERSHIP_CHANGED"
        file_record = session.get(FileRecord, item.file_id)
        if file_record is None:
            return False, "FILE_NOT_FOUND"
        if file_record.deleted_at is not None:
            return False, "FILE_IN_TRASH"
        if (
            file_record.status != "PARSED"
            or file_record.content_hash != item.content_hash
            or file_record.parse_revision_id != item.parse_revision_id
        ):
            return False, "SOURCE_VERSION_CHANGED"
        knowledge_base = session.get(KnowledgeBase, version.scope_id)
        if knowledge_base is None or knowledge_base.deleted_at is not None:
            return False, "KNOWLEDGE_BASE_IN_TRASH"
        if version.status != "BUILDING":
            return False, "INDEX_VERSION_NOT_BUILDING"
        return True, None

    def _record_result(
        self,
        task_id: str,
        version_id: str,
        input_id: str,
        status: str,
        reason: str | None,
        count: int,
    ) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            if task is None or item is None or not self._owns_task(task):
                return
            if task.status == "CANCELLED":
                self._mark_cancelled_by_id(task_id, version_id)
                return
            item.fts_status = status
            item.fts_reason_code = reason
            item.fts_count = count
            item.fts_indexed_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, status, count)
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
                "reason": item.fts_reason_code,
                "chunk_count": count,
            }
        )
        session.flush()
        total = session.scalar(
            select(func.count()).select_from(IndexVersionInput).where(
                IndexVersionInput.index_version_id == item.index_version_id
            )
        ) or 0
        completed = session.scalar(
            select(func.count()).select_from(IndexVersionInput).where(
                IndexVersionInput.index_version_id == item.index_version_id,
                IndexVersionInput.fts_status.in_(["INDEXED", "SKIPPED", "FAILED"]),
            )
        ) or 0
        checkpoint_task(
            session,
            task,
            "FTS_INDEXING",
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
            counts[row.fts_status] = counts.get(row.fts_status, 0) + 1
        indexed = counts.get("INDEXED", 0)
        failed = counts.get("FAILED", 0)
        skipped = counts.get("SKIPPED", 0)
        status = "COMPLETED" if failed == 0 and skipped == 0 else "PARTIAL" if indexed else "FAILED"
        version.fts_status = status
        version.status = "BUILDING"
        version.activated_at = None
        summary = fts_summary(
            indexed=indexed,
            failed=failed,
            skipped=skipped,
            chunks=sum(row.fts_count for row in rows),
            status=status,
        )
        task.checkpoint_json = {**(task.checkpoint_json or {}), "summary": summary}
        self._finish_task(session, task, "COMPLETED", None)

    def _mark_cancelled(self, session: Session, version: IndexVersion) -> None:
        version.fts_status = "CANCELLED"
        session.commit()

    def _mark_cancelled_by_id(self, task_id: str, version_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            version = session.get(IndexVersion, version_id)
            if task is not None and task.status == "CANCELLED" and version is not None:
                version.fts_status = "CANCELLED"
                session.commit()

    def _lease_heartbeat(self, task_id: str, stop_event: threading.Event) -> None:
        interval = max(0.05, min(1.0, self._settings.index_fts_worker_lease_seconds / 3))
        while not stop_event.wait(interval) and not self._stop_event.is_set():
            with self._session_factory() as session:
                if not renew_task_lease(
                    session,
                    task_id,
                    self.worker_id,
                    self._settings.index_fts_worker_lease_seconds,
                ):
                    session.rollback()
                    return
                session.commit()

    def _finish_task(
        self, session: Session, task: BackgroundTask, status: str, error: str | None
    ) -> None:
        task.status = status
        task.phase = "FTS_COMPLETED" if status == "COMPLETED" else "FTS_FAILED"
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
            version = session.get(IndexVersion, version_id) if isinstance(version_id, str) else None
            if version is not None:
                version.fts_status = "FAILED"
                for item in session.scalars(
                    select(IndexVersionInput).where(
                        IndexVersionInput.index_version_id == version.index_version_id,
                        IndexVersionInput.fts_status.in_(["PENDING", "RUNNING"]),
                    )
                ):
                    item.fts_status = "FAILED"
                    item.fts_reason_code = code
                    item.fts_indexed_at = datetime.now(UTC)
                    self._checkpoint_item(session, task, item, "FAILED", 0)
            self._finish_task(session, task, "FAILED", code)

    def _owns_task(self, task: BackgroundTask) -> bool:
        return (
            task.task_type == INDEX_FTS_TASK
            and task.status == "RUNNING"
            and task.lease_owner == self.worker_id
        )
