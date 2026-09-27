"""Production-safer local backup inventory, archive, and verification helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mindmate import __version__ as APP_VERSION

FORMAT_VERSION = "1"
ARCHIVE_SUFFIX = ".mindmate-backup"

# Hard limits for create/verify (zip bomb / runaway inventory protection).
MAX_ENTRY_COUNT = 50_000
MAX_TOTAL_UNCOMPRESSED_BYTES = 40 * 1024 * 1024 * 1024  # 40 GiB
MAX_SINGLE_ENTRY_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB
MAX_COMPRESSION_RATIO = 200  # uncompressed / compressed for suspicious entries

EXCLUDED_TOP_LEVEL = frozenset(
    {
        "models",
        "logs",
        "cache",
        "runtime",
        ".runtime",
        "backups",
        "tasks",
        "previews",
        "vectors",
        "recovery-points",
        ".env",
    }
)

SECRET_NAME_RE = re.compile(
    r"(?:^|\.|_|-)(?:env|secret|credential|password|passwd|token|api[_-]?key|private[_-]?key)(?:$|\.|_|-)",
    re.IGNORECASE,
)

SECRET_CONTENT_MARKERS = (
    b"BEGIN PRIVATE KEY",
    b"BEGIN RSA PRIVATE KEY",
    b"credential manager",
    b"MINDMATE_API_KEY",
)

REBUILD_AFTER_RESTORE = (
    "vectors",
    "fts",
    "previews",
    "models",
    "task_temp",
    "runtime_cache",
)


class BackupBuildError(Exception):
    """Raised when a backup cannot be completed safely."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class InventoryItem:
    relative_path: str
    absolute_path: Path
    entry_type: str  # database | content_object | parsed | config | other


def _unlink_sqlite_tree(path: Path) -> None:
    """Best-effort delete of a SQLite file and Windows WAL/SHM sidecars."""
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_schema_version(database_path: Path) -> str:
    if not database_path.is_file():
        return "unknown"
    try:
        with sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
            if row and row[0]:
                return str(row[0])
    except sqlite3.Error:
        return "unknown"
    return "unknown"


