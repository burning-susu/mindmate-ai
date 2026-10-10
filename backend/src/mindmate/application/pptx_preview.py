from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pypdf import PdfReader

from mindmate.application.files import validate_managed_content_path
from mindmate.application.resource_limits import JobObjectError, ManagedJobObject
from mindmate.config import Settings

PPTX_PREVIEW_CACHE_REVISION = "libreoffice-pdf-v1"
MAX_PREVIEW_PDF_PAGES = 2_000
MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS = 180
_RENDER_SLOT = threading.BoundedSemaphore(1)


class PptxPreviewError(RuntimeError):
    def __init__(self, code: str, detail: str, status: int) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def _candidate_executables(root: Path) -> tuple[Path, ...]:
    program = root / "program"
    return program / "soffice.com", program / "soffice.exe"


def find_libreoffice(settings: Settings) -> Path | None:
    configured = settings.libreoffice_path
    if configured is not None:
        candidates = (configured,) if configured.is_file() else _candidate_executables(configured)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

    roots = [Path(sys.executable).resolve().parent / "runtime" / "libreoffice"]
    package_root = getattr(sys, "_MEIPASS", None)
    if package_root:
        roots.append(Path(package_root) / "runtime" / "libreoffice")
    repository_root = Path(__file__).resolve().parents[4]
    roots.extend(
        (
            repository_root / "runtime" / "libreoffice",
            repository_root / "build" / "runtime" / "libreoffice",
        )
    )
    for root in roots:
        for candidate in _candidate_executables(root):
            if candidate.is_file():
                return candidate.resolve()

    for name in ("soffice.com", "soffice.exe", "soffice"):
        located = shutil.which(name)
        if located:
            return Path(located).resolve()

    program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    for base in filter(None, program_files):
        for candidate in _candidate_executables(Path(base) / "LibreOffice"):
            if candidate.is_file():
                return candidate.resolve()
    return None


@contextmanager
def _cache_lock(path: Path, timeout: float) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise PptxPreviewError(
                        "PPTX_PREVIEW_BUSY", "幻灯片预览正在生成，请稍后重试。", 503
                    ) from None
                time.sleep(0.05)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextmanager
def _renderer_slot(timeout: float) -> Iterator[None]:
    if not _RENDER_SLOT.acquire(timeout=timeout):
        raise PptxPreviewError(
            "PPTX_PREVIEW_BUSY", "另一个幻灯片预览正在转换，请稍后重试。", 503
        ) from None
    try:
        yield
    finally:
        _RENDER_SLOT.release()


def _pdf_page_count(path: Path, max_bytes: int) -> int | None:
    try:
        if not path.is_file() or path.stat().st_size > max_bytes:
            return None
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                return None
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            return None
        count = len(reader.pages)
        return count if 1 <= count <= MAX_PREVIEW_PDF_PAGES else None
    except Exception:
        return None


def _child_environment(workdir: Path, executable: Path) -> dict[str, str]:
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "PATH", "USERPROFILE", "APPDATA", "LOCALAPPDATA")
        if os.environ.get(key)
    }
    executable_dir = str(executable.parent)
    env["PATH"] = os.pathsep.join(filter(None, (executable_dir, env.get("PATH", ""))))
    env["TEMP"] = str(workdir)
    env["TMP"] = str(workdir)
    return env


