from __future__ import annotations

import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.ai.embeddings.model_manager import ModelManager, ModelManagerError, ModelProgress
from mindmate.application.tasks import (
    add_event,
    claim_task,
    create_task,
    finish_attempt,
)
from mindmate.infrastructure.models import BackgroundTask

EMBEDDING_MODEL_INSTALL_TASK = "EMBEDDING_MODEL_INSTALL"
ACTIVE_INSTALL_STATES = {"QUEUED", "RUNNING", "INTERRUPTED"}
INSTALL_LEASE_SECONDS = 60
PROGRESS_PERSIST_SECONDS = 0.5

_ENQUEUE_LOCK = threading.Lock()


def active_install_task(session: Session) -> BackgroundTask | None:
    return session.scalar(
        select(BackgroundTask)
        .where(
            BackgroundTask.task_type == EMBEDDING_MODEL_INSTALL_TASK,
            BackgroundTask.status.in_(ACTIVE_INSTALL_STATES),
        )
        .order_by(BackgroundTask.created_at.desc())
        .limit(1)
    )


def enqueue_embedding_model_install(
    session: Session, idempotency_key: str, manager: ModelManager
) -> BackgroundTask:
    with _ENQUEUE_LOCK:
        key = f"embedding-model-install:{manager.manifest.fingerprint}:{idempotency_key}"
        existing = session.scalar(
            select(BackgroundTask).where(BackgroundTask.idempotency_key == key)
        )
        if existing is not None:
            return existing
        active = active_install_task(session)
        if active is not None:
            return active
        task = create_task(
            session,
            EMBEDDING_MODEL_INSTALL_TASK,
            key,
            {
                "artifact_fingerprint": manager.manifest.fingerprint,
                "model_revision": manager.manifest.model_revision,
                "phase": "QUEUED",
                "downloaded_bytes": 0,
                "total_size_bytes": manager.manifest.total_size_bytes,
            },
        )
        session.commit()
        session.refresh(task)
        return task


