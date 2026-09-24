from __future__ import annotations

import threading
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.application.files import read_parsed_text
from mindmate.application.index_preprocessing import (
    INDEX_PREPROCESS_TASK,
    default_chunking_payload,
    default_embedding_payload,
    fingerprint,
    get_or_create_default_configs,
    reuse_reason,
    reuse_source_version_id,
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
    ChunkingConfig,
    EmbeddingConfig,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _chunking_fingerprint(config: ChunkingConfig) -> str:
    return fingerprint(
        {
            "config_version": config.config_version,
            "algorithm_id": config.algorithm_id,
            "measurement_unit": config.measurement_unit,
            "target_size": config.target_size,
            "min_size": config.min_size,
            "max_size": config.max_size,
            "overlap_size": config.overlap_size,
            "structure_rules_hash": config.structure_rules_hash,
        }
    )


def _embedding_fingerprint(config: EmbeddingConfig) -> str:
    return fingerprint(
        {
            "config_version": config.config_version,
            "provider_type": config.provider_type,
            "model_name": config.model_name,
            "model_revision": config.model_revision,
            "vector_dimension": config.vector_dimension,
            "normalization": config.normalization,
            "distance_metric": config.distance_metric,
        }
    )


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
            active_version = (
                session.get(IndexVersion, knowledge_base.active_index_version_id)
                if knowledge_base.active_index_version_id
                else None
            )
            active_inputs = (
                list(
                    session.scalars(
                        select(IndexVersionInput).where(
                            IndexVersionInput.index_version_id
                            == active_version.index_version_id
                        )
                    )
                )
                if active_version is not None
                else []
            )
            incremental_compatible, compatibility_reason = self._reuse_compatibility(
                session, active_version, chunking, embedding
            )
            reuse_by_file: dict[str, str] = {}
            change_by_file: dict[str, str] = {}
            active_by_file = {item.file_id: item for item in active_inputs}
            for _membership, record in rows:
                active_item = active_by_file.get(record.file_id)
                exact_active = bool(
                    incremental_compatible
                    and active_item is not None
                    and active_item.content_hash == record.content_hash
                    and active_item.parse_revision_id == record.parse_revision_id
                )
                if exact_active:
                    if active_version is not None:
                        reuse_by_file[record.file_id] = active_version.index_version_id
                    change_by_file[record.file_id] = "UNCHANGED"
                    continue

                change_by_file[record.file_id] = (
                    "CHANGED" if active_item is not None else "NEW"
                )
                source_id = None
                if active_version is None or incremental_compatible:
                    source_id = self._find_reusable_source(
                        session,
                        file_id=record.file_id,
                        content_hash=record.content_hash,
                        parse_revision_id=record.parse_revision_id,
                        chunking=chunking,
                        embedding=embedding,
                        exclude_version_id=(
                            active_version.index_version_id
                            if active_version is not None
                            else None
                        ),
                    )
                if source_id is not None:
                    reuse_by_file[record.file_id] = source_id
                if record.status in {"QUEUED", "PARSING", "IMPORTED"}:
                    change_by_file[record.file_id] = "PENDING"
                elif record.status != "PARSED" or not record.parse_revision_id:
                    change_by_file[record.file_id] = "FAILED"

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
            current_file_ids = {record.file_id for _, record in rows}
            removed_count = sum(1 for item in active_inputs if item.file_id not in current_file_ids)
            mode = "INCREMENTAL" if incremental_compatible else "FULL"
            if active_version is None:
                compatibility_reason = "NO_ACTIVE_VERSION"
            plan = {
                "schema_version": 1,
                "mode": mode,
                "base_version_id": active_version.index_version_id
                if active_version is not None
                else None,
                "reason": compatibility_reason,
                "counts": {
                    "new": sum(kind == "NEW" for kind in change_by_file.values()),
                    "changed": sum(kind == "CHANGED" for kind in change_by_file.values()),
                    "unchanged": sum(kind == "UNCHANGED" for kind in change_by_file.values()),
                    "reused": len(reuse_by_file),
                    "removed": removed_count,
                    "pending": sum(kind == "PENDING" for kind in change_by_file.values()),
                    "failed": sum(kind == "FAILED" for kind in change_by_file.values()),
                },
                "items": [
                    {
                        "file_id": record.file_id,
                        "change_kind": change_by_file.get(record.file_id, "NEW"),
                        "reuse_source_version_id": reuse_by_file.get(record.file_id),
                    }
                    for _membership, record in rows
                ],
            }
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
                source_id = reuse_by_file.get(record.file_id)
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
                        reason_code=reuse_reason(source_id) if source_id else None,
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
                    "incremental_plan": plan,
                    "next_ordinal": 0,
                    "results": [],
                },
                progress=0,
            )
            session.commit()
            return version.index_version_id

    @staticmethod
    def _reuse_compatibility(
        session: Session,
        active_version: IndexVersion | None,
        chunking: ChunkingConfig,
        embedding: EmbeddingConfig,
    ) -> tuple[bool, str]:
        if active_version is None or active_version.status != "READY":
            return False, "NO_ACTIVE_VERSION"
        source_chunking = session.get(ChunkingConfig, active_version.chunking_config_id)
        source_embedding = session.get(EmbeddingConfig, active_version.embedding_config_id)
        if source_chunking is None or source_embedding is None:
            return False, "CONFIG_MISSING"
        source_chunking_fingerprint = _chunking_fingerprint(source_chunking)
        source_embedding_fingerprint = _embedding_fingerprint(source_embedding)
        target_chunking_fingerprint = fingerprint(default_chunking_payload())
        target_embedding_fingerprint = fingerprint(default_embedding_payload())
        if (
            source_chunking.config_fingerprint != chunking.config_fingerprint
            or source_embedding.config_fingerprint != embedding.config_fingerprint
            or source_chunking_fingerprint != source_chunking.config_fingerprint
            or source_embedding_fingerprint != source_embedding.config_fingerprint
            or target_chunking_fingerprint != chunking.config_fingerprint
            or target_embedding_fingerprint != embedding.config_fingerprint
        ):
            return False, "CONFIG_INCOMPATIBLE"
        if active_version.vector_engine != "sqlite-vec":
            return False, "VECTOR_ENGINE_INCOMPATIBLE"
        return True, "ACTIVE_VERSION_COMPATIBLE"

    @staticmethod
    def _find_reusable_source(
        session: Session,
        *,
        file_id: str,
        content_hash: str,
        parse_revision_id: str | None,
        chunking: ChunkingConfig,
        embedding: EmbeddingConfig,
        exclude_version_id: str | None,
    ) -> str | None:
        versions = list(
            session.scalars(
                select(IndexVersion)
                .where(
                    IndexVersion.status.in_(["READY", "RETIRED"]),
                    IndexVersion.chunking_config_id == chunking.chunking_config_id,
                    IndexVersion.embedding_config_id == embedding.embedding_config_id,
                    IndexVersion.vector_engine == "sqlite-vec",
                )
                .order_by(IndexVersion.created_at.desc(), IndexVersion.index_version_id.desc())
            )
        )
        for version in versions:
            if exclude_version_id and version.index_version_id == exclude_version_id:
                continue
            item = session.scalar(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == version.index_version_id,
                    IndexVersionInput.file_id == file_id,
                    IndexVersionInput.content_hash == content_hash,
                    IndexVersionInput.parse_revision_id == parse_revision_id,
                    IndexVersionInput.status == "PREPARED",
                    IndexVersionInput.chunk_status == "CHUNKED",
                    IndexVersionInput.embedding_status == "EMBEDDED",
                    IndexVersionInput.fts_status == "INDEXED",
                )
            )
            if item is None:
                continue
            if item.chunk_count <= 0 or item.embedding_count != item.chunk_count or item.fts_count != item.chunk_count:
                continue
            return version.index_version_id
        return None

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
        source_version_id = reuse_source_version_id(item.reason_code)
        if source_version_id is not None and not self._source_is_reusable(
            session, item, source_version_id
        ):
            # The cache changed while the snapshot was being prepared. Keep the
            # input prepared so the existing stages can recompute it safely.
            item.reason_code = None
            return "PREPARED", None
        return "PREPARED", item.reason_code if source_version_id else None

    @staticmethod
    def _source_is_reusable(
        session: Session, item: IndexVersionInput, source_version_id: str
    ) -> bool:
        source = session.get(IndexVersion, source_version_id)
        target = session.get(IndexVersion, item.index_version_id)
        if (
            source is None
            or target is None
            or source.status not in {"READY", "RETIRED"}
            or source.chunking_config_id != target.chunking_config_id
            or source.embedding_config_id != target.embedding_config_id
            or source.vector_engine != target.vector_engine
        ):
            return False
        source_chunking = session.get(ChunkingConfig, source.chunking_config_id)
        target_chunking = session.get(ChunkingConfig, target.chunking_config_id)
        source_embedding = session.get(EmbeddingConfig, source.embedding_config_id)
        target_embedding = session.get(EmbeddingConfig, target.embedding_config_id)
        if (
            source_chunking is None
            or target_chunking is None
            or source_embedding is None
            or target_embedding is None
            or source_chunking.config_fingerprint != _chunking_fingerprint(source_chunking)
            or target_chunking.config_fingerprint != _chunking_fingerprint(target_chunking)
            or source_embedding.config_fingerprint != _embedding_fingerprint(source_embedding)
            or target_embedding.config_fingerprint != _embedding_fingerprint(target_embedding)
            or source_chunking.config_fingerprint != target_chunking.config_fingerprint
            or source_embedding.config_fingerprint != target_embedding.config_fingerprint
        ):
            return False
        source_item = session.scalar(
            select(IndexVersionInput).where(
                IndexVersionInput.index_version_id == source_version_id,
                IndexVersionInput.file_id == item.file_id,
                IndexVersionInput.content_hash == item.content_hash,
                IndexVersionInput.parse_revision_id == item.parse_revision_id,
                IndexVersionInput.status == "PREPARED",
                IndexVersionInput.chunk_status == "CHUNKED",
                IndexVersionInput.embedding_status == "EMBEDDED",
                IndexVersionInput.fts_status == "INDEXED",
            )
        )
        return bool(
            source_item is not None
            and source_item.chunk_count > 0
            and source_item.embedding_count == source_item.chunk_count
            and source_item.fts_count == source_item.chunk_count
        )

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
        plan = checkpoint.get("incremental_plan")
        if isinstance(plan, dict):
            counts = dict(plan.get("counts") or {})
            counts.update(
                {
                    "prepared": version.prepared_count,
                    "skipped": version.skipped_count,
                    "failed": version.failed_count,
                    "pending": sum(
                        1
                        for item in session.scalars(
                            select(IndexVersionInput).where(
                                IndexVersionInput.index_version_id == index_version_id,
                                IndexVersionInput.reason_code == "PARSE_PENDING",
                            )
                        )
                    ),
                    "reused": sum(
                        1
                        for item in prepared_inputs
                        if reuse_source_version_id(item.reason_code) is not None
                    ),
                }
            )
            plan = {**plan, "counts": counts}
            checkpoint["incremental_plan"] = plan
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
