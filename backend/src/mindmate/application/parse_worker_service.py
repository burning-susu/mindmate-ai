from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import Session
from uuid6 import uuid7

from mindmate.application.files import (
    FileValidationError,
    delete_parsed_text,
    mark_parse_failed,
    mark_parse_succeeded,
    parse_document_in_subprocess,
    parse_local_text,
    resolve_storage_path,
    safe_parse_failure_message,
    terminate_active_parser_processes,
    write_parsed_text,
)
from mindmate.application.tasks import (
    add_event,
    claim_next_task,
    finish_attempt,
    interrupt_owned_tasks,
    recover_expired_tasks,
    renew_task_lease,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask, ContentObject, FileRecord

FILE_IMPORT_TASK = "FILE_IMPORT"
FILE_REPROCESS_TASK = "FILE_REPROCESS"
RETRYABLE_PARSE_ERRORS = {
    "PARSER_TIMEOUT",
    "PARSER_FAILED",
    "PARSER_OUTPUT_INVALID",
    "PARSER_RESOURCE_LIMIT",
}


def _task_items(task: BackgroundTask) -> list[dict[str, Any]]:
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    items = checkpoint.get("items", [])
    return [copy.deepcopy(item) for item in items if isinstance(item, dict)]


def _checkpoint_context(task: BackgroundTask) -> dict[str, Any]:
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    context = checkpoint.get("context", {})
    return context if isinstance(context, dict) else {}


class ParsingWorker:
    """In-process durable worker for file parsing tasks."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"parser-{uuid7()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._start_lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-parse-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        terminate_active_parser_processes()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.1, timeout))

    def _run(self) -> None:
        try:
            with self._session_factory() as session:
                recover_expired_tasks(session)
                session.commit()
            while not self._stop_event.is_set():
                task_id = self._claim_one()
                if task_id is None:
                    self._stop_event.wait(max(0.02, self._settings.parse_worker_poll_seconds))
                    continue
                try:
                    self._process_task(task_id)
                except Exception:
                    self._fail_worker_task(task_id)
        finally:
            with self._session_factory() as session:
                interrupt_owned_tasks(session, self.worker_id)
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            task = claim_next_task(
                session,
                self.worker_id,
                self._settings.parse_worker_lease_seconds,
            )
            if task is None:
                return None
            session.commit()
            return task.task_id

    def _process_task(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            task_type = task.task_type
            items = _task_items(task)
            if task_type == FILE_REPROCESS_TASK and not items:
                file_id = _checkpoint_context(task).get("file_id")
                if isinstance(file_id, str):
                    items = [
                        {
                            "item_index": 0,
                            "file_id": file_id,
                            "status": "IMPORTED",
                            "parse_status": "QUEUED",
                            "manual_retry": True,
                        }
                    ]
                    task.checkpoint_json = {
                        "context": {"file_id": file_id},
                        "items": items,
                    }
                    session.commit()

        if task_type not in {FILE_IMPORT_TASK, FILE_REPROCESS_TASK}:
            self._finish_task(task_id, "FAILED", "TASK_TYPE_UNSUPPORTED")
            return

        for item in items:
            if self._stop_event.is_set():
                return
            if item.get("duplicate_status") in {"REUSED", "SKIPPED"}:
                continue
            if item.get("status") in {"REJECTED", "BLOCKED"}:
                continue
            if item.get("parse_status") in {"PARSED", "PARSE_FAILED"}:
                continue
            file_id = item.get("file_id")
            if not isinstance(file_id, str):
                continue
            outcome = self._process_one(
                task_id,
                file_id,
                int(item.get("item_index", 0)),
                manual_retry=bool(item.get("manual_retry", False)),
            )
            if outcome == "retry":
                self._stop_event.wait(0.05)
                return
            if outcome == "cancelled":
                return

        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING":
                return
            items = _task_items(task)
            failed = any(item.get("parse_status") == "PARSE_FAILED" for item in items)
            task.status = "FAILED" if failed else "COMPLETED"
            task.phase = "PARSING" if failed else "COMPLETED"
            if not failed:
                task.error_summary = None
            task.progress = 100
            task.completed_at = task.completed_at or datetime.now(UTC)
            task.lease_owner = None
            task.lease_until = None
            task.row_version += 1
            add_event(session, task, task.status, {"file_count": len(items)})
            finish_attempt(session, task.task_id, "FAILED" if failed else "SUCCEEDED", task.error_summary)
            session.commit()

    def _process_one(
        self, task_id: str, file_id: str, item_index: int, *, manual_retry: bool
    ) -> str:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            record = session.get(FileRecord, file_id)
            if task is None or record is None or task.status != "RUNNING":
                return "cancelled"
            content = session.get(ContentObject, record.content_object_id)
            if content is None or content.storage_state != "READY" or record.deleted_at is not None:
                self._mark_version_mismatch(session, task, item_index)
                session.commit()
                return "failed"
            if manual_retry and record.parse_error_id:
                record.parse_retry_count += 1
            record.status = "PARSING"
            record.updated_at = datetime.now(UTC)
            record.row_version += 1
            self._update_item(
                task,
                item_index,
                parse_status="PARSING",
                parse_retry_count=record.parse_retry_count,
            )
            session.commit()
            source = resolve_storage_path(self._settings, content.storage_relative_path)
            content_hash = content.sha256
            document_type = record.document_type

        lease_stop = threading.Event()
        lease_thread = threading.Thread(
            target=self._lease_heartbeat,
            args=(task_id, lease_stop),
            name="mindmate-parse-lease",
            daemon=True,
        )
        lease_thread.start()
        try:
            if document_type in {"TXT", "MARKDOWN"}:
                text, metadata = parse_local_text(source)
                parsed = {"text": text, "metadata": metadata, "locations": []}
            else:
                parsed = parse_document_in_subprocess(
                    source,
                    document_type,
                    timeout_seconds=self._settings.parser_timeout_seconds,
                    memory_limit_bytes=self._settings.parser_memory_limit_bytes,
                    stop_event=self._stop_event,
                )
        except FileValidationError as exc:
            if exc.code == "PARSER_CANCELLED" and self._stop_event.is_set():
                return "cancelled"
            return self._handle_failure(
                task_id, file_id, item_index, exc, count_retry=not manual_retry
            )
        except (OSError, ValueError) as exc:
            error = FileValidationError("PARSER_FAILED", str(exc)[:200])
            return self._handle_failure(
                task_id, file_id, item_index, error, count_retry=not manual_retry
            )
        finally:
            lease_stop.set()
            lease_thread.join(timeout=1)

        if self._stop_event.is_set():
            return "cancelled"
        try:
            with self._session_factory() as session:
                task = session.get(BackgroundTask, task_id)
                record = session.get(FileRecord, file_id)
                content = session.get(ContentObject, record.content_object_id) if record else None
                if (
                    task is None
                    or record is None
                    or content is None
                    or task.status != "RUNNING"
                    or record.deleted_at is not None
                    or content.storage_state != "READY"
                    or content.sha256 != content_hash
                    or record.content_hash != content_hash
                ):
                    if task is not None:
                        self._mark_version_mismatch(session, task, item_index)
                    session.commit()
                    return "failed"
                write_parsed_text(
                    self._settings,
                    file_id,
                    content_hash,
                    str(parsed["text"]),
                    cast(dict[str, object], parsed["metadata"]),
                    parser=(
                        "local-text-v1"
                        if document_type in {"TXT", "MARKDOWN"}
                        else f"isolated-{document_type.casefold()}-v1"
                    ),
                    locations=cast(list[dict[str, object]], parsed["locations"]),
                )
                record = session.get(FileRecord, file_id)
                if record is None or record.deleted_at is not None or record.content_hash != content_hash:
                    delete_parsed_text(self._settings, file_id)
                    if task is not None:
                        self._mark_version_mismatch(session, task, item_index)
                    session.commit()
                    return "failed"
                mark_parse_succeeded(record)
                record.updated_at = datetime.now(UTC)
                record.row_version += 1
                self._update_item(
                    task,
                    item_index,
                    status="IMPORTED",
                    parse_status="PARSED",
                    parse_error=None,
                    parse_error_id=None,
                    parse_failure_stage=None,
                    parse_retry_count=record.parse_retry_count,
                )
                renew_task_lease(
                    session,
                    task_id,
                    self.worker_id,
                    self._settings.parse_worker_lease_seconds,
                )
                session.commit()
            return "succeeded"
        except (OSError, ValueError) as exc:
            error = FileValidationError("PARSER_OUTPUT_INVALID", str(exc)[:200])
            return self._handle_failure(task_id, file_id, item_index, error)

    def _handle_failure(
        self,
        task_id: str,
        file_id: str,
        item_index: int,
        error: FileValidationError,
        *,
        count_retry: bool = True,
    ) -> str:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            record = session.get(FileRecord, file_id)
            if task is None or record is None or task.status != "RUNNING":
                return "cancelled"
            safe_error = mark_parse_failed(record, error)
            retryable = error.code in RETRYABLE_PARSE_ERRORS
            retry = retryable and record.parse_retry_count < self._settings.parse_worker_max_retries
            if retry and count_retry:
                record.parse_retry_count += 1
            record.updated_at = datetime.now(UTC)
            record.row_version += 1
            self._update_item(
                task,
                item_index,
                status="IMPORTED",
                parse_status="QUEUED" if retry else "PARSE_FAILED",
                parse_error=safe_error,
                parse_error_id=error.code,
                parse_failure_stage="PARSING",
                parse_retry_count=record.parse_retry_count,
            )
            task.error_summary = safe_error
            if retry:
                task.status = "QUEUED"
                task.phase = "RETRY_WAIT"
                task.lease_owner = None
                task.lease_until = None
                task.row_version += 1
                add_event(session, task, "RETRY_SCHEDULED", {"error_id": error.code})
                finish_attempt(session, task_id, "RETRYING", safe_error)
            session.commit()
            return "retry" if retry else "failed"

    def _mark_version_mismatch(self, session: Session, task: BackgroundTask, item_index: int) -> None:
        task.error_summary = safe_parse_failure_message("FILE_VERSION_CHANGED")
        self._update_item(
            task,
            item_index,
            status="IMPORTED",
            parse_status="PARSE_FAILED",
            parse_error=safe_parse_failure_message("FILE_VERSION_CHANGED"),
            parse_error_id="FILE_VERSION_CHANGED",
            parse_failure_stage="PARSING",
        )

    def _update_item(self, task: BackgroundTask, item_index: int, **values: Any) -> None:
        items = _task_items(task)
        for item in items:
            if int(item.get("item_index", -1)) == item_index:
                item.update(values)
                break
        total = max(1, len(items))
        completed = sum(
            1
            for item in items
            if item.get("parse_status") in {"PARSED", "PARSE_FAILED"}
            or item.get("duplicate_status") in {"REUSED", "SKIPPED"}
            or item.get("status") == "REJECTED"
        )
        from mindmate.application.tasks import checkpoint_task

        checkpoint_task(
            session=self._session_for_task(task),
            task=task,
            phase="PARSING",
            checkpoint={"context": _checkpoint_context(task), "items": items},
            progress=min(99, int(completed * 100 / total)),
        )

    def _session_for_task(self, task: BackgroundTask) -> Session:
        """Return the session currently owning the ORM object.

        SQLAlchemy keeps the session in the object state; this helper is replaced
        by the worker's explicit session context in `_update_item` callers.
        """
        state = getattr(task, "_sa_instance_state", None)
        session = state.session if state is not None else None
        if session is None:
            raise RuntimeError("task session unavailable")
        return session

    def _finish_task(self, task_id: str, status: str, error: str | None = None) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None:
                return
            task.status = status
            task.error_summary = error
            task.phase = "FAILED" if status == "FAILED" else "COMPLETED"
            task.progress = 100
            task.completed_at = datetime.now(UTC)
            task.lease_owner = None
            task.lease_until = None
            task.row_version += 1
            finish_attempt(session, task_id, "FAILED", error)
            add_event(session, task, status)
            session.commit()

    def _lease_heartbeat(self, task_id: str, stop_event: threading.Event) -> None:
        interval = max(0.05, self._settings.parse_worker_lease_seconds / 3)
        while not stop_event.wait(interval):
            try:
                with self._session_factory() as session:
                    if not renew_task_lease(
                        session,
                        task_id,
                        self.worker_id,
                        self._settings.parse_worker_lease_seconds,
                    ):
                        session.rollback()
                        return
                    session.commit()
            except Exception:
                return

    def _fail_worker_task(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING":
                return
            task.status = "FAILED"
            task.phase = "PARSING"
            task.error_summary = "解析 Worker 执行失败，可以稍后重新处理。"
            task.completed_at = datetime.now(UTC)
            task.lease_owner = None
            task.lease_until = None
            task.row_version += 1
            finish_attempt(session, task_id, "FAILED", task.error_summary)
            add_event(session, task, "FAILED", {"error_id": "PARSER_WORKER_FAILED"})
            session.commit()