class EmbeddingModelInstallWorker:
    """Installs the fixed ONNX artifact through the durable BackgroundTask queue."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        model_manager: ModelManager,
        *,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._model_manager = model_manager
        self.worker_id = worker_id or f"embedding-model-install-{uuid7()}"
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._state_lock = threading.Lock()
        self._active_cancel_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._recover_running_tasks()
        self._thread = threading.Thread(
            target=self._run,
            name="mindmate-embedding-model-install-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 35.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        with self._state_lock:
            if self._active_cancel_event is not None:
                self._active_cancel_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout))

    def wake(self) -> None:
        self._wake_event.set()

    def _recover_running_tasks(self) -> None:
        with self._session_factory() as session:
            tasks = list(
                session.scalars(
                    select(BackgroundTask).where(
                        BackgroundTask.task_type == EMBEDDING_MODEL_INSTALL_TASK,
                        BackgroundTask.status == "RUNNING",
                    )
                )
            )
            for task in tasks:
                task.status = "INTERRUPTED"
                task.phase = "RECOVERING"
                task.lease_owner = None
                task.lease_until = None
                task.updated_at = datetime.now(UTC)
                task.row_version += 1
                finish_attempt(session, task.task_id, "INTERRUPTED", "Application restarted.")
                add_event(session, task, "INTERRUPTED", {"reason": "APPLICATION_RESTARTED"})
            session.commit()

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self._wake_event.clear()
                task_id = self._claim_one()
                if task_id is None:
                    self._wake_event.wait(timeout=30)
                    continue
                try:
                    self._process(task_id)
                except Exception:
                    self._finish_failure(task_id, "MODEL_INSTALL_FAILED")
        finally:
            with self._session_factory() as session:
                session.execute(
                    update(BackgroundTask)
                    .where(
                        BackgroundTask.task_type == EMBEDDING_MODEL_INSTALL_TASK,
                        BackgroundTask.status == "RUNNING",
                        BackgroundTask.lease_owner == self.worker_id,
                    )
                    .values(
                        status="INTERRUPTED",
                        phase="RECOVERING",
                        lease_owner=None,
                        lease_until=None,
                        updated_at=datetime.now(UTC),
                        row_version=BackgroundTask.row_version + 1,
                    )
                )
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            candidate_id = session.scalar(
                select(BackgroundTask.task_id)
                .where(
                    BackgroundTask.task_type == EMBEDDING_MODEL_INSTALL_TASK,
                    BackgroundTask.status.in_({"QUEUED", "INTERRUPTED"}),
                )
                .order_by(BackgroundTask.priority.desc(), BackgroundTask.created_at)
                .limit(1)
            )
            if candidate_id is None:
                return None
            task = claim_task(
                session,
                candidate_id,
                self.worker_id,
                INSTALL_LEASE_SECONDS,
            )
            if task is None:
                return None
            task.phase = "STARTING"
            task.updated_at = datetime.now(UTC)
            task.row_version += 1
            session.commit()
            return task.task_id

    def _process(self, task_id: str) -> None:
        cancel_event = threading.Event()
        with self._state_lock:
            self._active_cancel_event = cancel_event
        last_status_check = 0.0
        last_progress_save = 0.0

        def on_progress(progress: ModelProgress) -> None:
            nonlocal last_status_check, last_progress_save
            current = monotonic()
            if self._stop_event.is_set():
                cancel_event.set()
                return
            if current - last_status_check >= 0.2:
                last_status_check = current
                if not self._is_owned(task_id):
                    cancel_event.set()
                    return
            if cancel_event.is_set():
                return
            if (
                current - last_progress_save >= PROGRESS_PERSIST_SECONDS
                or progress.total_bytes_downloaded >= progress.total_size_bytes
            ):
                phase = (
                    "VERIFYING"
                    if progress.total_bytes_downloaded >= progress.total_size_bytes
                    else "DOWNLOADING"
                )
                self._save_progress(task_id, phase, progress)
                last_progress_save = current

        try:
            self._save_initial_progress(task_id)
            self._model_manager.ensure_installed(
                allow_download=True,
                cancel_event=cancel_event,
                progress_callback=on_progress,
            )
            self._mark_ready(task_id)
        except ModelManagerError as error:
            self._finish_failure(task_id, error.code)
        finally:
            with self._state_lock:
                if self._active_cancel_event is cancel_event:
                    self._active_cancel_event = None

    def _is_owned(self, task_id: str) -> bool:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            return bool(
                task is not None
                and task.status == "RUNNING"
                and task.lease_owner == self.worker_id
            )

    def _save_initial_progress(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            checkpoint = deepcopy(task.checkpoint_json or {})
            checkpoint.setdefault("downloaded_bytes", 0)
            checkpoint.setdefault("total_size_bytes", self._model_manager.manifest.total_size_bytes)
            checkpoint.setdefault("current_file", None)
            checkpoint["phase"] = "DOWNLOADING"
            checkpoint["diagnostic_id"] = task.task_id
            task.checkpoint_json = checkpoint
            task.phase = "DOWNLOADING"
            task.progress = None
            task.checkpoint_version += 1
            task.updated_at = datetime.now(UTC)
            task.lease_until = task.updated_at + timedelta(seconds=INSTALL_LEASE_SECONDS)
            task.row_version += 1
            session.commit()

    def _save_progress(self, task_id: str, phase: str, progress: ModelProgress) -> None:
        self._save_checkpoint(
            task_id,
            phase,
            {
                "downloaded_bytes": progress.total_bytes_downloaded,
                "total_size_bytes": progress.total_size_bytes,
                "current_file": progress.file_path,
                "file_downloaded_bytes": progress.file_bytes_downloaded,
                "file_size_bytes": progress.file_size_bytes,
            },
        )

    def _save_checkpoint(self, task_id: str, phase: str, values: dict[str, Any]) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if (
                task is None
                or task.status != "RUNNING"
                or task.lease_owner != self.worker_id
            ):
                return
            checkpoint = deepcopy(task.checkpoint_json or {})
            checkpoint.update(values)
            checkpoint["phase"] = phase
            checkpoint["diagnostic_id"] = task.task_id
            task.checkpoint_json = checkpoint
            task.phase = phase
            task.progress = None
            task.checkpoint_version += 1
            task.updated_at = datetime.now(UTC)
            task.lease_until = task.updated_at + timedelta(seconds=INSTALL_LEASE_SECONDS)
            task.row_version += 1
            session.commit()

    def _mark_ready(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None:
                return
            if task.status == "CANCELLED":
                finish_attempt(session, task_id, "CANCELLED")
                session.commit()
                return
            if task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            checkpoint = deepcopy(task.checkpoint_json or {})
            checkpoint.update(
                {
                    "phase": "READY",
                    "downloaded_bytes": self._model_manager.manifest.total_size_bytes,
                    "total_size_bytes": self._model_manager.manifest.total_size_bytes,
                    "current_file": None,
                    "file_downloaded_bytes": None,
                    "file_size_bytes": None,
                    "error_code": None,
                    "diagnostic_id": task.task_id,
                }
            )
            task.checkpoint_json = checkpoint
            task.status = "COMPLETED"
            task.phase = "READY"
            task.progress = 100
            task.error_summary = None
            completed_at = datetime.now(UTC)
            task.completed_at = completed_at
            task.updated_at = completed_at
            task.lease_owner = None
            task.lease_until = None
            task.checkpoint_version += 1
            task.row_version += 1
            finish_attempt(session, task_id, "SUCCEEDED")
            add_event(session, task, "COMPLETED", {"phase": "READY"})
            session.commit()

    def _finish_failure(self, task_id: str, error_code: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None:
                return
            if task.status == "CANCELLED":
                finish_attempt(session, task_id, "CANCELLED")
                session.commit()
                return
            if task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return

            interrupted = self._stop_event.is_set()
            status = "INTERRUPTED" if interrupted else "FAILED"
            phase = "RECOVERING" if interrupted else "FAILED"
            checkpoint = deepcopy(task.checkpoint_json or {})
            checkpoint.update(
                {
                    "phase": phase,
                    "error_code": None if interrupted else error_code,
                    "diagnostic_id": task.task_id,
                }
            )
            task.checkpoint_json = checkpoint
            task.status = status
            task.phase = phase
            task.error_summary = None if interrupted else error_code
            if not interrupted:
                task.completed_at = datetime.now(UTC)
            task.updated_at = datetime.now(UTC)
            task.lease_owner = None
            task.lease_until = None
            task.checkpoint_version += 1
            task.row_version += 1
            finish_attempt(session, task_id, status, None if interrupted else error_code)
            add_event(
                session,
                task,
                status,
                {"reason": "APPLICATION_STOPPING" if interrupted else error_code},
            )
            session.commit()