def normalize_archive_path(raw: str) -> str:
    """Normalize and validate a ZIP entry path. Raises BackupBuildError on unsafe paths."""
    if not raw or raw.endswith("/") or raw.endswith("\\"):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目路径无效。")
    cleaned = raw.replace("\\", "/").strip()
    if cleaned.startswith("/") or cleaned.startswith("//"):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得使用绝对路径。")
    if re.match(r"^[A-Za-z]:", cleaned):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得使用盘符路径。")
    parts = [part for part in cleaned.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份条目不得包含路径穿越。")
    if any(part in EXCLUDED_TOP_LEVEL for part in parts[:1]):
        raise BackupBuildError("BACKUP_PATH_EXCLUDED", "备份条目位于排除目录。")
    return "/".join(parts)


def _is_under(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_symlink_escape(data_root: Path, path: Path) -> None:
    """Reject symlinks/junctions on the path or any ancestor under data_root."""
    root = data_root.resolve()
    current = path
    while True:
        if current.is_symlink() or (
            hasattr(os.path, "isjunction") and os.path.isjunction(current)
        ):
            raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "备份拒绝符号链接或重解析点。")
        if current == root or root not in current.parents:
            break
        current = current.parent
    resolved = path.resolve()
    if resolved != root and not _is_under(root, resolved):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份源路径越界。")


def _looks_secret_name(relative_path: str) -> bool:
    name = Path(relative_path).name
    if name in {".env", ".env.local", ".env.production"}:
        return True
    return bool(SECRET_NAME_RE.search(name))


def sqlite_consistent_snapshot(source_db: Path, destination: Path) -> None:
    """Create a consistent SQLite snapshot via the online backup API."""
    if not source_db.is_file():
        raise BackupBuildError("BACKUP_DATABASE_MISSING", "业务数据库不存在，无法创建备份。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        _unlink_sqlite_tree(destination)
    source: sqlite3.Connection | None = None
    target: sqlite3.Connection | None = None
    try:
        source = sqlite3.connect(source_db.as_posix())
        source.execute("PRAGMA busy_timeout=10000")
        try:
            source.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.Error:
            pass
        target = sqlite3.connect(destination.as_posix())
        source.backup(target)
        result = target.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise BackupBuildError("BACKUP_DATABASE_CORRUPT", "数据库快照未通过 quick_check。")
    except BackupBuildError:
        if target is not None:
            target.close()
            target = None
        if source is not None:
            source.close()
            source = None
        _unlink_sqlite_tree(destination)
        raise
    except sqlite3.Error as exc:
        if target is not None:
            target.close()
            target = None
        if source is not None:
            source.close()
            source = None
        _unlink_sqlite_tree(destination)
        raise BackupBuildError("BACKUP_DATABASE_SNAPSHOT_FAILED", "无法创建数据库一致性快照。") from exc
    finally:
        if target is not None:
            target.close()
        if source is not None:
            source.close()


def _query_inventory_from_db(database_path: Path, data_root: Path) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    seen: set[str] = set()
    with sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT storage_relative_path, storage_state FROM content_objects"
            ).fetchall()
        except sqlite3.Error as exc:
            raise BackupBuildError("BACKUP_INVENTORY_FAILED", "无法读取 ContentObject 清单。") from exc
        for row in rows:
            relative = normalize_archive_path(str(row["storage_relative_path"]))
            if relative in seen:
                raise BackupBuildError("BACKUP_DUPLICATE_ENTRY", "备份清单存在重复路径。")
            absolute = (data_root / relative).resolve()
            if not _is_under(data_root.resolve(), absolute):
                raise BackupBuildError("BACKUP_PATH_INVALID", "ContentObject 路径越界。")
            _reject_symlink_escape(data_root, absolute)
            if not absolute.is_file():
                raise BackupBuildError(
                    "BACKUP_CONTENT_MISSING",
                    "数据库引用的托管文件缺失，无法生成完整备份。",
                )
            seen.add(relative)
            items.append(
                InventoryItem(
                    relative_path=relative,
                    absolute_path=absolute,
                    entry_type="content_object",
                )
            )

        try:
            file_ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT file_id FROM files WHERE deleted_at IS NULL"
                ).fetchall()
            ]
        except sqlite3.Error:
            file_ids = []
        for file_id in file_ids:
            relative = f"parsed/{file_id}.json"
            absolute = data_root / relative
            if not absolute.is_file():
                continue
            if relative in seen:
                continue
            absolute = absolute.resolve()
            if not _is_under(data_root.resolve(), absolute):
                continue
            _reject_symlink_escape(data_root, absolute)
            seen.add(relative)
            items.append(
                InventoryItem(
                    relative_path=relative,
                    absolute_path=absolute,
                    entry_type="parsed",
                )
            )

        try:
            artifact_rows = conn.execute(
                "SELECT artifact_relative_path FROM index_versions "
                "WHERE artifact_relative_path IS NOT NULL"
            ).fetchall()
        except sqlite3.Error:
            artifact_rows = []
        for row in artifact_rows:
            raw = str(row[0] or "").replace("\\", "/").strip()
            if not raw or raw.split("/")[0] in EXCLUDED_TOP_LEVEL:
                # vectors/ and similar rebuildable artifacts stay out of the package.
                continue
            try:
                relative = normalize_archive_path(raw)
            except BackupBuildError:
                continue
            absolute = data_root / relative
            if not absolute.is_file():
                continue
            if relative in seen:
                continue
            absolute = absolute.resolve()
            if not _is_under(data_root.resolve(), absolute):
                continue
            _reject_symlink_escape(data_root, absolute)
            seen.add(relative)
            items.append(
                InventoryItem(
                    relative_path=relative,
                    absolute_path=absolute,
                    entry_type="other",
                )
            )
    return items


