"""Full local restore: precheck, recovery point, and restart-gated switch.

Windows cannot replace an open SQLite database. This module never overwrites the
live data directory while the application engine is running. Confirmation writes
a recovery point and a restart marker; the next process start swaps directories
only after the previous process has released the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from mindmate.application.local_backup import (
    FORMAT_VERSION,
    MAX_COMPRESSION_RATIO,
    MAX_ENTRY_COUNT,
    MAX_SINGLE_ENTRY_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    BackupBuildError,
    read_schema_version,
    sha256_file,
    sqlite_consistent_snapshot,
)
from mindmate.application.provider_configuration import (
    CONSENT_SETTING_KEY,
    GENERATION_MODE_SETTING_KEY,
    OPENAI_CONSENT_SETTING_KEY,
    OPENAI_PROBE_SETTING_KEY,
    PROBE_SETTING_KEY,
    read_setting,
    write_setting,
)
from mindmate.config import Settings

RESTORE_FLOW_AVAILABLE = True
CONFIRM_PHRASE = "覆盖当前全部本地数据"
PRECHECK_TTL = timedelta(minutes=30)
UPLOAD_TTL = timedelta(hours=2)
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
SPACE_MARGIN_BYTES = 64 * 1024 * 1024
RESTORE_RECONFIRM_KEY = "restore.provider_reconfirm_required"
_ID_RE = re.compile(r"^[0-9a-fA-F-]{16,80}$")
_FINGERPRINT_TABLES = (
    "files",
    "knowledge_bases",
    "conversations",
    "learning_sessions",
    "content_objects",
)
_SWAPPABLE = ("database", "objects", "parsed", "config", "vectors")
_WORKER_ATTRS = (
    "chat_worker",
    "embedding_model_install_worker",
    "parse_worker",
    "knowledge_membership_worker",
    "index_preprocessing_worker",
    "index_chunking_worker",
    "index_embedding_worker",
    "index_fts_worker",
    "index_activation_worker",
    "history_search_backfill",
    "history_trash_purge_worker",
    "task_retention_worker",
)
_RESTORE_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _control_dir(settings: Settings) -> Path:
    return settings.runtime_dir / "restore-control"


def _state_path(settings: Settings) -> Path:
    return _control_dir(settings) / "state.json"


def _freeze_path(settings: Settings) -> Path:
    return _control_dir(settings) / "writes-frozen"


def _inbox_dir(settings: Settings) -> Path:
    return _control_dir(settings) / "inbox"


def _staging_root(settings: Settings) -> Path:
    return _control_dir(settings) / "staging"


def _aside_root(settings: Settings) -> Path:
    return _control_dir(settings) / "aside"


def _recovery_root(settings: Settings) -> Path:
    return settings.resolved_data_dir / "recovery-points"


def _under(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _require_id(value: str, code: str) -> str:
    if not value or not _ID_RE.fullmatch(value) or "/" in value or "\\" in value or ".." in value:
        raise BackupBuildError(code, "恢复标识无效。")
    return value


def _public_detail(detail: str) -> str:
    text = " ".join(detail.split())
    lowered = text.replace("\\", "/").lower()
    if (
        ":/" in lowered
        or lowered.startswith("/")
        or "/users/" in lowered
        or "/temp/" in lowered
        or "appdata" in lowered
    ):
        return "恢复操作未能完成。当前数据未切换。"
    if len(text) > 180:
        return text[:180]
    return text or "恢复操作未能完成。当前数据未切换。"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def load_restore_state(settings: Settings) -> dict[str, Any] | None:
    path = _state_path(settings)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save_state(settings: Settings, state: dict[str, Any]) -> None:
    _atomic_write_json(_state_path(settings), state)


def restore_writes_frozen(settings: Settings) -> bool:
    return _freeze_path(settings).is_file()


def _set_frozen(settings: Settings, execution_id: str | None) -> None:
    path = _freeze_path(settings)
    if execution_id:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(execution_id, encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def _idempotency_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def session_fingerprint(token: str | None) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def restore_provider_reconfirm_required(session: Any) -> bool:
    stored = read_setting(session, RESTORE_RECONFIRM_KEY) or {}
    return stored.get("required") is True


def acknowledge_provider_reconfirm(session: Any, settings: Settings | None = None) -> None:
    write_setting(session, RESTORE_RECONFIRM_KEY, {"required": False})
    session.commit()
    if settings is not None:
        state = load_restore_state(settings)
        if state is not None:
            state["provider_reconfirm_required"] = False
            _save_state(settings, state)


def _stop_worker(worker: Any) -> None:
    stop = getattr(worker, "stop", None)
    if not callable(stop):
        return
    try:
        stop(0.5)
    except TypeError:
        stop()


def _start_worker(worker: Any) -> None:
    start = getattr(worker, "start", None)
    if callable(start):
        start()


def quiesce_writers(app: Any) -> None:
    for name in _WORKER_ATTRS:
        _stop_worker(getattr(app.state, name, None))


def resume_writers(app: Any) -> None:
    for name in _WORKER_ATTRS:
        _start_worker(getattr(app.state, name, None))


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    return bool(hasattr(os.path, "isjunction") and os.path.isjunction(path))


def _reject_reparse(path: Path) -> None:
    current = path
    while True:
        if _is_reparse(current):
            raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "恢复拒绝符号链接或 Windows 重解析点。")
        if current.parent == current:
            break
        current = current.parent


def free_bytes(path: Path) -> int:
    target = path if path.exists() else path.parent
    return int(shutil.disk_usage(target).free)


def assert_writable(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / ".restore-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise BackupBuildError("RESTORE_NOT_WRITABLE", "数据目录不可写，已停止恢复。") from exc


def _data_fingerprint(database_path: Path) -> dict[str, Any]:
    counts: dict[str, int | None] = {}
    if not database_path.is_file():
        return {"schema_version": "missing", "counts": counts}
    uri = f"file:{database_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        for table in _FINGERPRINT_TABLES:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0
            except sqlite3.Error:
                counts[table] = None
    return {"schema_version": read_schema_version(database_path), "counts": counts}


def _script_directory(settings: Settings) -> ScriptDirectory:
    config = Config(str(settings.alembic_ini))
    return ScriptDirectory.from_config(config)


def _schema_plan(settings: Settings, schema_version: str) -> str:
    """Return same, upgrade, or raise when the archived schema cannot be applied."""
    if schema_version in {"", "unknown", None}:
        raise BackupBuildError("BACKUP_SCHEMA_UNKNOWN", "备份数据库版本无法识别，已禁止恢复。")
    script = _script_directory(settings)
    heads = script.get_heads()
    if len(heads) != 1:
        raise BackupBuildError("BACKUP_SCHEMA_UNKNOWN", "应用迁移基线不唯一，已禁止恢复。")
    head = heads[0]
    if schema_version == head:
        return "same"
    revisions = {rev.revision for rev in script.walk_revisions()}
    if schema_version not in revisions:
        raise BackupBuildError("BACKUP_SCHEMA_NEWER", "备份的数据库版本比当前应用新，已禁止恢复。")
    current = script.get_revision(head)
    seen: set[str] = set()
    while current is not None and current.revision not in seen:
        if current.revision == schema_version:
            return "upgrade"
        seen.add(current.revision)
        down = current.down_revision
        if not isinstance(down, str):
            if down:
                raise BackupBuildError("BACKUP_SCHEMA_UNKNOWN", "备份迁移路径不受支持，已禁止恢复。")
            current = None
            continue
        current = script.get_revision(down)
    raise BackupBuildError("BACKUP_SCHEMA_UNKNOWN", "备份迁移路径不受支持，已禁止恢复。")


def _member_relative(name: str, seen: set[str], folded: set[str]) -> str:
    raw = name
    if raw.endswith("/") or raw.endswith("\\"):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目路径无效。")
    if "\\" in raw:
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得包含反斜杠。")
    if raw.startswith("/") or raw.startswith("//"):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得使用绝对路径。")
    if re.match(r"^[A-Za-z]:", raw):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得使用盘符路径。")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得包含路径穿越。")
    relative = "/".join(parts)
    if relative != raw:
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目路径无效。")
    if relative in seen:
        raise BackupBuildError("BACKUP_DUPLICATE_ENTRY", "备份包存在重复条目。")
    token = relative.casefold()
    if token in folded:
        raise BackupBuildError("BACKUP_CASE_COLLISION", "备份包存在大小写冲突路径。")
    seen.add(relative)
    folded.add(token)
    return relative


def _check_member_limits(info: zipfile.ZipInfo, total_uncompressed: int) -> int:
    if info.is_dir():
        return total_uncompressed
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "备份包含符号链接条目。")
    if info.file_size > MAX_SINGLE_ENTRY_BYTES:
        raise BackupBuildError("BACKUP_ENTRY_TOO_LARGE", "备份条目过大。")
    total_uncompressed += info.file_size
    if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise BackupBuildError("BACKUP_TOO_LARGE", "备份解压后的总大小超过安全上限。")
    if info.compress_size > 0 and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
        if info.file_size > 1024 * 1024:
            raise BackupBuildError("BACKUP_COMPRESSION_SUSPECT", "备份压缩比异常，已禁止恢复。")
    return total_uncompressed


def _hash_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[str, int, bytes]:
    digest = hashlib.sha256()
    size = 0
    head = b""
    with archive.open(info, "r") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > info.file_size or size > MAX_SINGLE_ENTRY_BYTES:
                raise BackupBuildError("BACKUP_ENTRY_TOO_LARGE", "备份条目读取超过声明大小。")
            digest.update(chunk)
            if len(head) < 4096:
                head += chunk[: 4096 - len(head)]
    if size != info.file_size:
        raise BackupBuildError("BACKUP_SIZE_MISMATCH", "备份条目大小不匹配。")
    return digest.hexdigest(), size, head


def inspect_restore_archive(archive_path: Path, settings: Settings) -> dict[str, Any]:
    """Stream-check a format-1 archive without touching the live database."""
    if not archive_path.is_file():
        raise BackupBuildError("BACKUP_ARCHIVE_MISSING", "备份包不存在。")
    if archive_path.stat().st_size > MAX_UPLOAD_BYTES:
        raise BackupBuildError("BACKUP_UPLOAD_TOO_LARGE", "备份包超过上传大小上限。")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > MAX_ENTRY_COUNT + 1:
                raise BackupBuildError("BACKUP_TOO_MANY_ENTRIES", "备份条目数量超过安全上限。")
            seen: set[str] = set()
            folded: set[str] = set()
            total = 0
            for info in infos:
                total = _check_member_limits(info, total)
                _member_relative(info.filename, seen, folded)
            if "manifest.json" not in seen:
                raise BackupBuildError("BACKUP_MANIFEST_MISSING", "备份包缺少 manifest。")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 2 * 1024 * 1024:
                raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest 过大。")
            _, _, manifest_head = _hash_member(archive, manifest_info)
            manifest_bytes = manifest_head if manifest_info.file_size <= 4096 else archive.read("manifest.json")
            manifest = json.loads(manifest_bytes)
            if not isinstance(manifest, dict):
                raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest 格式无效。")
            if manifest.get("backup_format_version") != FORMAT_VERSION:
                raise BackupBuildError("BACKUP_FORMAT_UNSUPPORTED", "不支持的备份格式版本。")
            if manifest.get("includes_secrets") or manifest.get("encrypted"):
                raise BackupBuildError("BACKUP_FORMAT_UNSUPPORTED", "当前只接受未加密且不含秘密的格式 1 备份。")
            entries = manifest.get("entries")
            if not isinstance(entries, list) or len(entries) != manifest.get("file_count"):
                raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest 文件计数不一致。")
            entry_by_path: dict[str, dict[str, Any]] = {}
            for entry in entries:
                if not isinstance(entry, dict) or "path" not in entry:
                    raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest 条目无效。")
                path = str(entry["path"])
                if path not in seen:
                    raise BackupBuildError("BACKUP_ENTRY_MISSING", "manifest 引用的文件缺失。")
                entry_by_path[path] = entry
            for info in infos:
                if info.filename == "manifest.json":
                    continue
                expected = entry_by_path.get(info.filename)
                if expected is None:
                    raise BackupBuildError("BACKUP_MANIFEST_INVALID", "备份包包含清单之外的文件。")
                digest, size, head = _hash_member(archive, info)
                if size != int(expected.get("byte_size", -1)) or digest != expected.get("sha256"):
                    raise BackupBuildError("BACKUP_HASH_MISMATCH", "备份条目哈希或大小不匹配。")
                top = info.filename.split("/", 1)[0]
                if top in {"models", "logs", "vectors", "backups", "recovery-points", "runtime"}:
                    raise BackupBuildError("BACKUP_CONTAINS_EXCLUDED", "备份包含不允许恢复的目录。")
                lowered = head.lower()
                if b"begin private key" in lowered or b"mindmate_api_key" in lowered:
                    raise BackupBuildError("BACKUP_CONTAINS_SECRETS", "备份包疑似包含秘密内容。")
            if "database/mindmate.db" not in entry_by_path:
                raise BackupBuildError("BACKUP_DATABASE_MISSING", "备份包缺少数据库快照。")
            schema_version = str(manifest.get("schema_version") or "")
            plan = _schema_plan(settings, schema_version)
            database_report = _inspect_archived_database(archive, entry_by_path)
            return {
                "created_at": manifest.get("created_at"),
                "backup_format_version": FORMAT_VERSION,
                "app_version": manifest.get("app_version"),
                "schema_version": schema_version,
                "schema_plan": plan,
                "file_count": int(manifest.get("file_count") or 0),
                "total_size": int(manifest.get("total_size") or 0),
                "includes_parsed": bool(manifest.get("includes_parsed")),
                "includes_vectors": False,
                "includes_secrets": False,
                "encrypted": False,
                "rebuild_after_restore": list(manifest.get("rebuild_after_restore") or []),
                "database_ok": database_report["ok"],
                "referenced_files": database_report["referenced_files"],
            }
    except BackupBuildError:
        raise
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise BackupBuildError("BACKUP_VERIFY_FAILED", "备份包校验失败。") from exc


def _inspect_archived_database(archive: zipfile.ZipFile, entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    info = archive.getinfo("database/mindmate.db")
    import tempfile

    descriptor, raw_name = tempfile.mkstemp(prefix="mindmate-restore-db-", suffix=".db")
    os.close(descriptor)
    temporary = Path(raw_name)
    try:
        with archive.open(info, "r") as src, temporary.open("wb") as dst:
            remaining = info.file_size
            while remaining:
                chunk = src.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                dst.write(chunk)
                remaining -= len(chunk)
        conn = sqlite3.connect(temporary.as_posix())
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()
            if not quick or quick[0] != "ok":
                raise BackupBuildError("BACKUP_DATABASE_CORRUPT", "备份内数据库未通过完整性检查。")
            conn.execute("PRAGMA foreign_keys=ON")
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise BackupBuildError("BACKUP_DATABASE_CORRUPT", "备份内数据库未通过外键检查。")
            try:
                rows = conn.execute("SELECT storage_relative_path FROM content_objects").fetchall()
            except sqlite3.Error:
                rows = []
            for row in rows:
                relative = str(row[0]).replace("\\", "/")
                if "\\" in str(row[0]) or relative not in entries:
                    raise BackupBuildError("BACKUP_CONTENT_MISSING", "备份内数据库引用了缺失的托管文件。")
            return {"ok": True, "referenced_files": len(rows)}
        finally:
            conn.close()
    finally:
        for suffix in ("", "-wal", "-shm"):
            Path(str(temporary) + suffix).unlink(missing_ok=True)


def _summary(inspected: dict[str, Any], *, executable: bool, block_reason: str | None = None) -> dict[str, Any]:
    return {
        "created_at": inspected.get("created_at"),
        "backup_format_version": inspected.get("backup_format_version"),
        "app_version": inspected.get("app_version"),
        "schema_version": inspected.get("schema_version"),
        "schema_plan": inspected.get("schema_plan"),
        "file_count": inspected.get("file_count"),
        "total_size": inspected.get("total_size"),
        "includes": {
            "database_snapshot": True,
            "content_objects": True,
            "parsed_artifacts": bool(inspected.get("includes_parsed")),
            "non_secret_config": True,
            "vectors": False,
            "fts_external": False,
            "models": False,
            "logs": False,
            "secrets": False,
        },
        "excludes": ["密钥", "向量索引", "模型缓存", "日志", "可重建缓存"],
        "overwrite_scope": "整份本地业务数据将被覆盖，不与当前资料、知识库、对话或学习记录合并。",
        "warnings": [
            "备份未加密，包含私人文件和学习记录。请确认包来自你自己的受保护磁盘。",
            "备份不含密钥、向量、外部全文索引和模型。恢复后保持 Mock，需重新确认后才能外发；索引在重建并校验前不可检索。",
        ],
        "index_effect": "NEEDS_REBUILD",
        "provider_effect": "RECONFIRM_REQUIRED",
        "executable": executable,
        "block_reason": block_reason,
    }


def _locked(func):
    def wrapper(*args, **kwargs):
        with _RESTORE_LOCK:
            return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


def cleanup_expired_uploads(settings: Settings) -> None:
    inbox = _inbox_dir(settings)
    if not inbox.is_dir():
        return
    state = load_restore_state(settings) or {}
    active = str(state.get("upload_id") or "")
    cutoff = _now() - UPLOAD_TTL
    for child in inbox.iterdir():
        if not child.is_file():
            continue
        if child.stem == active and state.get("phase") in {"PRECHECKED", "RESTART_REQUIRED", "APPLYING"}:
            continue
        try:
            modified = datetime.fromtimestamp(child.stat().st_mtime, UTC)
        except OSError:
            continue
        if modified < cutoff:
            child.unlink(missing_ok=True)


@_locked
def save_uploaded_archive(settings: Settings, source: Any, *, idempotency_key: str) -> dict[str, Any]:
    cleanup_expired_uploads(settings)
    state = load_restore_state(settings) or {}
    if state.get("phase") in {"RESTART_REQUIRED", "APPLYING"}:
        raise BackupBuildError("RESTORE_IN_PROGRESS", "已有恢复正在等待重启或切换，不能上传另一个包。")
    key_hash = _idempotency_hash(idempotency_key)
    if state.get("upload_idempotency_hash") == key_hash and state.get("upload_id"):
        existing = _inbox_dir(settings) / f"{state['upload_id']}.mindmate-backup"
        if existing.is_file():
            return {
                "upload_id": state["upload_id"],
                "archive_sha256": state.get("archive_sha256"),
                "byte_size": existing.stat().st_size,
            }
    from uuid6 import uuid7

    upload_id = str(uuid7())
    _require_id(upload_id, "RESTORE_UPLOAD_INVALID")
    destination = _inbox_dir(settings) / f"{upload_id}.mindmate-backup"
    if not _under(_inbox_dir(settings), destination):
        raise BackupBuildError("BACKUP_PATH_INVALID", "上传暂存位置无效。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise BackupBuildError("BACKUP_UPLOAD_TOO_LARGE", "备份包超过上传大小上限。")
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if size <= 0:
        destination.unlink(missing_ok=True)
        raise BackupBuildError("BACKUP_ARCHIVE_MISSING", "备份包是空的。")
    archive_sha = digest.hexdigest()
    state.update(
        {
            "phase": "UPLOADED",
            "upload_id": upload_id,
            "archive_sha256": archive_sha,
            "upload_idempotency_hash": key_hash,
            "uploaded_at": _stamp(_now()),
        }
    )
    _save_state(settings, state)
    return {"upload_id": upload_id, "archive_sha256": archive_sha, "byte_size": size}


def _archive_for_upload(settings: Settings, upload_id: str) -> Path:
    _require_id(upload_id, "RESTORE_UPLOAD_INVALID")
    path = (_inbox_dir(settings) / f"{upload_id}.mindmate-backup").resolve()
    if not _under(_inbox_dir(settings), path):
        raise BackupBuildError("BACKUP_PATH_INVALID", "上传暂存位置无效。")
    if not path.is_file():
        raise BackupBuildError("BACKUP_ARCHIVE_MISSING", "找不到待预检的备份包。")
    return path


@_locked
def precheck_upload(
    settings: Settings,
    upload_id: str,
    *,
    session_fingerprint_value: str,
) -> dict[str, Any]:
    cleanup_expired_uploads(settings)
    state = load_restore_state(settings) or {}
    if state.get("phase") in {"RESTART_REQUIRED", "APPLYING"}:
        raise BackupBuildError("RESTORE_IN_PROGRESS", "已有恢复正在等待重启，请先取消或完成重启。")
    archive = _archive_for_upload(settings, upload_id)
    if state.get("upload_id") != upload_id:
        raise BackupBuildError("RESTORE_UPLOAD_INVALID", "上传记录与暂存包不一致。")
    inspected = inspect_restore_archive(archive, settings)
    fingerprint = _data_fingerprint(settings.database_path)
    needed = int(inspected["total_size"]) + SPACE_MARGIN_BYTES
    # Recovery point is about the same size as the live managed data, bounded by the archive.
    if free_bytes(settings.resolved_data_dir) < needed * 2:
        summary = _summary(inspected, executable=False, block_reason="可用磁盘空间不足，已禁止执行。")
        raise BackupBuildError("RESTORE_DISK_SPACE", "可用磁盘空间不足，预检未改动当前数据。")
    assert_writable(_control_dir(settings))
    assert_writable(settings.database_path.parent)
    from uuid6 import uuid7

    precheck_id = str(uuid7())
    expires = _now() + PRECHECK_TTL
    summary = _summary(inspected, executable=True)
    state.update(
        {
            "phase": "PRECHECKED",
            "precheck_id": precheck_id,
            "upload_id": upload_id,
            "archive_sha256": sha256_file(archive),
            "session_fingerprint": session_fingerprint_value,
            "expires_at": _stamp(expires),
            "data_fingerprint": fingerprint,
            "summary": summary,
            "switch_step": None,
            "error_code": None,
            "error_detail": None,
            "one_time_consumed": False,
        }
    )
    _save_state(settings, state)
    return public_restore_status(settings)


def _expired(state: dict[str, Any]) -> bool:
    expires = _parse_stamp(str(state.get("expires_at") or ""))
    return bool(expires and expires < _now() and state.get("phase") == "PRECHECKED")


@_locked
def confirm_restore(
    settings: Settings,
    app: Any,
    *,
    precheck_id: str,
    confirm_full_replace: bool,
    confirm_phrase: str,
    idempotency_key: str,
    session_fingerprint_value: str,
) -> dict[str, Any]:
    _require_id(precheck_id, "RESTORE_PRECHECK_INVALID")
    state = load_restore_state(settings) or {}
    key_hash = _idempotency_hash(idempotency_key)
    if state.get("phase") in {"RESTART_REQUIRED", "APPLYING", "SUCCEEDED"} and state.get("execute_idempotency_hash") == key_hash:
        return public_restore_status(settings)
    if state.get("phase") in {"RESTART_REQUIRED", "APPLYING"}:
        raise BackupBuildError("RESTORE_ALREADY_CONFIRMED", "恢复已经确认，重复请求不会再次覆盖。")
    if not confirm_full_replace or confirm_phrase != CONFIRM_PHRASE:
        raise BackupBuildError("RESTORE_CONFIRMATION_REQUIRED", "必须明确确认整份覆盖当前本地数据。")
    if state.get("phase") != "PRECHECKED" or state.get("precheck_id") != precheck_id:
        raise BackupBuildError("RESTORE_PRECHECK_INVALID", "预检结果无效或已过期，请重新预检。")
    if state.get("one_time_consumed"):
        raise BackupBuildError("RESTORE_ALREADY_CONFIRMED", "该预检已经执行过，不会再次覆盖。")
    if _expired(state):
        raise BackupBuildError("RESTORE_PRECHECK_EXPIRED", "预检已过期，请重新选择备份包。")
    if state.get("session_fingerprint") != session_fingerprint_value:
        raise BackupBuildError("RESTORE_SESSION_MISMATCH", "请在建立预检的同一个本地会话中确认恢复。")
    archive = _archive_for_upload(settings, str(state.get("upload_id")))
    current_hash = sha256_file(archive)
    if current_hash != state.get("archive_sha256"):
        raise BackupBuildError("RESTORE_ARCHIVE_CHANGED", "预检后备份包已变化，已禁止执行。")
    current_fingerprint = _data_fingerprint(settings.database_path)
    if current_fingerprint != state.get("data_fingerprint"):
        raise BackupBuildError("RESTORE_DATA_CHANGED", "预检后本地数据已变化，请重新预检。")
    if free_bytes(settings.resolved_data_dir) < int(state["summary"]["total_size"]) * 2 + SPACE_MARGIN_BYTES:
        raise BackupBuildError("RESTORE_DISK_SPACE", "可用磁盘空间不足，已停止恢复，当前数据未改动。")
    quiesce_writers(app)
    try:
        recovery_id = _create_recovery_point(settings)
    except Exception:
        resume_writers(app)
        raise
    from uuid6 import uuid7

    execution_id = str(uuid7())
    state.update(
        {
            "phase": "RESTART_REQUIRED",
            "execution_id": execution_id,
            "execute_idempotency_hash": key_hash,
            "recovery_point_id": recovery_id,
            "one_time_consumed": True,
            "confirmed_at": _stamp(_now()),
            "switch_step": None,
            "error_code": None,
            "error_detail": None,
        }
    )
    _save_state(settings, state)
    _set_frozen(settings, execution_id)
    return public_restore_status(settings)


@_locked
def cancel_restore(settings: Settings, app: Any) -> dict[str, Any]:
    state = load_restore_state(settings) or {}
    phase = state.get("phase")
    if state.get("switch_step") or phase == "APPLYING":
        raise BackupBuildError("RESTORE_IN_PROGRESS", "切换已经开始，不能取消。请等待启动回滚或完成。")
    if phase == "RESTART_REQUIRED":
        resume_writers(app)
    state["phase"] = "CANCELLED"
    state["switch_step"] = None
    state["one_time_consumed"] = False
    _save_state(settings, state)
    _set_frozen(settings, None)
    return public_restore_status(settings)


def _create_recovery_point(settings: Settings) -> str:
    from uuid6 import uuid7

    recovery_id = str(uuid7())
    root = _recovery_root(settings)
    partial = root / f".partial-{recovery_id}"
    final = root / recovery_id
    if partial.exists():
        shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    try:
        db_dest = partial / "database" / "mindmate.db"
        database_present = settings.database_path.is_file()
        if database_present:
            sqlite_consistent_snapshot(settings.database_path, db_dest)
            quick = _quick_check_file(db_dest)
            if quick != "ok":
                raise BackupBuildError("RESTORE_RECOVERY_POINT_INVALID", "当前数据恢复点未通过校验，已停止。")
        data_root = settings.resolved_data_dir
        copied = 0
        for name in ("objects", "parsed", "config"):
            source = data_root / name
            if source.exists():
                _reject_reparse(source)
                copied += _copy_tree(source, partial / name)
        manifest = {
            "recovery_point_id": recovery_id,
            "created_at": _stamp(_now()),
            "copied_files": copied,
            "database_present": database_present,
        }
        _atomic_write_json(partial / "manifest.json", manifest)
        if final.exists():
            raise BackupBuildError("RESTORE_RECOVERY_POINT_INVALID", "恢复点位置冲突，已停止。")
        partial.rename(final)
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return recovery_id


def _copy_tree(source: Path, destination: Path) -> int:
    count = 0
    if not source.exists():
        return 0
    for path in source.rglob("*"):
        if _is_reparse(path):
            raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "恢复点拒绝符号链接或重解析点。")
        relative = path.relative_to(source)
        target = destination / relative
        if not _under(destination, target):
            raise BackupBuildError("BACKUP_PATH_INVALID", "恢复点路径越界。")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
        if count > MAX_ENTRY_COUNT:
            raise BackupBuildError("BACKUP_TOO_MANY_ENTRIES", "恢复点文件数量超过安全上限。")
    return count


def _quick_check_file(database_path: Path) -> str:
    conn = sqlite3.connect(database_path.as_posix())
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        return str(row[0]) if row else "fail"
    finally:
        conn.close()


def assert_database_unlocked(database_path: Path) -> None:
    if not database_path.is_file():
        return
    conn = sqlite3.connect(database_path.as_posix(), timeout=0.2)
    try:
        conn.execute("PRAGMA busy_timeout=200")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("COMMIT")
    except sqlite3.OperationalError as exc:
        raise BackupBuildError("RESTORE_DATABASE_LOCKED", "数据库仍被占用，已停止切换，当前数据保持不变。") from exc
    finally:
        conn.close()


def _rename_released(source: Path, dest: Path) -> None:
    """Rename a directory after Windows releases a just-closed SQLite handle."""
    last: OSError | None = None
    for attempt in range(8):
        try:
            source.rename(dest)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.05 * (attempt + 1))
    raise BackupBuildError(
        "RESTORE_DATABASE_LOCKED",
        "数据库目录仍被占用，已停止切换，当前数据保持不变。",
    ) from last


def swap_tree(live: Path, staged: Path, aside: Path) -> None:
    """Move one directory aside, then move the staged directory into place.

    Tests may replace this function to inject a crash between the two renames.
    """
    if _is_reparse(live) or (staged.exists() and _is_reparse(staged)):
        raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "切换拒绝符号链接或重解析点。")
    aside.parent.mkdir(parents=True, exist_ok=True)
    if live.exists():
        if aside.exists():
            raise BackupBuildError("RESTORE_SWITCH_CONFLICT", "切换暂存位置已存在，已停止。")
        _rename_released(live, aside)
    if staged.exists():
        if live.exists():
            raise BackupBuildError("RESTORE_SWITCH_CONFLICT", "切换目标仍存在，已停止。")
        _rename_released(staged, live)
    elif not live.exists():
        live.mkdir(parents=True, exist_ok=True)


def _extract_archive(archive_path: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as archive:
        seen: set[str] = set()
        folded: set[str] = set()
        total = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            total = _check_member_limits(info, total)
            relative = _member_relative(info.filename, seen, folded)
            target = (destination / relative).resolve()
            if not _under(destination, target):
                raise BackupBuildError("BACKUP_PATH_INVALID", "解包路径越界。")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise BackupBuildError("BACKUP_CASE_COLLISION", "解包目标已存在。")
            _reject_reparse(target.parent)
            remaining = info.file_size
            written = 0
            with archive.open(info, "r") as src, target.open("xb") as dst:
                while remaining:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size:
                        raise BackupBuildError("BACKUP_ENTRY_TOO_LARGE", "解包条目超过声明大小。")
                    dst.write(chunk)
                    remaining -= len(chunk)
            if _is_reparse(target):
                target.unlink(missing_ok=True)
                raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "解包结果是重解析点。")


def _migrate_staged_database(settings: Settings, staging: Path) -> None:
    staged_settings = settings.model_copy(update={"data_dir": staging, "env": "test"})
    config = Config(str(settings.alembic_ini))
    config.attributes["settings"] = staged_settings
    previous = logging.getLogger("alembic").level
    logging.getLogger("alembic").setLevel(logging.ERROR)
    try:
        command.upgrade(config, "head")
    except Exception as exc:
        raise BackupBuildError("RESTORE_MIGRATION_FAILED", "备份数据库迁移失败，当前数据未切换。") from exc
    finally:
        logging.getLogger("alembic").setLevel(previous)
    if _quick_check_file(staging / "database" / "mindmate.db") != "ok":
        raise BackupBuildError("RESTORE_MIGRATION_FAILED", "迁移后的数据库未通过完整性检查。")


def _reconcile_database(database_path: Path) -> None:
    now = _stamp(_now())
    conn = sqlite3.connect(database_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            UPDATE knowledge_bases
            SET active_index_version_id = NULL,
                status = CASE WHEN status = 'EMPTY' THEN status ELSE 'NEEDS_REBUILD' END
            WHERE active_index_version_id IS NOT NULL OR status IN ('READY', 'PARTIAL', 'PREPARING')
            """
        )
        conn.execute(
            """
            UPDATE knowledge_base_files
            SET index_state = 'NEEDS_REBUILD'
            WHERE index_state = 'READY'
            """
        )
        conn.execute(
            """
            UPDATE index_versions
            SET status = 'NEEDS_REBUILD',
                fts_status = 'NEEDS_REBUILD',
                embedding_status = 'NEEDS_REBUILD',
                activation_error_code = 'RESTORE_INDEX_NOT_REUSABLE'
            WHERE status IN ('READY', 'BUILDING')
            """
        )
        conn.execute(
            """
            UPDATE background_tasks
            SET status = 'INTERRUPTED',
                error_summary = '恢复后未继续原任务。'
            WHERE status IN ('QUEUED', 'RUNNING')
            """
        )
        conn.execute(
            """
            UPDATE backups
            SET status = 'FAILED',
                error_summary = '恢复包快照于备份完成前，且备份目录不随包恢复，此记录已关闭。'
            WHERE status IN ('CREATING', 'RUNNING', 'QUEUED')
            """
        )
        reconfirm = json.dumps({"required": True, "reason": "BACKUP_EXCLUDES_SECRETS"}, ensure_ascii=False)
        mode = json.dumps({"mode": "mock"}, ensure_ascii=False)
        consent = json.dumps({"version": "", "accepted_at": None, "cleared_by": "restore"}, ensure_ascii=False)
        for key, payload in (
            (RESTORE_RECONFIRM_KEY, reconfirm),
            (GENERATION_MODE_SETTING_KEY, mode),
            (CONSENT_SETTING_KEY, consent),
            (OPENAI_CONSENT_SETTING_KEY, consent),
        ):
            conn.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value_json, setting_schema_version, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value_json = excluded.setting_value_json,
                    setting_schema_version = 1,
                    updated_at = excluded.updated_at
                """,
                (key, payload, now),
            )
        conn.execute("DELETE FROM app_settings WHERE setting_key = ?", (PROBE_SETTING_KEY,))
        conn.execute("DELETE FROM app_settings WHERE setting_key = ?", (OPENAI_PROBE_SETTING_KEY,))
        conn.commit()
    finally:
        conn.close()


def _set_step(settings: Settings, state: dict[str, Any], step: str) -> None:
    state["phase"] = "APPLYING"
    state["switch_step"] = step
    _save_state(settings, state)


def _perform_switch(settings: Settings, state: dict[str, Any]) -> None:
    archive = _archive_for_upload(settings, str(state.get("upload_id")))
    if sha256_file(archive) != state.get("archive_sha256"):
        raise BackupBuildError("RESTORE_ARCHIVE_CHANGED", "重启前备份包已变化，已停止切换。")
    recovery_id = str(state.get("recovery_point_id") or "")
    recovery = _recovery_root(settings) / recovery_id
    if not recovery.is_dir() or not _under(_recovery_root(settings), recovery):
        raise BackupBuildError("RESTORE_RECOVERY_POINT_INVALID", "找不到恢复点，已停止切换。")
    snapshot = recovery / "database" / "mindmate.db"
    if snapshot.is_file() and _quick_check_file(snapshot) != "ok":
        raise BackupBuildError("RESTORE_RECOVERY_POINT_INVALID", "恢复点数据库校验失败，已停止切换。")
    staging = _staging_root(settings) / str(state.get("execution_id"))
    _extract_archive(archive, staging)
    inspect_restore_archive(archive, settings)
    _migrate_staged_database(settings, staging)
    if not (staging / "database" / "mindmate.db").is_file():
        raise BackupBuildError("BACKUP_DATABASE_MISSING", "解包后缺少数据库，已停止切换。")
    assert_database_unlocked(settings.database_path)
    data_root = settings.resolved_data_dir
    aside = _aside_root(settings) / str(state.get("execution_id"))
    for name in _SWAPPABLE:
        _set_step(settings, state, f"{name}_aside")
        staged_path = staging / name
        # Vectors from the old database must not be reused. Never install staged vectors.
        if name == "vectors":
            staged_path = staging / "vectors-not-used"
        swap_tree(data_root / name, staged_path, aside / name)
        _set_step(settings, state, f"{name}_installed")
    database = data_root / "database" / "mindmate.db"
    if _quick_check_file(database) != "ok":
        raise BackupBuildError("BACKUP_DATABASE_CORRUPT", "切换后的数据库未通过完整性检查。")
    violations = _foreign_key_violations(database)
    if violations:
        raise BackupBuildError("BACKUP_DATABASE_CORRUPT", "切换后的数据库未通过外键检查。")
    _set_step(settings, state, "reconciled")
    _reconcile_database(database)
    state["phase"] = "SUCCEEDED"
    state["switch_step"] = None
    state["index_outcome"] = "NEEDS_REBUILD"
    state["provider_reconfirm_required"] = True
    state["completed_at"] = _stamp(_now())
    state["error_code"] = None
    state["error_detail"] = None
    _save_state(settings, state)
    _set_frozen(settings, None)
    shutil.rmtree(staging, ignore_errors=True)
    archive.unlink(missing_ok=True)


def _foreign_key_violations(database_path: Path) -> list[Any]:
    conn = sqlite3.connect(database_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        return list(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()


def _rollback_partial(settings: Settings, state: dict[str, Any]) -> None:
    execution_id = str(state.get("execution_id") or "")
    aside = _aside_root(settings) / execution_id
    data_root = settings.resolved_data_dir
    rejected = _control_dir(settings) / "rejected" / execution_id
    for name in reversed(_SWAPPABLE):
        live = data_root / name
        saved = aside / name
        if saved.exists() and live.exists():
            rejected.mkdir(parents=True, exist_ok=True)
            target = rejected / name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            live.rename(target)
            saved.rename(live)
        elif saved.exists() and not live.exists():
            saved.rename(live)
    database = settings.database_path
    if database.is_file() and _quick_check_file(database) != "ok":
        raise BackupBuildError("RESTORE_ROLLBACK_FAILED", "回滚后的数据库未通过校验，已停止启动。")
    shutil.rmtree(_staging_root(settings) / execution_id, ignore_errors=True)
    state["phase"] = "ROLLED_BACK"
    state["switch_step"] = None
    state["error_code"] = state.get("error_code") or "RESTORE_ROLLED_BACK"
    state["error_detail"] = state.get("error_detail") or "切换未完成，已回到恢复前的数据。"
    _save_state(settings, state)
    _set_frozen(settings, None)


@_locked
def apply_pending_restore(settings: Settings) -> dict[str, Any] | None:
    """Run before the engine opens. Rollback partial swaps, or finish a confirmed restore."""
    state = load_restore_state(settings)
    if not state:
        return None
    if state.get("phase") == "SUCCEEDED":
        return state
    try:
        if state.get("switch_step"):
            _rollback_partial(settings, state)
            return load_restore_state(settings)
        if state.get("phase") in {"RESTART_REQUIRED", "APPLYING"}:
            try:
                _perform_switch(settings, state)
            except BackupBuildError as exc:
                fresh = load_restore_state(settings) or state
                if fresh.get("switch_step"):
                    fresh["error_code"] = exc.code
                    fresh["error_detail"] = _public_detail(exc.detail)
                    _save_state(settings, fresh)
                    _rollback_partial(settings, fresh)
                else:
                    fresh["phase"] = "ROLLED_BACK"
                    fresh["error_code"] = exc.code
                    fresh["error_detail"] = _public_detail(exc.detail)
                    _save_state(settings, fresh)
                    _set_frozen(settings, None)
            return load_restore_state(settings)
    except BackupBuildError as exc:
        raise RuntimeError(_public_detail(exc.detail)) from exc
    return state


def public_restore_status(settings: Settings) -> dict[str, Any]:
    state = load_restore_state(settings) or {}
    phase = str(state.get("phase") or "IDLE")
    if _expired(state):
        phase = "PRECHECK_EXPIRED"
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else None
    recovery_id = state.get("recovery_point_id")
    recovery_ok = False
    if isinstance(recovery_id, str) and _ID_RE.fullmatch(recovery_id):
        recovery_ok = (_recovery_root(settings) / recovery_id / "manifest.json").is_file()
    return {
        "restore_available": RESTORE_FLOW_AVAILABLE,
        "phase": phase,
        "precheck_id": state.get("precheck_id"),
        "execution_id": state.get("execution_id"),
        "upload_id": state.get("upload_id"),
        "expires_at": state.get("expires_at"),
        "archive_sha256": state.get("archive_sha256"),
        "summary": summary,
        "restart_required": phase == "RESTART_REQUIRED",
        "writes_frozen": restore_writes_frozen(settings),
        "error_code": state.get("error_code"),
        "error_detail": state.get("error_detail"),
        "index_outcome": state.get("index_outcome"),
        "provider_reconfirm_required": bool(state.get("provider_reconfirm_required")),
        "recovery_point_available": recovery_ok,
        "recovery_point_id": recovery_id if recovery_ok else None,
        "confirm_phrase": CONFIRM_PHRASE,
        "overwrite_scope": "整份本地业务数据将被覆盖，不与当前数据合并。",
    }


def list_recovery_points(settings: Settings) -> dict[str, Any]:
    root = _recovery_root(settings)
    items: list[dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir(), reverse=True):
            if not child.is_dir() or child.name.startswith("."):
                continue
            manifest_path = child / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(manifest, dict):
                continue
            items.append(
                {
                    "recovery_point_id": child.name,
                    "created_at": manifest.get("created_at"),
                    "copied_files": manifest.get("copied_files"),
                    "database_present": bool(manifest.get("database_present")),
                }
            )
            if len(items) >= 20:
                break
    return {"items": items}


__all__ = [
    "CONFIRM_PHRASE",
    "MAX_UPLOAD_BYTES",
    "RESTORE_FLOW_AVAILABLE",
    "RESTORE_RECONFIRM_KEY",
    "acknowledge_provider_reconfirm",
    "apply_pending_restore",
    "assert_database_unlocked",
    "cancel_restore",
    "confirm_restore",
    "inspect_restore_archive",
    "list_recovery_points",
    "precheck_upload",
    "public_restore_status",
    "quiesce_writers",
    "restore_provider_reconfirm_required",
    "restore_writes_frozen",
    "resume_writers",
    "save_uploaded_archive",
    "swap_tree",
]
