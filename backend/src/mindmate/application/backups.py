"""Local backup create/list/verify orchestration for MindMate AI."""

from __future__ import annotations

import hashlib
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
    backup_manifest_sha256,
    create_backup_archive,
    read_schema_version,
    verify_backup_archive,
)
from mindmate.application.local_restore import RESTORE_FLOW_AVAILABLE
from mindmate.application.tasks import create_task
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask, Backup, BackupEntry, new_id

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


def _retry_task_key(raw_key: str) -> str:
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"br:{digest}"


def _now() -> datetime:
    return datetime.now(UTC)


def _archive_relative_name(backup_id: str, created_at: datetime) -> str:
    stamp = created_at.strftime("%Y%m%d-%H%M%S")
    return f"backups/mindmate-backup-{stamp}-{backup_id}{ARCHIVE_SUFFIX}"


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
        "restore_available": RESTORE_FLOW_AVAILABLE,
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


def _backup_for_task_key(
    session: Session,
    task_key: str,
    *,
    expected_backup_id: str | None = None,
) -> Backup | None:
    task = session.scalar(
        select(BackgroundTask).where(BackgroundTask.idempotency_key == task_key)
    )
    if task is None:
        return None
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    backup_id = checkpoint.get("backup_id")
    if not isinstance(backup_id, str):
        return None
    if expected_backup_id is not None and backup_id != expected_backup_id:
        raise BackupBuildError("BACKUP_IDEMPOTENCY_CONFLICT", "重试请求已用于另一份备份。")
    return session.get(Backup, backup_id)


def _active_backup(session: Session) -> Backup | None:
    return session.scalar(
        select(Backup)
        .where(Backup.status.in_({"CREATING", "QUEUED", "RUNNING"}))
        .order_by(Backup.created_at, Backup.backup_id)
        .limit(1)
    )


def _commit_new_task_or_resolve_race(
    session: Session,
    *,
    task_key: str,
    expected_backup_id: str | None = None,
) -> Backup:
    from sqlalchemy.exc import IntegrityError

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = _backup_for_task_key(
            session,
            task_key,
            expected_backup_id=expected_backup_id,
        )
        if existing is not None:
            return existing
        if _active_backup(session) is not None:
            raise BackupBuildError(
                "BACKUP_CREATE_IN_PROGRESS",
                "已有备份任务正在排队或运行，请稍后重试。",
            ) from exc
        raise
    backup_id = expected_backup_id
    if backup_id is None:
        task = session.scalar(
            select(BackgroundTask).where(BackgroundTask.idempotency_key == task_key)
        )
        checkpoint = task.checkpoint_json if task and isinstance(task.checkpoint_json, dict) else {}
        backup_id = checkpoint.get("backup_id") if isinstance(checkpoint, dict) else None
    row = session.get(Backup, backup_id) if isinstance(backup_id, str) else None
    if row is None:
        raise BackupBuildError("BACKUP_CREATE_FAILED", "备份任务已保存，但备份记录无法读取。")
    return row


def start_or_get_backup(
    session: Session,
    settings: Settings,
    *,
    idempotency_key: str,
) -> Backup:
    """Persist an idempotent backup record and queued task without building the archive."""
    task_key = _idempotency_task_key(idempotency_key)
    existing = _backup_for_task_key(session, task_key)
    if existing is not None:
        return existing
    if _active_backup(session) is not None:
        raise BackupBuildError(
            "BACKUP_CREATE_IN_PROGRESS",
            "已有备份任务正在排队或运行，请稍后重试。",
        )

    task = create_task(session, "BACKUP_CREATE", task_key, {"phase": "init"})
    session.flush()

    created_at = _now()
    backup_id = str(uuid7())
    relative = _archive_relative_name(backup_id, created_at)
    schema_version = read_schema_version(settings.database_path)
    row = Backup(
        backup_id=backup_id,
        archive_relative_path=relative,
        status="QUEUED",
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
    task.checkpoint_json = {"backup_id": backup_id, "phase": "queued"}
    task.status = "QUEUED"
    task.phase = "QUEUED"
    task.progress = None
    task.error_summary = None
    task.completed_at = None
    task.lease_owner = None
    task.lease_until = None
    task.updated_at = created_at
    return _commit_new_task_or_resolve_race(session, task_key=task_key)


def retry_backup(
    session: Session,
    *,
    backup_id: str,
    idempotency_key: str,
) -> Backup:
    task_key = _retry_task_key(idempotency_key)
    existing = _backup_for_task_key(session, task_key, expected_backup_id=backup_id)
    if existing is not None:
        return existing
    row = session.get(Backup, backup_id)
    if row is None:
        raise BackupBuildError("BACKUP_NOT_FOUND", "备份记录不存在。")
    if row.status in {"CREATING", "QUEUED", "RUNNING"}:
        return row
    if row.status != "FAILED":
        raise BackupBuildError("BACKUP_RETRY_NOT_ALLOWED", "仅失败的备份可以重试。")
    active = _active_backup(session)
    if active is not None:
        raise BackupBuildError(
            "BACKUP_CREATE_IN_PROGRESS",
            "已有备份任务正在排队或运行，请稍后重试。",
        )

    task = create_task(session, "BACKUP_CREATE", task_key, {"backup_id": backup_id})
    task.status = "QUEUED"
    task.phase = "QUEUED"
    task.progress = None
    task.error_summary = None
    task.completed_at = None
    task.lease_owner = None
    task.lease_until = None
    task.checkpoint_json = {"backup_id": backup_id, "phase": "queued"}
    task.updated_at = _now()
    row.status = "QUEUED"
    row.file_count = 0
    row.total_size = 0
    row.manifest_sha256 = "0" * 64
    row.includes_vectors = False
    row.includes_parsed = False
    row.completed_at = None
    row.error_summary = None
    session.execute(delete(BackupEntry).where(BackupEntry.backup_id == backup_id))
    return _commit_new_task_or_resolve_race(
        session,
        task_key=task_key,
        expected_backup_id=backup_id,
    )


def verify_managed_backup(session: Session, settings: Settings, backup_id: str) -> dict[str, Any]:
    row = session.get(Backup, backup_id)
    if row is None:
        raise BackupBuildError("BACKUP_NOT_FOUND", "备份记录不存在。")
    if row.status != "COMPLETED":
        raise BackupBuildError("BACKUP_NOT_READY", "仅已完成的备份可以校验。")
    path = resolve_archive_path(settings, row)
    try:
        manifest = verify_backup_archive(path, expect_schema=row.schema_version)
    except BackupBuildError:
        row.status = "FAILED"
        row.completed_at = _now()
        row.error_summary = "备份文件缺失或未通过完整性校验。"
        session.commit()
        raise
    if backup_manifest_sha256(path) != row.manifest_sha256:
        row.status = "FAILED"
        row.completed_at = _now()
        row.error_summary = "备份文件与记录不匹配，无法下载。"
        session.commit()
        raise BackupBuildError("BACKUP_ARCHIVE_MISMATCH", "备份文件未通过归档一致性校验。")
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
    "retry_backup",
    "start_or_get_backup",
    "verify_backup",
    "verify_managed_backup",
]
