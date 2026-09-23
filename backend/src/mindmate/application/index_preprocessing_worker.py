from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.application.files import read_parsed_text
from mindmate.application.index_preprocessing import (
    INDEX_PREPROCESS_TASK,
    fingerprint,
    get_or_create_default_configs,
)
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
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class IndexPreprocessingWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"index-preprocess-{uuid7()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-index-preprocessing-worker",
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
                    self._stop_event.wait(max(0.02, self._settings.index_worker_poll_seconds))
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
                self._settings.index_worker_lease_seconds,
                {INDEX_PREPROCESS_TASK},
            )
            if task is None:
                return None
            task.phase = "FREEZING_INPUT_SNAPSHOT"
            session.commit()
            return task.task_id

    def _process(self, task_id: str) -> None:
        with self._session_factory() as session:
            current = session.get(BackgroundTask, task_id)
            current_checkpoint = current.checkpoint_json if current is not None else {}
            current_version_id = (
                current_checkpoint.get("index_version_id")
                if isinstance(current_checkpoint, dict)
                else None
            )
            if current is not None and current.status == "CANCELLED":
                version = (
                    session.get(IndexVersion, current_version_id)
                    if isinstance(current_version_id, str)
                    else None
                )
                if version is not None and version.preprocessing_status == "RUNNING":
                    version.preprocessing_status = "CANCELLED"
                    version.preprocessed_at = datetime.now(UTC)
                    session.commit()
                return
        index_version_id = self._ensure_snapshot(task_id)
        if index_version_id is None:
            return
        while not self._stop_event.is_set():
            with self._session_factory() as session:
                task = session.get(BackgroundTask, task_id)
                if task is None:
                    return
                if task.status == "CANCELLED":
                    version = session.get(IndexVersion, index_version_id)
                    if version is not None and version.preprocessing_status == "RUNNING":
                        version.preprocessing_status = "CANCELLED"
                        version.preprocessed_at = datetime.now(UTC)
                        session.commit()
                    return
                if task.status != "RUNNING" or task.lease_owner != self.worker_id:
                    return
                item = session.scalar(
                    select(IndexVersionInput)
                    .where(
                        IndexVersionInput.index_version_id == index_version_id,
                        IndexVersionInput.status == "PENDING",
                    )
                    .order_by(IndexVersionInput.ordinal)
                    .limit(1)
                )
                if item is None:
                    self._complete(session, task, index_version_id)
                    return
                result = self._evaluate_input(session, item)
                item.status = result[0]
                item.reason_code = result[1]
                item.prepared_at = datetime.now(UTC)
                results = list((task.checkpoint_json or {}).get("results", []))
                results.append(
                    {
                        "file_id": item.file_id,
                        "status": item.status,
                        "reason": item.reason_code,
                    }
                )
                total = session.scalar(
                    select(func.count())
                    .select_from(IndexVersionInput)
                    .where(IndexVersionInput.index_version_id == index_version_id)
                ) or 0
                checkpoint = {
                    **(task.checkpoint_json or {}),
                    "index_version_id": index_version_id,
                    "next_ordinal": item.ordinal + 1,
                    "results": results,
                }
                checkpoint_task(
                    session,
                    task,
                    "VALIDATING_INPUT_SNAPSHOT",
                    checkpoint,
                    progress=round((item.ordinal + 1) * 100 / max(1, total)),
                )
                session.commit()
                if not renew_task_lease(
                    session,
                    task_id,
                    self.worker_id,
                    self._settings.index_worker_lease_seconds,
                ):
                    session.rollback()
                    self._mark_cancelled_version(task_id, index_version_id)
                    return
                session.commit()

    def _ensure_snapshot(self, task_id: str) -> str | None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return None
            checkpoint = dict(task.checkpoint_json or {})
            existing_id = checkpoint.get("index_version_id")
            if isinstance(existing_id, str) and session.get(IndexVersion, existing_id) is not None:
                return existing_id
            knowledge_base_id = checkpoint.get("knowledge_base_id")
            knowledge_base = (
                session.get(KnowledgeBase, knowledge_base_id)
                if isinstance(knowledge_base_id, str)
                else None
            )
            if knowledge_base is None or knowledge_base.deleted_at is not None:
                self._finish_task(session, task, "FAILED", "目标知识库已不存在或位于回收站。")
                return None

            chunking, embedding = get_or_create_default_configs(session)
            rows = session.execute(
                select(KnowledgeBaseFile, FileRecord)
                .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
                .where(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.membership_status == "ACTIVE",
                )
                .order_by(KnowledgeBaseFile.knowledge_base_file_id)
            ).all()
            snapshot_values = [
                {
                    "membership_id": membership.knowledge_base_file_id,
                    "file_id": record.file_id,
                    "content_hash": record.content_hash,
                    "parse_revision_id": record.parse_revision_id,
                    "membership_added_at": _as_utc(membership.added_at).isoformat(),
                }
                for membership, record in rows
            ]
            snapshot_hash = fingerprint({"inputs": snapshot_values})
            version = IndexVersion(
                index_version_id=new_id(),
                scope_type="KNOWLEDGE_BASE",
                scope_id=knowledge_base_id,
                parse_revision_set_hash=snapshot_hash,
                chunking_config_id=chunking.chunking_config_id,
                embedding_config_id=embedding.embedding_config_id,
                vector_engine="sqlite-vec",
                vector_engine_version="UNBUILT",
                status="BUILDING",
                preprocessing_status="RUNNING",
                input_count=len(rows),
                prepared_count=0,
                skipped_count=0,
                failed_count=0,
                created_at=datetime.now(UTC),
            )
            session.add(version)
            session.flush()
            for ordinal, (membership, record) in enumerate(rows):
                session.add(
                    IndexVersionInput(
                        index_version_input_id=new_id(),
                        index_version_id=version.index_version_id,
                        knowledge_base_file_id=membership.knowledge_base_file_id,
                        file_id=record.file_id,
                        content_hash=record.content_hash,
                        parse_revision_id=record.parse_revision_id,
                        membership_added_at=membership.added_at,
                        ordinal=ordinal,
                        status="PENDING",
                    )
                )
            checkpoint_task(
                session,
                task,
                "INPUT_SNAPSHOT_FROZEN",
                {
                    **checkpoint,
                    "index_version_id": version.index_version_id,
                    "parse_revision_set_hash": snapshot_hash,
                    "chunking_config_fingerprint": chunking.config_fingerprint,
                    "embedding_config_fingerprint": embedding.config_fingerprint,
                    "next_ordinal": 0,
                    "results": [],
                },
                progress=0,
            )
            session.commit()
            return version.index_version_id

    def _evaluate_input(
        self, session: Session, item: IndexVersionInput
    ) -> tuple[str, str | None]:
        membership = session.get(KnowledgeBaseFile, item.knowledge_base_file_id)
        if membership is None or membership.membership_status != "ACTIVE":
            return "SKIPPED", "MEMBERSHIP_REMOVED"
        if _as_utc(membership.added_at) != _as_utc(item.membership_added_at):
            return "SKIPPED", "MEMBERSHIP_CHANGED"
        record = session.get(FileRecord, item.file_id)
        if record is None:
            return "FAILED", "FILE_NOT_FOUND"
        if record.deleted_at is not None:
            return "SKIPPED", "FILE_IN_TRASH"
        if record.content_hash != item.content_hash or record.parse_revision_id != item.parse_revision_id:
            return "SKIPPED", "SOURCE_VERSION_CHANGED"
        if record.status in {"QUEUED", "PARSING", "IMPORTED"}:
            return "SKIPPED", "PARSE_PENDING"
        if record.status == "PARSE_FAILED":
            return "FAILED", "PARSE_FAILED"
        if record.status != "PARSED" or not record.parse_revision_id:
            return "FAILED", "PARSE_REVISION_UNAVAILABLE"
        parsed = read_parsed_text(self._settings, record.file_id)
        if parsed is None or parsed.get("content_hash") != record.content_hash:
            return "FAILED", "PARSED_CONTENT_UNAVAILABLE"
        if not isinstance(parsed.get("text"), str) or not str(parsed["text"]).strip():
            return "FAILED", "PARSED_TEXT_EMPTY"
        return "PREPARED", None

    def _complete(self, session: Session, task: BackgroundTask, index_version_id: str) -> None:
        version = session.get(IndexVersion, index_version_id)
        if version is None:
            self._finish_task(session, task, "FAILED", "索引版本快照不存在。")
            return
        knowledge_base = session.get(KnowledgeBase, version.scope_id)
        prepared_inputs = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == index_version_id,
                    IndexVersionInput.status == "PREPARED",
                )
            )
        )
        for item in prepared_inputs:
            if knowledge_base is None or knowledge_base.deleted_at is not None:
                item.status = "SKIPPED"
                item.reason_code = "KNOWLEDGE_BASE_IN_TRASH"
                continue
            status, reason = self._evaluate_input(session, item)
            if status != "PREPARED":
                item.status = status
                item.reason_code = reason
        count_rows = session.execute(
            select(IndexVersionInput.status, func.count())
            .where(IndexVersionInput.index_version_id == index_version_id)
            .group_by(IndexVersionInput.status)
        ).all()
        counts: dict[str, int] = {str(status): int(count) for status, count in count_rows}
        version.prepared_count = int(counts.get("PREPARED", 0))
        version.skipped_count = int(counts.get("SKIPPED", 0))
        version.failed_count = int(counts.get("FAILED", 0))
        version.preprocessed_at = datetime.now(UTC)
        if version.failed_count or version.skipped_count:
            version.preprocessing_status = (
                "PARTIAL" if version.prepared_count else "FAILED"
            )
        else:
            version.preprocessing_status = "COMPLETED"
        # BUILDING is intentional: no chunks, embeddings, FTS, vectors, or activation exist yet.
        version.status = "BUILDING"
        checkpoint = dict(task.checkpoint_json or {})
        checkpoint["summary"] = {
            "prepared": version.prepared_count,
            "skipped": version.skipped_count,
            "failed": version.failed_count,
            "index_status": version.status,
            "preprocessing_status": version.preprocessing_status,
            "index_ready": False,
        }
        task.checkpoint_json = checkpoint
        self._finish_task(session, task, "COMPLETED", None)

    def _finish_task(
        self, session: Session, task: BackgroundTask, status: str, error: str | None
    ) -> None:
        task.status = status
        task.phase = "PREPROCESSING_COMPLETED" if status == "COMPLETED" else "PREPROCESSING_FAILED"
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

    def _mark_cancelled_version(self, task_id: str, index_version_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            version = session.get(IndexVersion, index_version_id)
            if (
                task is not None
                and task.status == "CANCELLED"
                and version is not None
                and version.preprocessing_status == "RUNNING"
            ):
                version.preprocessing_status = "CANCELLED"
                version.preprocessed_at = datetime.now(UTC)
                session.commit()

    def _fail(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            checkpoint = task.checkpoint_json or {}
            index_version_id = checkpoint.get("index_version_id")
            version = (
                session.get(IndexVersion, index_version_id)
                if isinstance(index_version_id, str)
                else None
            )
            if version is not None:
                version.preprocessing_status = "FAILED"
                version.preprocessed_at = datetime.now(UTC)
            self._finish_task(session, task, "FAILED", "索引预处理失败，可以从检查点重试。")