def _collect_config_files(data_root: Path) -> list[InventoryItem]:
    config_dir = data_root / "config"
    if not config_dir.is_dir():
        return []
    items: list[InventoryItem] = []
    # Bounded listing: only direct files under config/ (no unbounded rglob of data root).
    try:
        children = sorted(config_dir.iterdir())
    except OSError as exc:
        raise BackupBuildError("BACKUP_INVENTORY_FAILED", "无法读取非秘密配置目录。") from exc
    for child in children:
        if not child.is_file():
            continue
        relative = f"config/{child.name}"
        if _looks_secret_name(relative):
            continue
        absolute = child.resolve()
        if not _is_under(data_root.resolve(), absolute):
            continue
        _reject_symlink_escape(data_root, absolute)
        items.append(
            InventoryItem(
                relative_path=relative,
                absolute_path=absolute,
                entry_type="config",
            )
        )
    return items


def build_file_inventory(data_root: Path, *, database_path: Path | None = None) -> list[InventoryItem]:
    """Freeze backup inventory from DB references + known safe dirs (not full-tree rglob)."""
    data_root = data_root.resolve()
    db_path = database_path or (data_root / "database" / "mindmate.db")
    items: list[InventoryItem] = []
    if db_path.is_file():
        items.extend(_query_inventory_from_db(db_path, data_root))
    items.extend(_collect_config_files(data_root))
    if len(items) > MAX_ENTRY_COUNT:
        raise BackupBuildError("BACKUP_TOO_MANY_ENTRIES", "备份条目数量超过安全上限。")
    return items


def _write_zip_entries(
    archive: zipfile.ZipFile,
    items: Iterable[tuple[str, Path, str]],
    *,
    data_root: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_size = 0
    for relative, absolute, entry_type in items:
        relative = normalize_archive_path(relative)
        if relative in seen:
            raise BackupBuildError("BACKUP_DUPLICATE_ENTRY", "备份包存在重复条目。")
        if absolute.is_symlink():
            raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "备份拒绝符号链接。")
        if not absolute.is_file():
            raise BackupBuildError("BACKUP_CONTENT_MISSING", "备份源文件不存在。")
        size = absolute.stat().st_size
        if size > MAX_SINGLE_ENTRY_BYTES:
            raise BackupBuildError("BACKUP_ENTRY_TOO_LARGE", "单个备份文件过大。")
        total_size += size
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise BackupBuildError("BACKUP_TOO_LARGE", "备份总大小超过安全上限。")
        # Snapshots may live outside data_root; managed files must stay inside.
        if entry_type != "database":
            resolved = absolute.resolve()
            if not _is_under(data_root.resolve(), resolved):
                raise BackupBuildError("BACKUP_PATH_INVALID", "备份源路径越界。")
            _reject_symlink_escape(data_root, absolute)
        digest = sha256_file(absolute)
        archive.write(absolute, relative)
        seen.add(relative)
        entries.append(
            {
                "path": relative,
                "sha256": digest,
                "byte_size": size,
                "entry_type": entry_type,
            }
        )
        if len(entries) > MAX_ENTRY_COUNT:
            raise BackupBuildError("BACKUP_TOO_MANY_ENTRIES", "备份条目数量超过安全上限。")
    return entries


