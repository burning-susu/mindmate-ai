"""Local backup create/list/verify orchestration for MindMate AI."""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from uuid6 import uuid7

from mindmate.application.local_backup import (
    ARCHIVE_SUFFIX,
    FORMAT_VERSION,
    BackupBuildError,
    create_backup_archive,
    read_schema_version,
    verify_backup_archive,
)
from mindmate.application.tasks import create_task
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask, Backup, BackupEntry, new_id

_CREATE_LOCK = threading.Lock()

UNENCRYPTED_WARNING = (
    "此备份包未加密，并包含用户文件与学习历史。请保存在受保护磁盘上，不要上传到云端或共享给他人。"
)


def create_backup(source_root: Path, destination: Path, schema_version: str) -> dict[str, Any]:
    """Callable used by tests and low-level tooling. Safe inventory, not full-tree rglob."""
    return create_backup_archive(source_root, destination, schema_version)


def verify_backup(archive_path: Path) -> dict[str, Any]:
    return verify_backup_archive(archive_path)


def _idempotency_task_key(raw_key: str) -> str:
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"bc:{digest}"


def _now() -> datetime:
    return datetime.now(UTC)


def _archive_relative_name(backup_id: str, created_at: datetime) -> str:
    stamp = created_at.strftime("%Y%m%d-%H%M%S")
    short = backup_id.replace("-", "")[:8]
    return f"backups/mindmate-backup-{stamp}-{short}{ARCHIVE_SUFFIX}"


def _has_drive_prefix(relative: str) -> bool:
    return len(relative) >= 2 and relative[1] == ":"


def backup_public_view(row: Backup) -> dict[str, Any]:
    download_available = row.status == "COMPLETED" and bool(row.archive_relative_path)
    return {
        "backup_id": row.backup_id,
        "status": row.status,
        "backup_format_version": row.backup_format_version,
        "schema_version": row.schema_version,
        "file_count": row.file_count,
        "total_size": row.total_size,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
        "error_summary": row.error_summary,
        "includes_vectors": row.includes_vectors,
        "includes_parsed": row.includes_parsed,
        "includes_secrets": False,
        "encrypted": False,
        "contains_user_files_and_history": True,
        "unencrypted_warning": True,
        "warning_message": UNENCRYPTED_WARNING,
        "download_available": download_available,
        "restore_available": False,
        "scope": {
            "database_snapshot": True,
            "content_objects": True,
            "parsed_artifacts": row.includes_parsed,
            "non_secret_config": True,
            "vectors": False,
            "fts": False,
            "models": False,
            "logs": False,
            "secrets": False,
        },
    }


def list_backups(session: Session, *, limit: int = 50) -> list[Backup]:
    limit = max(1, min(limit, 100))
    return list(session.scalars(select(Backup).order_by(Backup.created_at.desc()).limit(limit)))


def get_backup(session: Session, backup_id: str) -> Backup | None:
    return session.get(Backup, backup_id)


def resolve_archive_path(settings: Settings, row: Backup) -> Path:
    root = settings.resolved_data_dir.resolve()
    relative = row.archive_relative_path.replace("\\", "/")
    if ".." in relative.split("/") or relative.startswith("/") or _has_drive_prefix(relative):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份归档路径无效。")
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份归档路径越界。")
    return path


def _persist_entries(session: Session, backup_id: str, manifest: dict[str, Any]) -> None:
    session.execute(delete(BackupEntry).where(BackupEntry.backup_id == backup_id))
    for entry in manifest.get("entries") or []:
        session.add(
            BackupEntry(
                backup_entry_id=new_id(),
                backup_id=backup_id,
                relative_path=str(entry["path"])[:500],
                entry_type=str(entry.get("entry_type") or "other")[:30],
                sha256=str(entry["sha256"]),
                byte_size=int(entry["byte_size"]),
            )
        )


def _update_backup_task(session: Session, backup_id: str, *, status: str, error: str | None) -> None:
    now = _now()
    for task_row in session.scalars(
        select(BackgroundTask).where(BackgroundTask.task_type == "BACKUP_CREATE")
    ):
        payload = task_row.checkpoint_json or {}
        if payload.get("backup_id") != backup_id:
            continue
        task_row.status = status
        task_row.updated_at = now
        task_row.completed_at = now if status in {"COMPLETED", "FAILED"} else task_row.completed_at
        task_row.progress = 100 if status == "COMPLETED" else task_row.progress
        task_row.error_summary = error
        task_row.checkpoint_json = {
            **payload,
            "phase": "completed" if status == "COMPLETED" else "failed",
        }
        break


