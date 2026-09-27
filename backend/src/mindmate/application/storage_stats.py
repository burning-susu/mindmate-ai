from __future__ import annotations

from pathlib import Path
from typing import Any

from mindmate.config import Settings

CATEGORY_DIRS: tuple[tuple[str, str], ...] = (
    ("database", "数据库"),
    ("objects", "托管文件"),
    ("parsed", "解析产物"),
    ("vectors", "向量索引"),
    ("previews", "预览缓存"),
    ("tasks", "任务临时"),
    ("backups", "本地备份"),
    ("models", "本地模型"),
    ("logs", "日志"),
    ("cache", "缓存"),
    ("config", "非秘密配置"),
    ("runtime", "运行时"),
)


def _dir_size_bytes(path: Path) -> int | None:
    if not path.exists():
        return 0
    if not path.is_dir():
        return None
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                if child.is_file() and not child.is_symlink():
                    total += child.stat().st_size
            except OSError:
                continue
    except OSError:
        return None
    return total


def display_data_dir(settings: Settings) -> str:
    path = settings.resolved_data_dir
    home = Path.home()
    try:
        relative = path.relative_to(home)
        return str(Path("%USERPROFILE%") / relative)
    except ValueError:
        local_app = home / "AppData" / "Local"
        try:
            relative = path.relative_to(local_app)
            return str(Path("%LOCALAPPDATA%") / relative)
        except ValueError:
            return path.name


def storage_overview(settings: Settings) -> dict[str, Any]:
    root = settings.resolved_data_dir
    categories: list[dict[str, Any]] = []
    readable = True
    total: int | None = 0
    for dirname, label in CATEGORY_DIRS:
        size = _dir_size_bytes(root / dirname)
        if size is None:
            readable = False
            categories.append(
                {
                    "key": dirname,
                    "label": label,
                    "byte_size": None,
                    "available": False,
                    "message": "暂时无法读取",
                }
            )
            total = None
        else:
            categories.append(
                {
                    "key": dirname,
                    "label": label,
                    "byte_size": size,
                    "available": True,
                    "message": None,
                }
            )
            if total is not None:
                total += size
    return {
        "data_dir_configured": bool(settings.data_dir) or root.exists(),
        "data_dir_display": display_data_dir(settings),
        "database": "sqlite",
        "writable": root.exists() and os_access_writable(root),
        "categories": categories,
        "total_byte_size": total,
        "readable": readable,
        "message": None if readable else "部分目录暂时无法读取，未显示为 0。",
    }


def os_access_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".mindmate-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


__all__ = ["display_data_dir", "storage_overview"]