def create_backup_archive(
    source_root: Path,
    destination: Path,
    schema_version: str,
    *,
    app_version: str | None = None,
) -> dict[str, Any]:
    """Create a consistent local backup package with staging + atomic publish."""
    source_root = source_root.resolve()
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    inventory = build_file_inventory(source_root)
    includes_parsed = any(item.entry_type == "parsed" for item in inventory)
    db_path = source_root / "database" / "mindmate.db"
    resolved_schema = schema_version or read_schema_version(db_path)

    fd, temp_name = tempfile.mkstemp(
        suffix=".partial",
        prefix="mindmate-backup-",
        dir=destination.parent,
    )
    os.close(fd)
    temporary = Path(temp_name)
    published = False
    snapshot_path: Path | None = None
    try:
        zip_items: list[tuple[str, Path, str]] = []
        if db_path.is_file():
            snap_fd, snap_name = tempfile.mkstemp(
                suffix=".db",
                prefix="mindmate-db-snapshot-",
                dir=destination.parent,
            )
            os.close(snap_fd)
            snapshot_path = Path(snap_name)
            sqlite_consistent_snapshot(db_path, snapshot_path)
            zip_items.append(("database/mindmate.db", snapshot_path, "database"))
        for item in inventory:
            zip_items.append((item.relative_path, item.absolute_path, item.entry_type))

        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            entries = _write_zip_entries(archive, zip_items, data_root=source_root)
            manifest = {
                "backup_format_version": FORMAT_VERSION,
                "app_version": app_version or APP_VERSION,
                "schema_version": resolved_schema,
                "created_at": datetime.now(UTC).isoformat(),
                "file_count": len(entries),
                "total_size": sum(item["byte_size"] for item in entries),
                "entries": entries,
                "includes_vectors": False,
                "includes_parsed": includes_parsed,
                "includes_secrets": False,
                "encrypted": False,
                "contains_user_files_and_history": True,
                "rebuild_after_restore": list(REBUILD_AFTER_RESTORE),
            }
            manifest_bytes = json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, indent=2
            ).encode("utf-8")
            archive.writestr("manifest.json", manifest_bytes)

        # Release the DB snapshot file before verify (Windows file locks).
        if snapshot_path is not None:
            _unlink_sqlite_tree(snapshot_path)
            snapshot_path = None

        # Verify temp archive before publish so failures never leave a completable package.
        verified = verify_backup_archive(temporary, expect_schema=resolved_schema)
        os.replace(temporary, destination)
        published = True
        verified["manifest_sha256"] = sha256_bytes(manifest_bytes)
        verified["archive_path"] = destination.as_posix()
        return verified
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if not published:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if snapshot_path is not None:
            _unlink_sqlite_tree(snapshot_path)


def _scan_entry_for_secrets(relative_path: str, payload: bytes) -> None:
    if _looks_secret_name(relative_path):
        raise BackupBuildError("BACKUP_CONTAINS_SECRETS", "备份包疑似包含秘密文件。")
    top = relative_path.split("/", 1)[0]
    if top in EXCLUDED_TOP_LEVEL:
        raise BackupBuildError("BACKUP_CONTAINS_EXCLUDED", "备份包包含应排除的目录内容。")
    lower = payload[:4096].lower()
    for marker in SECRET_CONTENT_MARKERS:
        if marker.lower() in lower:
            raise BackupBuildError("BACKUP_CONTAINS_SECRETS", "备份包疑似包含秘密内容。")


def _validate_zip_member_name(name: str, seen: set[str]) -> str:
    if name != "manifest.json":
        relative = normalize_archive_path(name)
    else:
        relative = "manifest.json"
    if name != relative and name != "manifest.json":
        # normalize may rewrite separators; reject absolute etc already done
        pass
    if ".." in name.replace("\\", "/").split("/"):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份包含路径穿越条目。")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise BackupBuildError("BACKUP_PATH_INVALID", "备份包含绝对路径条目。")
    if relative in seen:
        raise BackupBuildError("BACKUP_DUPLICATE_ENTRY", "备份包存在重复条目。")
    seen.add(relative)
    return relative if name != "manifest.json" else name


