from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.application.chunking import (
    CHUNK_GENERATION_TASK,
    ChunkDraft,
    ChunkingCancelled,
    chunk_parsed_document,
    config_values,
)
from mindmate.application.files import read_parsed_text
from mindmate.application.index_preprocessing import reuse_source_version_id
from mindmate.application.tasks import (
    add_event,
    checkpoint_task,
    claim_next_task,
    finish_attempt,
    interrupt_owned_tasks,
    renew_task_lease,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    ChunkingConfig,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class IndexChunkingWorker:
    """Durable worker that turns PREPARED inputs into reusable file-level chunks."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"index-chunk-{uuid7()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-index-chunking-worker",
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
                    self._stop_event.wait(max(0.02, self._settings.index_chunk_worker_poll_seconds))
                    continue
                try:
                    self._process(task_id)
                except Exception:
                    self._fail(task_id)
        finally:
            with self._session_factory() as session:
                interrupt_owned_tasks(session, self.worker_id)
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            task = claim_next_task(
                session,
                self.worker_id,
                self._settings.index_chunk_worker_lease_seconds,
                {CHUNK_GENERATION_TASK},
            )
            if task is None:
                return None
            task.phase = "CHUNKING"
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
                if task is None:
                    return
                if version is None:
                    if task.status == "RUNNING" and task.lease_owner == self.worker_id:
                        self._finish_task(
                            session, task, "FAILED", "INDEX_VERSION_REMOVED"
                        )
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
                        IndexVersionInput.chunk_status.in_(["PENDING", "RUNNING"]),
                    )
                    .order_by(IndexVersionInput.ordinal)
                    .limit(1)
                )
                if item is None:
                    self._complete(session, task, version)
                    return
                if reuse_source_version_id(item.reason_code) is not None:
                    item_id = item.index_version_input_id
                    # A valid source cache is copied by reference to the new
                    # immutable version. If it is unavailable, fall through to
                    # the normal parser/chunker path and rebuild this file.
                    session.commit()
                    if self._reuse_item(task_id, index_version_id, item_id):
                        continue
                item.chunk_status = "RUNNING"
                item.chunk_reason_code = None
                session.commit()
                item_id = item.index_version_input_id

            # Parsing and splitting happen outside the write transaction. The item
            # is marked RUNNING so a restart can safely put it back in PENDING.
            lease_stop = threading.Event()
            lease_thread = threading.Thread(
                target=self._lease_heartbeat,
                args=(task_id, lease_stop),
                name="mindmate-index-chunk-lease",
                daemon=True,
            )
            lease_thread.start()
            checks = 0

            def cancelled() -> bool:
                nonlocal checks
                if self._stop_event.is_set():
                    return True
                checks += 1
                if checks % 8:
                    return False
                with self._session_factory() as check_session:
                    status = check_session.execute(
                        select(BackgroundTask.status, BackgroundTask.lease_owner).where(
                            BackgroundTask.task_id == task_id
                        )
                    ).one_or_none()
                    return (
                        status is None
                        or status.status != "RUNNING"
                        or status.lease_owner != self.worker_id
                    )

            try:
                outcome, drafts, reason = self._build_for_item(
                    task_id, index_version_id, item_id, cancelled
                )
            finally:
                lease_stop.set()
                lease_thread.join(timeout=1)
            if outcome == "CANCELLED":
                self._mark_cancelled_by_id(task_id, index_version_id)
                return
            if outcome != "READY":
                self._record_item_result(task_id, index_version_id, item_id, outcome, reason, 0)
                continue
            if not self._publish_item(task_id, index_version_id, item_id, drafts):
                return

    def _reuse_item(self, task_id: str, index_version_id: str, input_id: str) -> bool:
        """Mark a reusable file as chunked without reading or splitting it again."""
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if task is None or item is None or version is None or not self._task_can_continue(
                session, task_id
            ):
                return False
            source_id = reuse_source_version_id(item.reason_code)
            if source_id is None:
                return False
            source = session.get(IndexVersion, source_id)
            source_item = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == source_id,
                    IndexVersionInput.file_id == item.file_id,
                    IndexVersionInput.content_hash == item.content_hash,
                    IndexVersionInput.parse_revision_id == item.parse_revision_id,
                    IndexVersionInput.status == "PREPARED",
                    IndexVersionInput.chunk_status == "CHUNKED",
                    IndexVersionInput.embedding_status == "EMBEDDED",
                    IndexVersionInput.fts_status == "INDEXED",
                )
            )
            valid, _reason, record = self._validate_item(session, item, version)
            if (
                source is None
                or source.status not in {"READY", "RETIRED"}
                or source.chunking_config_id != version.chunking_config_id
                or source.embedding_config_id != version.embedding_config_id
                or source_item is None
                or not valid
                or record is None
            ):
                return False
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
                or len(chunks) != source_item.chunk_count
                or [chunk.sequence_number for chunk in chunks] != list(range(len(chunks)))
                or any(
                    chunk.content_hash != sha256(chunk.content.encode("utf-8")).hexdigest()
                    for chunk in chunks
                )
            ):
                return False
            item.chunk_status = "CHUNKED"
            item.chunk_reason_code = "REUSED"
            item.chunk_count = len(chunks)
            item.chunked_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, "CHUNKED", len(chunks))
            session.commit()
            return True

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
                    version.chunking_status = "CANCELLED"
                    session.commit()
                return None
            if task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return None
            if version is None or version.status != "BUILDING":
                if version is not None:
                    version.chunking_status = "FAILED"
                self._finish_task(session, task, "FAILED", "索引版本不可用于切片。")
                return None
            config = session.get(ChunkingConfig, version.chunking_config_id)
            if config is None:
                version.chunking_status = "FAILED"
                self._finish_task(session, task, "FAILED", "切片配置已变化，不能消费旧快照。")
                return None
            checkpoint_config_id = checkpoint.get("chunking_config_id")
            checkpoint_fingerprint = checkpoint.get("chunking_config_fingerprint")
            if checkpoint_config_id is not None and checkpoint_config_id != version.chunking_config_id:
                version.chunking_status = "FAILED"
                self._finish_task(session, task, "FAILED", "切片配置已变化，不能消费旧快照。")
                return None
            if checkpoint_fingerprint is not None and checkpoint_fingerprint != config.config_fingerprint:
                version.chunking_status = "FAILED"
                self._finish_task(session, task, "FAILED", "切片配置已变化，不能消费旧快照。")
                return None
            if checkpoint_config_id is None or checkpoint_fingerprint is None:
                task.checkpoint_json = {
                    **checkpoint,
                    "chunking_config_id": version.chunking_config_id,
                    "chunking_config_fingerprint": config.config_fingerprint,
                }
                session.commit()
            if version.preprocessing_status not in {"COMPLETED", "PARTIAL"}:
                version.chunking_status = "FAILED"
                self._finish_task(session, task, "FAILED", "索引输入预处理尚未完成。")
                return None
            if version.chunking_status in {
                "NOT_STARTED",
                "CANCELLED",
                "FAILED",
                "PARTIAL",
            }:
                version.chunking_status = "RUNNING"
            elif version.chunking_status == "COMPLETED":
                # A retried idempotent task can safely re-read the existing sets.
                version.chunking_status = "RUNNING"
            if checkpoint.get("retry_failed") is True:
                session.execute(
                    update(IndexVersionInput)
                    .where(
                        IndexVersionInput.index_version_id == index_version_id,
                        IndexVersionInput.status == "PREPARED",
                        IndexVersionInput.chunk_status == "FAILED",
                    )
                    .values(
                        chunk_status="PENDING",
                        chunk_reason_code=None,
                        chunk_count=0,
                        chunked_at=None,
                    )
                )
            session.commit()
            return index_version_id

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
                    IndexVersionInput.chunk_status == "RUNNING",
                )
                .values(chunk_status="PENDING", chunk_reason_code=None)
            )
            session.commit()

    def _build_for_item(
        self,
        task_id: str,
        index_version_id: str,
        input_id: str,
        cancel_check: Callable[[], bool],
    ) -> tuple[str, list[ChunkDraft], str | None]:
        with self._session_factory() as session:
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if item is None or version is None:
                return "FAILED", [], "INPUT_NOT_FOUND"
            if not self._task_can_continue(session, task_id):
                return "CANCELLED", [], None
            valid, reason, record = self._validate_item(session, item, version)
            if not valid or record is None:
                return "SKIPPED" if reason in {"MEMBERSHIP_REMOVED", "FILE_IN_TRASH", "SOURCE_VERSION_CHANGED"} else "FAILED", [], reason
            parsed = read_parsed_text(self._settings, record.file_id)
            if (
                parsed is None
                or parsed.get("content_hash") != record.content_hash
                or (
                    parsed.get("parse_revision_id") is not None
                    and parsed.get("parse_revision_id") != item.parse_revision_id
                )
            ):
                return "FAILED", [], "PARSED_CONTENT_UNAVAILABLE"
            config = session.get(ChunkingConfig, version.chunking_config_id)
            if config is None:
                return "FAILED", [], "CHUNKING_CONFIG_UNAVAILABLE"
            try:
                drafts = chunk_parsed_document(
                    parsed,
                    **config_values(config),
                    cancel_check=cancel_check,
                )
            except ChunkingCancelled:
                return "CANCELLED", [], None
            except Exception:
                return "FAILED", [], "CHUNK_GENERATION_FAILED"
            if not drafts:
                return "FAILED", [], "PARSED_TEXT_EMPTY"
            return "READY", drafts, None

    def _publish_item(
        self, task_id: str, index_version_id: str, input_id: str, drafts: list[ChunkDraft]
    ) -> bool:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if task is None:
                return False
            if item is None or version is None:
                if task.status == "RUNNING" and task.lease_owner == self.worker_id:
                    self._finish_task(session, task, "FAILED", "INDEX_INPUT_REMOVED")
                return False
            if task.status == "CANCELLED":
                self._mark_cancelled(session, version)
                return False
            if (
                task.status != "RUNNING"
                or task.lease_owner != self.worker_id
                or item.status != "PREPARED"
            ):
                return False
            config = session.get(ChunkingConfig, version.chunking_config_id)
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            if (
                config is None
                or checkpoint.get("chunking_config_id") != version.chunking_config_id
                or checkpoint.get("chunking_config_fingerprint") != config.config_fingerprint
            ):
                item.chunk_status = "FAILED"
                item.chunk_reason_code = "CHUNKING_CONFIG_CHANGED"
                item.chunked_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, item.chunk_status, 0)
                session.commit()
                return True
            valid, reason, record = self._validate_item(session, item, version)
            if not valid or record is None:
                item.chunk_status = (
                    "SKIPPED"
                    if reason in {"MEMBERSHIP_REMOVED", "FILE_IN_TRASH", "SOURCE_VERSION_CHANGED"}
                    else "FAILED"
                )
                item.chunk_reason_code = reason
                item.chunked_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, item.chunk_status, 0)
                session.commit()
                return True
            parsed = read_parsed_text(self._settings, record.file_id)
            if (
                parsed is None
                or parsed.get("content_hash") != record.content_hash
                or (
                    parsed.get("parse_revision_id") is not None
                    and parsed.get("parse_revision_id") != item.parse_revision_id
                )
            ):
                item.chunk_status = "FAILED"
                item.chunk_reason_code = "PARSED_CONTENT_UNAVAILABLE"
                item.chunked_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, item.chunk_status, 0)
                session.commit()
                return True
            existing = list(
                session.scalars(
                    select(Chunk)
                    .where(
                        Chunk.file_id == record.file_id,
                        Chunk.parse_revision_id == item.parse_revision_id,
                        Chunk.chunking_config_id == version.chunking_config_id,
                        Chunk.invalidated_at.is_(None),
                    )
                    .order_by(Chunk.sequence_number)
                )
            )
            if existing and self._is_same_set(existing, drafts):
                count = len(existing)
            elif existing:
                item.chunk_status = "FAILED"
                item.chunk_reason_code = "CHUNK_VERSION_CONFLICT"
                item.chunked_at = datetime.now(UTC)
                self._checkpoint_item(session, task, item, item.chunk_status, 0)
                session.commit()
                return True
            else:
                now = datetime.now(UTC)
                try:
                    for draft in drafts:
                        session.add(
                            Chunk(
                                chunk_id=new_id(),
                                file_id=record.file_id,
                                parse_revision_id=item.parse_revision_id,
                                chunking_config_id=version.chunking_config_id,
                                sequence_number=draft.sequence_number,
                                heading_path=draft.heading_path,
                                page_start=draft.page_start,
                                page_end=draft.page_end,
                                slide_number=draft.slide_number,
                                line_start=draft.line_start,
                                line_end=draft.line_end,
                                source_kind=draft.source_kind,
                                content=draft.content,
                                content_hash=draft.content_hash,
                                length_unit=draft.length_unit,
                                length_value=draft.length_value,
                                token_count=draft.token_count,
                                created_at=now,
                            )
                        )
                    session.flush()
                    count = len(drafts)
                except IntegrityError:
                    session.rollback()
                    return self._publish_existing_after_race(
                        task_id, index_version_id, input_id, drafts
                    )
            item.chunk_status = "CHUNKED"
            item.chunk_reason_code = None
            item.chunk_count = count
            item.chunked_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, "CHUNKED", count)
            session.commit()
            if not renew_task_lease(
                session,
                task_id,
                self.worker_id,
                self._settings.index_chunk_worker_lease_seconds,
            ):
                return False
            session.commit()
            return True

    def _publish_existing_after_race(
        self,
        task_id: str,
        index_version_id: str,
        input_id: str,
        drafts: list[ChunkDraft],
    ) -> bool:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            item = session.get(IndexVersionInput, input_id)
            version = session.get(IndexVersion, index_version_id)
            if task is None:
                return False
            if item is None or version is None:
                if task.status == "RUNNING" and task.lease_owner == self.worker_id:
                    self._finish_task(session, task, "FAILED", "INDEX_INPUT_REMOVED")
                return False
            if (
                task.status != "RUNNING"
                or task.lease_owner != self.worker_id
                or item.status != "PREPARED"
            ):
                return False
            existing = list(
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
            if not self._is_same_set(existing, drafts):
                item.chunk_status = "FAILED"
                item.chunk_reason_code = "CHUNK_WRITE_RACE"
                item.chunked_at = datetime.now(UTC)
                session.commit()
                return True
            item.chunk_status = "CHUNKED"
            item.chunk_count = len(existing)
            item.chunked_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, "CHUNKED", len(existing))
            session.commit()
            return True

    def _validate_item(
        self, session: Session, item: IndexVersionInput, version: IndexVersion
    ) -> tuple[bool, str, FileRecord | None]:
        membership = session.get(KnowledgeBaseFile, item.knowledge_base_file_id)
        if (
            membership is None
            or membership.membership_status != "ACTIVE"
            or membership.knowledge_base_id != version.scope_id
        ):
            return False, "MEMBERSHIP_REMOVED", None
        if _as_utc(membership.added_at) != _as_utc(item.membership_added_at):
            return False, "MEMBERSHIP_CHANGED", None
        record = session.get(FileRecord, item.file_id)
        if record is None:
            return False, "FILE_NOT_FOUND", None
        if record.deleted_at is not None:
            return False, "FILE_IN_TRASH", None
        if record.content_hash != item.content_hash or record.parse_revision_id != item.parse_revision_id:
            return False, "SOURCE_VERSION_CHANGED", None
        if record.status != "PARSED" or not record.parse_revision_id:
            return False, "PARSE_REVISION_UNAVAILABLE", None
        knowledge_base = session.get(KnowledgeBase, version.scope_id)
        if knowledge_base is None or knowledge_base.deleted_at is not None:
            return False, "KNOWLEDGE_BASE_IN_TRASH", None
        return True, "", record

    def _task_can_continue(self, session: Session, task_id: str) -> bool:
        task = session.get(BackgroundTask, task_id)
        return bool(
            task is not None
            and task.task_type == CHUNK_GENERATION_TASK
            and task.status == "RUNNING"
            and task.lease_owner == self.worker_id
        )

    def _lease_heartbeat(self, task_id: str, stop_event: threading.Event) -> None:
        interval = max(
            0.05,
            min(1.0, self._settings.index_chunk_worker_lease_seconds / 3),
        )
        while not stop_event.wait(interval) and not self._stop_event.is_set():
            with self._session_factory() as session:
                if not renew_task_lease(
                    session,
                    task_id,
                    self.worker_id,
                    self._settings.index_chunk_worker_lease_seconds,
                ):
                    session.rollback()
                    return
                session.commit()

    @staticmethod
    def _is_complete_set(chunks: list[Chunk]) -> bool:
        return bool(chunks) and [chunk.sequence_number for chunk in chunks] == list(range(len(chunks)))

    @classmethod
    def _is_same_set(cls, chunks: list[Chunk], drafts: list[ChunkDraft]) -> bool:
        return cls._is_complete_set(chunks) and len(chunks) == len(drafts) and all(
            chunk.content_hash == draft.content_hash
            and chunk.content == draft.content
            and chunk.sequence_number == draft.sequence_number
            for chunk, draft in zip(chunks, drafts, strict=True)
        )

    def _checkpoint_item(
        self, session: Session, task: BackgroundTask, item: IndexVersionInput, status: str, count: int
    ) -> None:
        results = list((task.checkpoint_json or {}).get("results", []))
        results = [result for result in results if result.get("file_id") != item.file_id]
        results.append(
            {
                "file_id": item.file_id,
                "status": status,
                "reason": item.chunk_reason_code,
                "chunk_count": count,
            }
        )
        total = session.scalar(
            select(func.count())
            .select_from(IndexVersionInput)
            .where(
                IndexVersionInput.index_version_id == item.index_version_id,
                IndexVersionInput.status == "PREPARED",
            )
        ) or 0
        completed = session.scalar(
            select(func.count())
            .select_from(IndexVersionInput)
            .where(
                IndexVersionInput.index_version_id == item.index_version_id,
                IndexVersionInput.status == "PREPARED",
                IndexVersionInput.chunk_status.in_(["CHUNKED", "SKIPPED", "FAILED"]),
            )
        ) or 0
        checkpoint_task(
            session,
            task,
            "CHUNKING",
            {
                **(task.checkpoint_json or {}),
                "next_ordinal": item.ordinal + 1,
                "results": sorted(results, key=lambda result: str(result.get("file_id"))),
            },
            progress=round(int(completed) * 100 / max(1, int(total))),
        )

    def _record_item_result(
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
            if task is None or task.status != "RUNNING":
                return
            if item is None:
                if task.lease_owner == self.worker_id:
                    self._finish_task(session, task, "FAILED", "INDEX_INPUT_REMOVED")
                return
            item.chunk_status = status
            item.chunk_reason_code = reason
            item.chunk_count = count
            item.chunked_at = datetime.now(UTC)
            self._checkpoint_item(session, task, item, status, count)
            session.commit()
            if not renew_task_lease(
                session,
                task_id,
                self.worker_id,
                self._settings.index_chunk_worker_lease_seconds,
            ):
                return
            session.commit()

    def _complete(self, session: Session, task: BackgroundTask, version: IndexVersion) -> None:
        rows = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version.index_version_id,
                )
            )
        )
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.chunk_status] = counts.get(row.chunk_status, 0) + 1
        chunked = counts.get("CHUNKED", 0)
        failed = counts.get("FAILED", 0)
        skipped = counts.get("SKIPPED", 0)
        input_skipped = sum(1 for row in rows if row.status == "SKIPPED")
        input_failed = sum(1 for row in rows if row.status == "FAILED")
        skipped += input_skipped
        failed += input_failed
        version.chunking_status = (
            "COMPLETED" if failed == 0 and skipped == 0 else "PARTIAL" if chunked else "FAILED"
        )
        summary = {
            "chunked": chunked,
            "skipped": skipped,
            "failed": failed,
            "chunks": sum(row.chunk_count for row in rows),
            "index_status": version.status,
            "chunking_status": version.chunking_status,
            "index_ready": False,
        }
        task.checkpoint_json = {**(task.checkpoint_json or {}), "summary": summary}
        self._finish_task(session, task, "COMPLETED", None)

    def _mark_cancelled(self, session: Session, version: IndexVersion) -> None:
        version.chunking_status = "CANCELLED"
        session.commit()

    def _mark_cancelled_by_id(self, task_id: str, index_version_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            version = session.get(IndexVersion, index_version_id)
            if task is not None and task.status == "CANCELLED" and version is not None:
                self._mark_cancelled(session, version)

    def _finish_task(
        self, session: Session, task: BackgroundTask, status: str, error: str | None
    ) -> None:
        task.status = status
        task.phase = "CHUNKING_COMPLETED" if status == "COMPLETED" else "CHUNKING_FAILED"
        task.progress = 100
        task.error_summary = error
        completed_at = datetime.now(UTC)
        task.completed_at = completed_at
        task.updated_at = completed_at
        task.lease_owner = None
        task.lease_until = None
        task.row_version += 1
        finish_attempt(session, task.task_id, "SUCCEEDED" if status == "COMPLETED" else "FAILED", error)
        add_event(session, task, status, (task.checkpoint_json or {}).get("summary"))
        session.commit()

    def _fail(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            checkpoint = task.checkpoint_json or {}
            version_id = checkpoint.get("index_version_id")
            version = session.get(IndexVersion, version_id) if isinstance(version_id, str) else None
            if version is not None:
                version.chunking_status = "FAILED"
            self._finish_task(session, task, "FAILED", "Chunk 生成失败，可以从检查点重试。")
