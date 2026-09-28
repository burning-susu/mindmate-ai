from __future__ import annotations

import json
import logging
import os
import re
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from uuid6 import uuid7

from mindmate.config import Settings

LOGGER = logging.getLogger(__name__)
RETENTION_DAYS = 30
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_SEGMENT_BYTES = 10 * 1024 * 1024
MAINTENANCE_INTERVAL_SECONDS = 6 * 60 * 60
LOCK_TIMEOUT_SECONDS = 5.0
_LOG_NAME = re.compile(r"^mindmate-safe-(\d{8}T\d{12}Z)-(\d{4})\.jsonl$")
_THREAD_LOCK = threading.RLock()
_TASK_TYPES = frozenset(
    {
        "FILE_IMPORT",
        "FILE_REPROCESS",
        "AI_GENERATION",
        "INDEX_PREPROCESS",
        "INDEX_CHUNK",
        "INDEX_EMBED",
        "INDEX_FTS",
        "KNOWLEDGE_MEMBERSHIP_ADD",
        "EMBEDDING_MODEL_INSTALL",
        "BACKUP_CREATE",
    }
)
_TASK_STATUSES = frozenset(
    {"QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED", "PARTIAL"}
)
_EVENTS: dict[str, tuple[str, str]] = {
    "APPLICATION_STARTED": ("runtime", "INFO"),
    "APPLICATION_STOPPED": ("runtime", "INFO"),
    "APPLICATION_LIFESPAN_FAILED": ("runtime", "ERROR"),
    "LOG_RETENTION_FAILED": ("diagnostic_log_retention", "ERROR"),
}


class DiagnosticLogError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LogRetentionStatus:
    available: bool
    file_count: int
    bytes_used: int
    retention_days: int = RETENTION_DAYS
    max_bytes: int = MAX_TOTAL_BYTES
    cleanup_complete: bool = True
    error_code: str | None = None


@dataclass(frozen=True)
class LogClearResult:
    files_removed: int
    bytes_removed: int
    remaining_files: int
    remaining_bytes: int
    complete: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _is_reparse_point(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_attribute)


def _ensure_directory(path: Path) -> None:
    try:
        path.mkdir()
    except FileExistsError:
        pass
    except OSError as exc:
        raise DiagnosticLogError("LOG_DIRECTORY_UNAVAILABLE") from exc
    try:
        info = path.lstat()
    except OSError as exc:
        raise DiagnosticLogError("LOG_DIRECTORY_UNAVAILABLE") from exc
    if _is_reparse_point(info) or not stat.S_ISDIR(info.st_mode):
        raise DiagnosticLogError("LOG_DIRECTORY_UNSAFE")


def _log_directory(settings: Settings) -> Path:
    root = settings.resolved_data_dir
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise DiagnosticLogError("LOG_DIRECTORY_UNAVAILABLE") from exc
    if _is_reparse_point(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise DiagnosticLogError("LOG_DIRECTORY_UNSAFE")

    logs_dir = root / "logs"
    diagnostic_dir = logs_dir / "diagnostic-events"
    _ensure_directory(logs_dir)
    _ensure_directory(diagnostic_dir)
    return diagnostic_dir


def _safe_regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise DiagnosticLogError("LOG_STORAGE_UNAVAILABLE") from exc
    if (
        _is_reparse_point(info)
        or not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_nlink", 1) != 1
    ):
        raise DiagnosticLogError("LOG_DIRECTORY_UNSAFE")
    return info


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    lock_path = directory / ".retention.lock"
    try:
        if lock_path.exists() or lock_path.is_symlink():
            _safe_regular_file(lock_path)
        lock_file = lock_path.open("a+b")
    except (DiagnosticLogError, OSError) as exc:
        raise DiagnosticLogError("LOG_LOCK_UNAVAILABLE") from exc

    with _THREAD_LOCK:
        acquired = False
        try:
            if lock_file.seek(0, os.SEEK_END) == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while not acquired:
                try:
                    lock_file.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise DiagnosticLogError("LOG_LOCK_UNAVAILABLE") from exc
                    time.sleep(0.025)
            yield
        finally:
            if acquired:
                lock_file.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


def _owned_files(directory: Path) -> list[tuple[Path, datetime, int]]:
    files: list[tuple[Path, datetime, int]] = []
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        raise DiagnosticLogError("LOG_STORAGE_UNAVAILABLE") from exc
    for path in children:
        match = _LOG_NAME.fullmatch(path.name)
        if match is None:
            continue
        info = _safe_regular_file(path)
        try:
            created = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
        except ValueError as exc:
            raise DiagnosticLogError("LOG_DIRECTORY_UNSAFE") from exc
        files.append((path, created, info.st_size))
    return sorted(files, key=lambda item: item[0].name)


def _delete_oldest(files: list[tuple[Path, datetime, int]], index: int) -> bool:
    path = files[index][0]
    try:
        _safe_regular_file(path)
        path.unlink()
        return True
    except (DiagnosticLogError, OSError):
        return False


def _prune_unlocked(
    directory: Path,
    now: datetime,
    *,
    incoming_bytes: int = 0,
) -> tuple[list[tuple[Path, datetime, int]], bool]:
    files = _owned_files(directory)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    complete = True
    for index in range(len(files) - 1, -1, -1):
        if files[index][1] < cutoff:
            if _delete_oldest(files, index):
                files.pop(index)
            else:
                complete = False

    total_bytes = sum(item[2] for item in files)
    while files and total_bytes + incoming_bytes > MAX_TOTAL_BYTES:
        oldest_size = files[0][2]
        if not _delete_oldest(files, 0):
            complete = False
            break
        files.pop(0)
        total_bytes -= oldest_size
    return files, complete


def inspect_log_retention(settings: Settings) -> LogRetentionStatus:
    try:
        directory = _log_directory(settings)
        with _locked(directory):
            files, complete = _prune_unlocked(directory, _now())
        return LogRetentionStatus(
            available=True,
            file_count=len(files),
            bytes_used=sum(item[2] for item in files),
            cleanup_complete=complete,
            error_code=None if complete else "LOG_CLEANUP_INCOMPLETE",
        )
    except DiagnosticLogError as exc:
        return LogRetentionStatus(
            available=False,
            file_count=0,
            bytes_used=0,
            cleanup_complete=False,
            error_code=exc.code,
        )
    except OSError:
        return LogRetentionStatus(
            available=False,
            file_count=0,
            bytes_used=0,
            cleanup_complete=False,
            error_code="LOG_STORAGE_UNAVAILABLE",
        )


def clear_diagnostic_logs(settings: Settings) -> LogClearResult:
    directory = _log_directory(settings)
    with _locked(directory):
        files = _owned_files(directory)
        removed_files = 0
        removed_bytes = 0
        complete = True
        for index in range(len(files) - 1, -1, -1):
            path, _created, size = files[index]
            if _delete_oldest(files, index):
                removed_files += 1
                removed_bytes += size
            else:
                complete = False
        remaining = _owned_files(directory)
    return LogClearResult(
        files_removed=removed_files,
        bytes_removed=removed_bytes,
        remaining_files=len(remaining),
        remaining_bytes=sum(item[2] for item in remaining),
        complete=complete and not remaining,
    )


def _event_document(
    event_code: str,
    *,
    task_id: str | None,
    task_type: str | None,
    task_status: str | None,
    duration_ms: int | None,
    attempt_number: int | None,
) -> dict[str, object] | None:
    if not isinstance(event_code, str):
        return None
    event = _EVENTS.get(event_code)
    if event is None:
        return None
    if task_id is not None:
        try:
            task_id = str(UUID(task_id))
        except (ValueError, TypeError, AttributeError):
            return None
    if task_type is not None and (
        not isinstance(task_type, str) or task_type not in _TASK_TYPES
    ):
        return None
    if task_status is not None and (
        not isinstance(task_status, str) or task_status not in _TASK_STATUSES
    ):
        return None
    for value in (duration_ms, attempt_number):
        if value is not None and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value > 2**31 - 1
        ):
            return None

    module, level = event
    document: dict[str, object] = {
        "timestamp_utc": _now().isoformat().replace("+00:00", "Z"),
        "level": level,
        "module": module,
        "event_code": event_code,
    }
    if level == "ERROR":
        document["diagnostic_id"] = str(uuid7())
    for key, value in (
        ("task_id", task_id),
        ("task_type", task_type),
        ("task_status", task_status),
        ("duration_ms", duration_ms),
        ("attempt_number", attempt_number),
    ):
        if value is not None:
            document[key] = value
    return document


