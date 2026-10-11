from __future__ import annotations

import hashlib
import os
import posixpath
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader

from mindmate.application.files import validate_managed_content_path
from mindmate.application.resource_limits import JobObjectError, ManagedJobObject
from mindmate.config import Settings

OFFICE_PREVIEW_CACHE_REVISION = "libreoffice-office-pdf-v1"
MAX_PREVIEW_PDF_PAGES = 2_000
MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS = 180
MAX_XLSX_HTML_BYTES = 20 * 1024 * 1024
XLSX_PREVIEW_STYLE = """
<style id="mindmate-xlsx-table-style">
html,body{background:#fff!important;color:#17232a!important}
body{padding:12px!important}
table{border-collapse:collapse!important;border-spacing:0!important;background:#fff!important}
td,th{border:1px solid #8797a0!important;padding:5px 8px!important;vertical-align:top!important}
tr:first-child>td,tr:first-child>th{background:#e9f1f3!important;font-weight:700!important;border-bottom:2px solid #637781!important}
</style>
""".strip()
_RENDER_SLOT = threading.BoundedSemaphore(1)


class OfficePreviewError(RuntimeError):
    def __init__(self, code: str, detail: str, status: int) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


class _SpreadsheetHTMLGuard(HTMLParser):
    blocked_tags = {"script", "iframe", "object", "embed", "form", "input", "video", "audio"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self.blocked_tags:
            raise ValueError("Spreadsheet HTML contains an active element.")
        for name, value in attrs:
            if name.casefold().startswith("on"):
                raise ValueError("Spreadsheet HTML contains an event attribute.")
            if name.casefold() in {"src", "srcset"} and value and not value.strip().casefold().startswith("data:"):
                raise ValueError("Spreadsheet HTML references an external resource.")
            if name.casefold() == "http-equiv" and (value or "").casefold() == "refresh":
                raise ValueError("Spreadsheet HTML contains a refresh directive.")


PptxPreviewError = OfficePreviewError


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
                    raise OfficePreviewError(
                        "OFFICE_PREVIEW_BUSY", "文档版式预览正在生成，请稍后重试。", 503
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
        raise OfficePreviewError(
            "OFFICE_PREVIEW_BUSY", "另一个文档正在转换，请稍后重试。", 503
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
    document_type: str,
) -> Path:
    if not source.is_file():
        raise OfficePreviewError("FILE_CONTENT_MISSING", "Office 原文件不可用。", 409)
    if source.stat().st_size > 50 * 1024 * 1024:
        raise OfficePreviewError("OFFICE_PREVIEW_INPUT_TOO_LARGE", "Office 文件超过预览限制。", 413)

    export_filters = {
        "DOCX": "writer_pdf_Export",
        "PPT": "impress_pdf_Export",
        "PPTX": "impress_pdf_Export",
        "XLSX": "calc_pdf_Export",
    }
    extensions = {"DOCX": ".docx", "PPT": ".ppt", "PPTX": ".pptx", "XLSX": ".xlsx"}
    export_filter = export_filters.get(document_type)
    extension = extensions.get(document_type)
    if export_filter is None or extension is None:
        raise OfficePreviewError(
            "OFFICE_PREVIEW_TYPE_UNSUPPORTED", "Office 文件类型不受支持。", 415
        )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="mindmate-pptx-", dir=cache_path.parent) as value:
            workdir = Path(value)
            source_copy = workdir / f"source{extension}"
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
                f"pdf:{export_filter}",
                "--outdir",
                str(workdir),
                str(source_copy),
            ]
            try:
                job = ManagedJobObject.create(settings.pptx_preview_memory_limit_bytes)
            except JobObjectError as exc:
                raise OfficePreviewError(
                    "OFFICE_PREVIEW_LIMIT_SETUP_FAILED", "无法建立受限的文档转换进程。", 503
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
                    raise OfficePreviewError(
                        "OFFICE_RENDERER_START_FAILED", "无法安全启动 LibreOffice 转换器。", 503
                    ) from exc
                assert process is not None
                try:
                    return_code = process.wait(timeout=settings.pptx_preview_timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.wait()
                    raise OfficePreviewError(
                        "OFFICE_RENDER_TIMEOUT", "文档转换超时，请稍后重试。", 504
                    ) from exc
            finally:
                job.close()

            generated = workdir / "source.pdf"
            if return_code != 0:
                raise OfficePreviewError(
                    "OFFICE_RENDER_FAILED", "LibreOffice 无法生成文档预览。", 422
                )
            if _pdf_page_count(generated, settings.pptx_preview_max_bytes) is None:
                raise OfficePreviewError(
                    "OFFICE_RENDER_OUTPUT_INVALID", "生成的文档预览无效或超过限制。", 422
                )
            temporary_cache = cache_path.with_suffix(f".{os.getpid()}.partial")
            shutil.copyfile(generated, temporary_cache)
            os.replace(temporary_cache, cache_path)
    except OfficePreviewError:
        raise
    except OSError as exc:
        raise OfficePreviewError("OFFICE_RENDER_FAILED", "无法写入文档预览缓存。", 500) from exc
    return cache_path


def get_or_create_office_preview(
    source: Path, content_hash: str, document_type: str, settings: Settings
) -> tuple[Path, int, bool]:
    if document_type not in {"DOCX", "PPT", "PPTX", "XLSX"}:
        raise OfficePreviewError(
            "OFFICE_PREVIEW_TYPE_UNSUPPORTED", "Office 文件类型不受支持。", 415
        )
    if len(content_hash) != 64 or any(
        character not in "0123456789abcdef" for character in content_hash
    ):
        raise OfficePreviewError("OFFICE_PREVIEW_CACHE_KEY_INVALID", "Office 预览缓存键无效。", 500)

    cache_key = hashlib.sha256(
        f"{OFFICE_PREVIEW_CACHE_REVISION}:{document_type}:{content_hash}".encode("ascii")
    ).hexdigest()
    relative = f"previews/office/{document_type.lower()}/{cache_key}.pdf"
    cache_path = validate_managed_content_path(settings, relative)
    lock_path = validate_managed_content_path(settings, "previews/office/renderer.lock")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    page_count = _pdf_page_count(cache_path, settings.pptx_preview_max_bytes)
    if page_count is not None:
        return cache_path, page_count, True
    cache_path.unlink(missing_ok=True)

    executable = find_libreoffice(settings)
    if executable is None:
        raise OfficePreviewError(
            "OFFICE_RENDERER_UNAVAILABLE",
            "缺少本地 LibreOffice 运行时，无法生成 Office 版式预览。",
            503,
        )

    with _renderer_slot(MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS):
        with _cache_lock(lock_path, MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS):
            page_count = _pdf_page_count(cache_path, settings.pptx_preview_max_bytes)
            if page_count is not None:
                return cache_path, page_count, True
            cache_path.unlink(missing_ok=True)
            _render_to_cache(source, executable, cache_path, settings, document_type)
            page_count = _pdf_page_count(cache_path, settings.pptx_preview_max_bytes)
            if page_count is None:
                cache_path.unlink(missing_ok=True)
                raise OfficePreviewError(
                    "OFFICE_RENDER_OUTPUT_INVALID", "生成的文档预览无效或超过限制。", 422
                )
            return cache_path, page_count, False


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _select_xlsx_sheet(source: Path, sheet_index: int) -> None:
    temporary = source.with_name("selected-sheet.xlsx")
    workbook_path = "xl/workbook.xml"
    relationships_path = "xl/_rels/workbook.xml.rels"
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ET.register_namespace("", namespace)
    ET.register_namespace("r", relationship_namespace)

    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if workbook_path not in names or relationships_path not in names:
                raise OfficePreviewError("XLSX_WORKBOOK_INVALID", "Excel 工作簿结构无效。", 422)
            workbook = ET.fromstring(archive.read(workbook_path))
            relations_root = ET.fromstring(archive.read(relationships_path))
            relations = {
                item.attrib.get("Id", ""): item.attrib.get("Target", "")
                for item in relations_root
                if _local_name(item.tag) == "Relationship"
                and item.attrib.get("TargetMode") != "External"
            }
            sheets = [item for item in workbook.iter() if _local_name(item.tag) == "sheet"]
            if sheet_index < 0 or sheet_index >= len(sheets):
                raise OfficePreviewError("XLSX_PREVIEW_SHEET_NOT_FOUND", "工作表不存在。", 404)
            views = [item for item in workbook.iter() if _local_name(item.tag) == "workbookView"]
            if not views:
                book_views = workbook.find(f"{{{namespace}}}bookViews")
                if book_views is None:
                    book_views = ET.Element(f"{{{namespace}}}bookViews")
                    sheets_element = workbook.find(f"{{{namespace}}}sheets")
                    insert_at = list(workbook).index(sheets_element) if sheets_element is not None else len(workbook)
                    workbook.insert(insert_at, book_views)
                views = [ET.SubElement(book_views, f"{{{namespace}}}workbookView")]
            for view in views:
                view.set("activeTab", str(sheet_index))

            selected_target: str | None = None
            for index, sheet in enumerate(sheets):
                relation_id = next(
                    (value for key, value in sheet.attrib.items() if key.endswith("}id")), ""
                )
                target = relations.get(relation_id, "")
                if target.startswith("/"):
                    internal = posixpath.normpath(target.lstrip("/"))
                else:
                    internal = posixpath.normpath(posixpath.join("xl", target))
                if not internal.startswith("xl/") or ".." in internal.split("/"):
                    raise OfficePreviewError("XLSX_WORKBOOK_INVALID", "工作表路径无效。", 422)
                if index == sheet_index:
                    selected_target = internal
            if selected_target is None or selected_target not in names:
                raise OfficePreviewError("XLSX_PREVIEW_SHEET_NOT_FOUND", "工作表内容不可用。", 404)

            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for info in infos:
                    data = archive.read(info.filename)
                    if info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml"):
                        root = ET.fromstring(data)
                        sheet_views = [item for item in root.iter() if _local_name(item.tag) == "sheetView"]
                        for view in sheet_views:
                            if info.filename == selected_target:
                                view.set("tabSelected", "1")
                            else:
                                view.attrib.pop("tabSelected", None)
                        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                    elif info.filename == workbook_path:
                        data = ET.tostring(workbook, encoding="utf-8", xml_declaration=True)
                    output.writestr(info, data)
        os.replace(temporary, source)
    except OfficePreviewError:
        raise
    except (OSError, zipfile.BadZipFile, ET.ParseError, RuntimeError) as exc:
        temporary.unlink(missing_ok=True)
        raise OfficePreviewError("XLSX_WORKBOOK_INVALID", "Excel 工作簿结构无效。", 422) from exc


def _render_xlsx_html(
    source: Path, executable: Path, cache_path: Path, settings: Settings, sheet_index: int
) -> Path:
    if not source.is_file():
        raise OfficePreviewError("FILE_CONTENT_MISSING", "Office 原文件不可用。", 409)
    if source.stat().st_size > 50 * 1024 * 1024:
        raise OfficePreviewError("OFFICE_PREVIEW_INPUT_TOO_LARGE", "Office 文件超过预览限制。", 413)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="mindmate-xlsx-", dir=cache_path.parent) as value:
            workdir = Path(value)
            source_copy = workdir / "source.xlsx"
            shutil.copyfile(source, source_copy)
            _select_xlsx_sheet(source_copy, sheet_index)
            profile = workdir / "profile"
            profile.mkdir()
            command = [
                str(executable), "--headless", "--nologo", "--nodefault", "--nolockcheck",
                "--norestore", f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--convert-to", "html", "--outdir", str(workdir), str(source_copy),
            ]
            try:
                job = ManagedJobObject.create(settings.pptx_preview_memory_limit_bytes)
            except JobObjectError as exc:
                raise OfficePreviewError(
                    "OFFICE_PREVIEW_LIMIT_SETUP_FAILED", "无法建立受限的文档转换进程。", 503
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
                    raise OfficePreviewError(
                        "OFFICE_RENDERER_START_FAILED", "无法安全启动 LibreOffice 转换器。", 503
                    ) from exc
                assert process is not None
                try:
                    return_code = process.wait(timeout=settings.pptx_preview_timeout_seconds)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.wait()
                    raise OfficePreviewError(
                        "OFFICE_RENDER_TIMEOUT", "文档转换超时，请稍后重试。", 504
                    ) from exc
            finally:
                job.close()

            generated = workdir / "source.html"
            if return_code != 0 or not generated.is_file():
                raise OfficePreviewError("OFFICE_RENDER_FAILED", "LibreOffice 无法生成工作表预览。", 422)
            if generated.stat().st_size > MAX_XLSX_HTML_BYTES:
                raise OfficePreviewError("OFFICE_RENDER_OUTPUT_TOO_LARGE", "工作表预览超过大小限制。", 413)
            content = generated.read_text(encoding="utf-8")
            guard = _SpreadsheetHTMLGuard()
            guard.feed(content)
            guard.close()
            closing_head = content.casefold().find("</head>")
            if closing_head >= 0:
                content = f"{content[:closing_head]}{XLSX_PREVIEW_STYLE}{content[closing_head:]}"
            else:
                opening_body = content.casefold().find("<body")
                if opening_body >= 0:
                    body_start = content.find(">", opening_body)
                    if body_start >= 0:
                        content = f"{content[:body_start + 1]}{XLSX_PREVIEW_STYLE}{content[body_start + 1:]}"
                else:
                    raise ValueError("Spreadsheet HTML is missing a document body.")
            temporary_cache = cache_path.with_suffix(f".{os.getpid()}.partial")
            temporary_cache.write_text(content, encoding="utf-8")
            os.replace(temporary_cache, cache_path)
    except OfficePreviewError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise OfficePreviewError("OFFICE_RENDER_FAILED", "无法生成安全的工作表预览。", 422) from exc
    return cache_path


def get_or_create_xlsx_sheet_preview(
    source: Path, content_hash: str, sheet_index: int, settings: Settings
) -> Path:
    if len(content_hash) != 64 or any(character not in "0123456789abcdef" for character in content_hash):
        raise OfficePreviewError("OFFICE_PREVIEW_CACHE_KEY_INVALID", "Office 预览缓存键无效。", 500)
    if sheet_index < 0 or sheet_index >= 2000:
        raise OfficePreviewError("XLSX_PREVIEW_SHEET_NOT_FOUND", "工作表不存在。", 404)
    cache_key = hashlib.sha256(
        f"{OFFICE_PREVIEW_CACHE_REVISION}:XLSX-HTML-TABLE-STYLE-V2:{content_hash}:{sheet_index}".encode("ascii")
    ).hexdigest()
    cache_path = validate_managed_content_path(
        settings, f"previews/office/xlsx/html/{cache_key}.html"
    )
    lock_path = validate_managed_content_path(settings, "previews/office/renderer.lock")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.is_file() and cache_path.stat().st_size <= MAX_XLSX_HTML_BYTES:
        return cache_path
    cache_path.unlink(missing_ok=True)
    executable = find_libreoffice(settings)
    if executable is None:
        raise OfficePreviewError(
            "OFFICE_RENDERER_UNAVAILABLE", "缺少本地 LibreOffice 运行时，无法生成工作表预览。", 503
        )
    with _renderer_slot(MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS):
        with _cache_lock(lock_path, MAX_PREVIEW_CACHE_LOCK_WAIT_SECONDS):
            if cache_path.is_file() and cache_path.stat().st_size <= MAX_XLSX_HTML_BYTES:
                return cache_path
            cache_path.unlink(missing_ok=True)
            _render_xlsx_html(source, executable, cache_path, settings, sheet_index)
            return cache_path


def get_or_create_pptx_preview(
    source: Path, content_hash: str, settings: Settings
) -> tuple[Path, int, bool]:
    return get_or_create_office_preview(source, content_hash, "PPTX", settings)
