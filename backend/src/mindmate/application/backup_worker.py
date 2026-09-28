"""Durable single-concurrency worker for local backup creation."""

from __future__ import annotations

import errno
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session
from uuid6 import uuid7

from mindmate.application.backups import (
    _archive_relative_name,
    _persist_entries,
    resolve_archive_path,
)
from mindmate.application.local_backup import (
    BackupBuildError,
    backup_manifest_sha256,
    create_backup_archive,
    verify_backup_archive,
)
from mindmate.application.tasks import (
    add_event,
    claim_next_serial_task,
    finish_attempt,
    renew_task_lease,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask, Backup

logger = logging.getLogger(__name__)
BACKUP_CREATE_TASK = "BACKUP_CREATE"
_CLAIMABLE = {"QUEUED", "INTERRUPTED"}


def _now() -> datetime:
    return datetime.now(UTC)


class BackupCreationWorker:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
        poll_seconds: float = 0.1,
        lease_seconds: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"backup-{uuid7()}"
        self._poll_seconds = max(0.02, poll_seconds)
        self._lease_seconds = max(1, lease_seconds)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._start_lock:
            if self.is_running:
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-backup-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join()

    def notify(self) -> None:
        self._wake.set()

    def run_once(self) -> bool:
        task_id = self._claim_one()
        if task_id is None:
            return False
        self._process_task(task_id)
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                did_work = self.run_once()
            except Exception:
                logger.exception("backup worker cycle failed")
                did_work = False
            if not did_work:
                self._wake.wait(self._poll_seconds)
                self._wake.clear()

    def _claim_one(self) -> str | None:
        current = _now()
        claimable = or_(
            BackgroundTask.status.in_(_CLAIMABLE),
            and_(
                BackgroundTask.status == "RUNNING",
                or_(
                    BackgroundTask.lease_until.is_(None),
                    BackgroundTask.lease_until <= current,
                ),
            ),
        )
        with self._session_factory() as session:
            active_id = session.scalar(
                select(BackgroundTask.task_id)
                .where(
                    BackgroundTask.task_type == BACKUP_CREATE_TASK,
                    BackgroundTask.status == "RUNNING",
                    BackgroundTask.lease_until > current,
                )
                .limit(1)
            )
            if active_id is not None:
                return None
            candidate = session.scalar(
                select(BackgroundTask.task_id)
                .where(BackgroundTask.task_type == BACKUP_CREATE_TASK, claimable)
                .order_by(BackgroundTask.created_at, BackgroundTask.task_id)
                .limit(1)
            )
            if candidate is None:
                return None

            task = session.get(BackgroundTask, candidate)
            if task is not None and task.status == "RUNNING":
                finish_attempt(session, candidate, "INTERRUPTED", "Worker lease expired.")
            claimed = claim_next_serial_task(
                session,
                BACKUP_CREATE_TASK,
                self.worker_id,
                self._lease_seconds,
            )
            if claimed is None:
                return None

            checkpoint = claimed.checkpoint_json or {}
            backup_id = checkpoint.get("backup_id") if isinstance(checkpoint, dict) else None
            backup = session.get(Backup, backup_id) if isinstance(backup_id, str) else None
            if backup is None:
                claimed.status = "FAILED"
                claimed.phase = "FAILED"
                claimed.error_summary = "备份记录不存在，任务已停止。"
                claimed.completed_at = _now()
                claimed.lease_owner = None
                claimed.lease_until = None
                finish_attempt(session, claimed.task_id, "FAILED", claimed.error_summary)
                add_event(session, claimed, "FAILED", {"error_id": "BACKUP_RECORD_MISSING"})
                session.commit()
                return None

            conflicting_path = session.scalar(
                select(Backup.backup_id)
                .where(
                    Backup.archive_relative_path == backup.archive_relative_path,
                    Backup.backup_id != backup.backup_id,
                )
                .limit(1)
            )
            if conflicting_path is not None:
                backup.archive_relative_path = _archive_relative_name(
                    backup.backup_id,
                    backup.created_at,
                )
            backup.status = "RUNNING"
            backup.completed_at = None
            backup.error_summary = None
            claimed.phase = "BUILDING"
            claimed.checkpoint_json = {**checkpoint, "phase": "building"}
            claimed.updated_at = _now()
            session.commit()
            return claimed.task_id

    def _process_task(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            checkpoint = task.checkpoint_json or {}
            backup_id = checkpoint.get("backup_id") if isinstance(checkpoint, dict) else None
            if not isinstance(backup_id, str):
                return
            backup = session.get(Backup, backup_id)
            if backup is None:
                return
            destination = resolve_archive_path(self._settings, backup)
            schema_version = backup.schema_version

        lease_lost = threading.Event()
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat,
            args=(task_id, heartbeat_stop, lease_lost),
            name="mindmate-backup-lease",
            daemon=True,
        )
        heartbeat.start()
        try:
            with _target_lock(destination, lease_lost) as acquired:
                if not acquired or lease_lost.is_set():
                    return
                self._remove_partial_files(destination.parent)
                manifest = self._verified_existing_archive(
                    destination,
                    schema_version,
                    backup_id=backup_id,
                    task_id=task_id,
                )
                if manifest is None:
                    destination.unlink(missing_ok=True)
                    manifest = create_backup_archive(
                        self._settings.resolved_data_dir,
                        destination,
                        schema_version,
                        cancel_event=lease_lost,
                    )
                if lease_lost.is_set():
                    return
                manifest["manifest_sha256"] = backup_manifest_sha256(destination)
                self._complete(task_id, backup_id, manifest)
        except BackupBuildError as exc:
            if not lease_lost.is_set():
                self._fail(task_id, backup_id, exc.detail[:500])
        except Exception:  # noqa: BLE001 — sanitize user-facing state
            if not lease_lost.is_set():
                self._fail(task_id, backup_id, "备份创建失败，请稍后重试。")
        finally:
            heartbeat_stop.set()
            heartbeat.join()

    def _verified_existing_archive(
        self,
        destination: Path,
        schema_version: str,
        *,
        backup_id: str,
        task_id: str,
    ) -> dict | None:
        if not destination.is_file():
            return None
        try:
            with self._session_factory() as session:
                backup = session.get(Backup, backup_id)
                relative_path = backup.archive_relative_path if backup else None
            return verify_backup_archive(
                destination,
                expect_schema=schema_version,
                expected_backup_id=backup_id,
                expected_task_id=task_id,
                expected_archive_relative_path=relative_path,
            )
        except BackupBuildError:
            destination.unlink(missing_ok=True)
            return None

    def _remove_partial_files(self, directory: Path) -> None:
        for partial in directory.glob("mindmate-backup-*.partial"):
            try:
                partial.unlink(missing_ok=True)
            except OSError as exc:
                raise BackupBuildError("BACKUP_TEMP_CLEANUP_FAILED", "备份临时文件无法清理。") from exc

    def _heartbeat(
        self,
        task_id: str,
        stop: threading.Event,
        lease_lost: threading.Event,
    ) -> None:
        interval = max(0.1, self._lease_seconds / 3)
        while not stop.wait(interval):
            try:
                with self._session_factory() as session:
                    renewed = renew_task_lease(
                        session,
                        task_id,
                        self.worker_id,
                        self._lease_seconds,
                    )
                    if not renewed:
                        session.rollback()
                        lease_lost.set()
                        return
                    session.commit()
            except Exception:
                logger.warning("backup worker lease renewal failed")

    def _complete(self, task_id: str, backup_id: str, manifest: dict) -> bool:
        current = _now()
        with self._session_factory() as session:
            result = session.execute(
                update(BackgroundTask)
                .where(
                    BackgroundTask.task_id == task_id,
                    BackgroundTask.status == "RUNNING",
                    BackgroundTask.lease_owner == self.worker_id,
                    BackgroundTask.lease_until > current,
                )
                .values(
                    status="COMPLETED",
                    phase="COMPLETED",
                    progress=100,
                    error_summary=None,
                    completed_at=current,
                    updated_at=current,
                    lease_owner=None,
                    lease_until=None,
                    checkpoint_json={"backup_id": backup_id, "phase": "completed"},
                    row_version=BackgroundTask.row_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                return False
            task = session.get(BackgroundTask, task_id)
            backup = session.get(Backup, backup_id)
            if task is None or backup is None:
                session.rollback()
                return False
            backup.status = "COMPLETED"
            backup.file_count = int(manifest.get("file_count") or 0)
            backup.total_size = int(manifest.get("total_size") or 0)
            backup.manifest_sha256 = str(manifest.get("manifest_sha256") or ("0" * 64))
            backup.includes_vectors = bool(manifest.get("includes_vectors"))
            backup.includes_parsed = bool(manifest.get("includes_parsed"))
            backup.schema_version = str(manifest.get("schema_version") or backup.schema_version)
            backup.completed_at = current
            backup.error_summary = None
            _persist_entries(session, backup_id, manifest)
            finish_attempt(session, task_id, "COMPLETED")
            add_event(session, task, "COMPLETED")
            session.commit()
            return True

    def _fail(self, task_id: str, backup_id: str, error: str) -> bool:
        current = _now()
        with self._session_factory() as session:
            result = session.execute(
                update(BackgroundTask)
                .where(
                    BackgroundTask.task_id == task_id,
                    BackgroundTask.status == "RUNNING",
                    BackgroundTask.lease_owner == self.worker_id,
                    BackgroundTask.lease_until > current,
                )
                .values(
                    status="FAILED",
                    phase="FAILED",
                    error_summary=error,
                    completed_at=current,
                    updated_at=current,
                    lease_owner=None,
                    lease_until=None,
                    checkpoint_json={"backup_id": backup_id, "phase": "failed"},
                    row_version=BackgroundTask.row_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                return False
            task = session.get(BackgroundTask, task_id)
            backup = session.get(Backup, backup_id)
            if task is None or backup is None:
                session.rollback()
                return False
            backup.status = "FAILED"
            backup.completed_at = current
            backup.error_summary = error
            finish_attempt(session, task_id, "FAILED", error)
            add_event(session, task, "FAILED", {"error_id": "BACKUP_CREATE_FAILED"})
            session.commit()
            return True


@contextmanager
def _target_lock(destination: Path, lease_lost: threading.Event) -> Iterator[bool]:
    lock_path = destination.with_name(destination.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b", buffering=0)
    acquired = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
        while not lease_lost.is_set():
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as exc:
                contention = exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
                contention = contention or getattr(exc, "winerror", None) in {33, 36}
                if not contention:
                    raise
                time.sleep(0.05)
        yield acquired
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


__all__ = ["BACKUP_CREATE_TASK", "BackupCreationWorker"]