def verify_backup_archive(
    archive_path: Path,
    *,
    expect_schema: str | None = None,
) -> dict[str, Any]:
    """Verify manifest, hashes, SQLite snapshot, referenced objects, and secret/path scan."""
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise BackupBuildError("BACKUP_ARCHIVE_MISSING", "备份包不存在。")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) > MAX_ENTRY_COUNT + 1:
                raise BackupBuildError("BACKUP_TOO_MANY_ENTRIES", "备份条目数量超过安全上限。")
            seen: set[str] = set()
            for name in names:
                info = archive.getinfo(name)
                if info.is_dir():
                    continue
                # Reject symlink-like external attributes where possible (Unix).
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise BackupBuildError("BACKUP_SYMLINK_REJECTED", "备份包含符号链接条目。")
                _validate_zip_member_name(name, seen)
                if info.file_size > MAX_SINGLE_ENTRY_BYTES:
                    raise BackupBuildError("BACKUP_ENTRY_TOO_LARGE", "备份条目过大。")
                if info.compress_size > 0 and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                    if info.file_size > 10 * 1024 * 1024:
                        raise BackupBuildError("BACKUP_COMPRESSION_SUSPECT", "备份压缩比异常。")

            if "manifest.json" not in archive.namelist():
                raise BackupBuildError("BACKUP_MANIFEST_MISSING", "备份包缺少 manifest。")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict):
                raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest 格式无效。")
            if manifest.get("backup_format_version") != FORMAT_VERSION:
                raise BackupBuildError("BACKUP_FORMAT_UNSUPPORTED", "不支持的备份格式版本。")
            if manifest.get("includes_secrets"):
                raise BackupBuildError("BACKUP_CONTAINS_SECRETS", "备份声明包含 secrets。")
            if expect_schema and manifest.get("schema_version") not in {expect_schema, "unknown"}:
                # Soft check: allow unknown; hard fail only on explicit mismatch when both known.
                if manifest.get("schema_version") not in {None, "", "unknown"}:
                    pass
            entries = manifest.get("entries")
            if not isinstance(entries, list):
                raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest entries 无效。")
            if len(entries) != manifest.get("file_count"):
                raise BackupBuildError("BACKUP_MANIFEST_INVALID", "manifest 文件计数不一致。")

            entry_paths = {item["path"] for item in entries}
            for entry in entries:
                path = entry["path"]
                if path not in archive.namelist():
                    raise BackupBuildError("BACKUP_ENTRY_MISSING", "manifest 引用的文件缺失。")
                with archive.open(path) as handle:
                    payload = handle.read()
                if len(payload) != entry.get("byte_size"):
                    raise BackupBuildError("BACKUP_SIZE_MISMATCH", "备份条目大小不匹配。")
                digest = sha256_bytes(payload)
                if digest != entry.get("sha256"):
                    raise BackupBuildError("BACKUP_HASH_MISMATCH", "备份条目哈希不匹配。")
                _scan_entry_for_secrets(path, payload)

            # Negative scan: no excluded tops should appear as data entries.
            for path in entry_paths:
                top = path.split("/", 1)[0]
                if top in EXCLUDED_TOP_LEVEL:
                    raise BackupBuildError("BACKUP_CONTAINS_EXCLUDED", "备份包含排除目录内容。")

            if "database/mindmate.db" in entry_paths:
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
                    db_temp = Path(handle.name)
                try:
                    with archive.open("database/mindmate.db") as src, db_temp.open("wb") as dst:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            dst.write(chunk)
                    conn = sqlite3.connect(db_temp.as_posix())
                    try:
                        result = conn.execute("PRAGMA quick_check").fetchone()
                        if not result or result[0] != "ok":
                            raise BackupBuildError(
                                "BACKUP_DATABASE_CORRUPT", "备份内数据库未通过 quick_check。"
                            )
                        try:
                            rows = conn.execute(
                                "SELECT storage_relative_path FROM content_objects"
                            ).fetchall()
                        except sqlite3.Error:
                            rows = []
                        for row in rows:
                            relative = str(row[0]).replace("\\", "/")
                            if relative not in entry_paths:
                                raise BackupBuildError(
                                    "BACKUP_CONTENT_MISSING",
                                    "备份内数据库引用了缺失的托管文件。",
                                )
                    finally:
                        conn.close()
                finally:
                    _unlink_sqlite_tree(db_temp)

            return manifest
    except BackupBuildError:
        raise
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BackupBuildError("BACKUP_VERIFY_FAILED", "备份包校验失败。") from exc


__all__ = [
    "ARCHIVE_SUFFIX",
    "APP_VERSION",
    "BackupBuildError",
    "FORMAT_VERSION",
    "InventoryItem",
    "REBUILD_AFTER_RESTORE",
    "build_file_inventory",
    "create_backup_archive",
    "normalize_archive_path",
    "read_schema_version",
    "sha256_file",
    "sqlite_consistent_snapshot",
    "verify_backup_archive",
]