def _next_log_path(directory: Path, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    for sequence in range(10_000):
        path = directory / f"mindmate-safe-{stamp}-{sequence:04d}.jsonl"
        if not path.exists() and not path.is_symlink():
            return path
    raise DiagnosticLogError("LOG_STORAGE_UNAVAILABLE")


def _append_document(settings: Settings, document: dict[str, object]) -> None:
    directory = _log_directory(settings)
    now = _now()
    payload = (json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with _locked(directory):
        files, complete = _prune_unlocked(directory, now, incoming_bytes=len(payload))
        if not complete or len(payload) > MAX_TOTAL_BYTES:
            raise DiagnosticLogError("LOG_CLEANUP_INCOMPLETE")
        current_day = now.strftime("%Y%m%d")
        active = files[-1] if files and files[-1][0].name.startswith(f"mindmate-safe-{current_day}T") else None
        if active is not None and active[2] + len(payload) <= MAX_SEGMENT_BYTES:
            target = active[0]
            _safe_regular_file(target)
            with target.open("ab") as stream:
                stream.write(payload)
                stream.flush()
            return

        target = _next_log_path(directory, now)
        try:
            with target.open("xb") as stream:
                stream.write(payload)
                stream.flush()
        except FileExistsError:
            raise DiagnosticLogError("LOG_STORAGE_UNAVAILABLE") from None


def record_diagnostic_event(
    settings: Settings,
    event_code: str,
    *,
    task_id: str | None = None,
    task_type: str | None = None,
    task_status: str | None = None,
    duration_ms: int | None = None,
    attempt_number: int | None = None,
) -> bool:
    document = _event_document(
        event_code,
        task_id=task_id,
        task_type=task_type,
        task_status=task_status,
        duration_ms=duration_ms,
        attempt_number=attempt_number,
    )
    if document is None:
        return False
    try:
        _append_document(settings, document)
        return True
    except DiagnosticLogError as exc:
        LOGGER.error(exc.code)
    except OSError:
        LOGGER.error("LOG_WRITE_FAILED")
    return False


class DiagnosticLogRetentionWorker:
    def __init__(
        self,
        settings: Settings,
        *,
        interval_seconds: float = MAINTENANCE_INTERVAL_SECONDS,
    ) -> None:
        self._settings = settings
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="diagnostic-log-retention",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            status = inspect_log_retention(self._settings)
            if not status.available or not status.cleanup_complete:
                record_diagnostic_event(self._settings, "LOG_RETENTION_FAILED")


__all__ = [
    "MAX_SEGMENT_BYTES",
    "MAX_TOTAL_BYTES",
    "RETENTION_DAYS",
    "DiagnosticLogError",
    "DiagnosticLogRetentionWorker",
    "LogClearResult",
    "LogRetentionStatus",
    "clear_diagnostic_logs",
    "inspect_log_retention",
    "record_diagnostic_event",
]