def start_or_get_backup(
    session: Session,
    settings: Settings,
    *,
    idempotency_key: str,
) -> Backup:
    """Idempotent backup create: returns existing row for the same Idempotency-Key."""
    task_key = _idempotency_task_key(idempotency_key)
    task = create_task(session, "BACKUP_CREATE", task_key, {"phase": "init"})
    session.flush()
    existing_id = (task.checkpoint_json or {}).get("backup_id")
    if existing_id:
        existing = session.get(Backup, existing_id)
        if existing is not None:
            return existing

    created_at = _now()
    backup_id = str(uuid7())
    relative = _archive_relative_name(backup_id, created_at)
    schema_version = read_schema_version(settings.database_path)
    row = Backup(
        backup_id=backup_id,
        archive_relative_path=relative,
        status="CREATING",
        backup_format_version=FORMAT_VERSION,
        schema_version=schema_version,
        file_count=0,
        total_size=0,
        manifest_sha256="0" * 64,
        includes_vectors=False,
        includes_parsed=False,
        created_at=created_at,
        completed_at=None,
        error_summary=None,
    )
    session.add(row)
    task.checkpoint_json = {"backup_id": backup_id, "phase": "creating"}
    task.status = "RUNNING"
    task.started_at = created_at
    task.updated_at = created_at
    session.commit()

    _run_create_locked(session, settings, row.backup_id)
    session.refresh(row)
    return row


def _run_create_locked(session: Session, settings: Settings, backup_id: str) -> None:
    with _CREATE_LOCK:
        row = session.get(Backup, backup_id)
        if row is None or row.status == "COMPLETED":
            return
        destination = resolve_archive_path(settings, row)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            manifest = create_backup_archive(
                settings.resolved_data_dir,
                destination,
                row.schema_version,
            )
            row.status = "COMPLETED"
            row.file_count = int(manifest.get("file_count") or 0)
            row.total_size = int(manifest.get("total_size") or 0)
            row.manifest_sha256 = str(manifest.get("manifest_sha256") or ("0" * 64))
            row.includes_vectors = bool(manifest.get("includes_vectors"))
            row.includes_parsed = bool(manifest.get("includes_parsed"))
            row.schema_version = str(manifest.get("schema_version") or row.schema_version)
            row.completed_at = _now()
            row.error_summary = None
            _persist_entries(session, row.backup_id, manifest)
            _update_backup_task(session, backup_id, status="COMPLETED", error=None)
            session.commit()
        except BackupBuildError as exc:
            destination.unlink(missing_ok=True)
            for partial in destination.parent.glob("mindmate-backup-*.partial"):
                try:
                    partial.unlink(missing_ok=True)
                except OSError:
                    pass
            row.status = "FAILED"
            row.error_summary = exc.detail[:500]
            row.completed_at = _now()
            _update_backup_task(session, backup_id, status="FAILED", error=exc.detail[:500])
            session.commit()
        except Exception:  # noqa: BLE001 — sanitize for user-facing status
            destination.unlink(missing_ok=True)
            row.status = "FAILED"
            row.error_summary = "备份创建失败，请稍后重试。"
            row.completed_at = _now()
            _update_backup_task(session, backup_id, status="FAILED", error=row.error_summary)
            session.commit()
            # Status is persisted for polling; do not re-raise private exception details.


def verify_managed_backup(session: Session, settings: Settings, backup_id: str) -> dict[str, Any]:
    row = session.get(Backup, backup_id)
    if row is None:
        raise BackupBuildError("BACKUP_NOT_FOUND", "备份记录不存在。")
    if row.status != "COMPLETED":
        raise BackupBuildError("BACKUP_NOT_READY", "仅已完成的备份可以校验。")
    path = resolve_archive_path(settings, row)
    manifest = verify_backup_archive(path, expect_schema=row.schema_version)
    return {
        "backup_id": backup_id,
        "verified": True,
        "file_count": manifest.get("file_count"),
        "total_size": manifest.get("total_size"),
        "schema_version": manifest.get("schema_version"),
        "includes_secrets": False,
        "includes_vectors": bool(manifest.get("includes_vectors")),
    }


__all__ = [
    "UNENCRYPTED_WARNING",
    "backup_public_view",
    "create_backup",
    "get_backup",
    "list_backups",
    "resolve_archive_path",
    "start_or_get_backup",
    "verify_backup",
    "verify_managed_backup",
]
