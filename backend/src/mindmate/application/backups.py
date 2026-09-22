from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FORMAT_VERSION = "1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(source_root: Path, destination: Path, schema_version: str) -> dict[str, Any]:
    source_root = source_root.resolve()
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".partial", dir=destination.parent
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_root.rglob("*")):
                if not path.is_file() or any(
                    part in {".runtime", "runtime", "logs", "cache"}
                    for part in path.relative_to(source_root).parts
                ):
                    continue
                relative = path.relative_to(source_root).as_posix()
                digest = sha256_file(path)
                archive.write(path, relative)
                entries.append(
                    {"path": relative, "sha256": digest, "byte_size": path.stat().st_size}
                )
            manifest = {
                "backup_format_version": FORMAT_VERSION,
                "schema_version": schema_version,
                "created_at": datetime.now(UTC).isoformat(),
                "file_count": len(entries),
                "total_size": sum(item["byte_size"] for item in entries),
                "entries": entries,
                "includes_vectors": False,
                "includes_secrets": False,
            }
            manifest_bytes = json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, indent=2
            ).encode()
            archive.writestr("manifest.json", manifest_bytes)
        os.replace(temporary, destination)
        manifest["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        return manifest
    finally:
        temporary.unlink(missing_ok=True)


def verify_backup(archive_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("includes_secrets"):
            raise ValueError("backup contains secrets")
        for entry in manifest["entries"]:
            with archive.open(entry["path"]) as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            if digest != entry["sha256"]:
                raise ValueError(f"backup hash mismatch: {entry['path']}")
        return manifest