def _render_to_cache(
    source: Path,
    executable: Path,
    cache_path: Path,
    settings: Settings,
) -> Path:
    if not source.is_file():
        raise PptxPreviewError("FILE_CONTENT_MISSING", "PPTX 原文件不可用。", 409)
    if source.stat().st_size > 50 * 1024 * 1024:
        raise PptxPreviewError("PPTX_PREVIEW_INPUT_TOO_LARGE", "PPTX 文件超过预览限制。", 413)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="mindmate-pptx-", dir=cache_path.parent) as value:
            workdir = Path(value)
            source_copy = workdir / "source.pptx"
            shutil.copyfile(source, source_copy)
            profile = workdir / "profile"
            profile.mkdir()
            profile_url = profile.resolve().as_uri()
            command = [
                str(executable),
                "--headless",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                "--norestore",
                f"-env:UserInstallation={profile_url}",
                "--convert-to",
                "pdf:impress_pdf_Export",
                "--outdir",
                str(workdir),
                str(source_copy),
            ]
            try:
                job = ManagedJobObject.create(settings.pptx_preview_memory_limit_bytes)
            except JobObjectError as exc:
                raise PptxPreviewError(
                    "PPTX_PREVIEW_LIMIT_SETUP_FAILED", "无法建立受限的幻灯片转换进程。", 503
                ) from exc
            try:
                process: subprocess.Popen[bytes] | None = None
                try:
                    process = subprocess.Popen(
                        command,
                        cwd=workdir,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=_child_environment(workdir, executable),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    job.assign(process)
                except (OSError, JobObjectError) as exc:
                    if process is not None:
                        process.kill()
                        process.wait()
                    raise PptxPreviewError(
                        "PPTX_RENDERER_START_FAILED", "无法安全启动 LibreOffice 转换器。", 503
                    ) from exc
                assert process is not None
                try:
                    return_code = process.wait(timeout=settings.pptx_preview_timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.wait()
                    raise PptxPreviewError(
                        "PPTX_RENDER_TIMEOUT", "幻灯片转换超时，请稍后重试。", 504
                    ) from exc
            finally:
                job.close()

            generated = workdir / "source.pdf"
            if return_code != 0:
                raise PptxPreviewError(
                    "PPTX_RENDER_FAILED", "LibreOffice 无法生成幻灯片预览。", 422
                )
            if _pdf_page_count(generated, settings.pptx_preview_max_bytes) is None:
                raise PptxPreviewError(
                    "PPTX_RENDER_OUTPUT_INVALID", "生成的幻灯片预览无效或超过限制。", 422
                )
            temporary_cache = cache_path.with_suffix(f".{os.getpid()}.partial")
            shutil.copyfile(generated, temporary_cache)
            os.replace(temporary_cache, cache_path)
    except PptxPreviewError:
        raise
    except OSError as exc:
        raise PptxPreviewError("PPTX_RENDER_FAILED", "无法写入幻灯片预览缓存。", 500) from exc
    return cache_path


def get_or_create_pptx_preview(
    source: Path, content_hash: str, settings: Settings
) -> tuple[Path, int, bool]:
    if len(content_hash) != 64 or any(character not in "0123456789abcdef" for character in content_hash):
        raise PptxPreviewError("PPTX_PREVIEW_CACHE_KEY_INVALID", "PPTX 预览缓存键无效。", 500)

    cache_key = hashlib.sha256(
        f"{PPTX_PREVIEW_CACHE_REVISION}:{content_hash}".encode("ascii")
    ).hexdigest()
    relative = f"previews/pptx/{cache_key}.pdf"
    cache_path = validate_managed_content_path(settings, relative)
    lock_path = validate_managed_content_path(settings, "previews/pptx/renderer.lock")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    page_count = _pdf_page_count(cache_path, settings.pptx_preview_max_bytes)
    if page_count is not None:
        return cache_path, page_count, True
    cache_path.unlink(missing_ok=True)

    executable = find_libreoffice(settings)
    if executable is None:
        raise PptxPreviewError(
            "PPTX_RENDERER_UNAVAILABLE",
            "缺少本地幻灯片渲染组件，无法生成 PPTX 版式预览。",
            503,
        )

    with _renderer_slot(MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS):
        with _cache_lock(lock_path, MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS):
            page_count = _pdf_page_count(cache_path, settings.pptx_preview_max_bytes)
            if page_count is not None:
                return cache_path, page_count, True
            cache_path.unlink(missing_ok=True)
            _render_to_cache(source, executable, cache_path, settings)
            page_count = _pdf_page_count(cache_path, settings.pptx_preview_max_bytes)
            if page_count is None:
                cache_path.unlink(missing_ok=True)
                raise PptxPreviewError(
                    "PPTX_RENDER_OUTPUT_INVALID", "生成的幻灯片预览无效或超过限制。", 422
                )
            return cache_path, page_count, False
