from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from mindmate.config import Settings

MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_FILE_COUNT = 20
MAX_BATCH_SIZE = 500 * 1024 * 1024
MAX_FOLDER_DEPTH = 5
MAX_FILE_TAGS = 10
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_EXPANDED_SIZE = 200 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 100
MAX_PARSED_OUTPUT_SIZE = 20 * 1024 * 1024
PARSER_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class DocumentSpec:
    extension: str
    document_type: str
    mime_type: str


SUPPORTED_DOCUMENTS: dict[str, DocumentSpec] = {
    ".pdf": DocumentSpec(".pdf", "PDF", "application/pdf"),
    ".docx": DocumentSpec(
        ".docx",
        "DOCX",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".pptx": DocumentSpec(
        ".pptx",
        "PPTX",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ".txt": DocumentSpec(".txt", "TXT", "text/plain"),
    ".md": DocumentSpec(".md", "MARKDOWN", "text/markdown"),
    ".markdown": DocumentSpec(".markdown", "MARKDOWN", "text/markdown"),
}

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class FileValidationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def utc_now() -> datetime:
    return datetime.now(UTC)


def sanitize_display_name(name: str) -> str:
    """Return a display name; never use this value as a storage path."""
    candidate = Path(name.replace("\\", "/")).name
    candidate = CONTROL_CHARACTERS.sub("", candidate).strip().rstrip(".")
    if not candidate or candidate in {".", ".."}:
        raise FileValidationError("FILE_NAME_INVALID", "文件名不能为空或不能只包含路径符号。")
    stem = candidate.rsplit(".", 1)[0] if "." in candidate else candidate
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        raise FileValidationError("FILE_NAME_INVALID", "文件名使用了 Windows 保留名称。")
    if len(candidate) > 255:
        raise FileValidationError("FILE_NAME_INVALID", "文件显示名称不能超过 255 个字符。")
    return candidate


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).casefold()


def document_spec(name: str) -> DocumentSpec:
    extension = Path(name).suffix.casefold()
    spec = SUPPORTED_DOCUMENTS.get(extension)
    if spec is None:
        raise FileValidationError(
            "FILE_TYPE_UNSUPPORTED",
            "仅支持 PDF、DOCX、PPTX、TXT 和 Markdown 文件。",
        )
    return spec


def copy_stream_to_staging(source: BinaryIO, destination: Path) -> tuple[int, str, bytes]:
    """Copy an upload in bounded chunks and return size, hash, and the file header."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    header = bytearray()
    try:
        with destination.open("wb") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise FileValidationError("FILE_TOO_LARGE", "单个文件不能超过 50 MB。")
                digest.update(chunk)
                if len(header) < 8192:
                    header.extend(chunk[: 8192 - len(header)])
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest(), bytes(header)


def _zip_package_kind(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                return None
            expanded_size = sum(entry.file_size for entry in entries)
            compressed_size = sum(max(1, entry.compress_size) for entry in entries)
            if expanded_size > MAX_ARCHIVE_EXPANDED_SIZE:
                return None
            if expanded_size > compressed_size * MAX_ARCHIVE_COMPRESSION_RATIO:
                return None
            names = {name.replace("\\", "/") for name in archive.namelist()}
            if "[Content_Types].xml" not in names:
                return None
            has_word = any(name.startswith("word/") for name in names)
            has_ppt = any(name.startswith("ppt/") for name in names)
            if has_word and not has_ppt:
                return "DOCX"
            if has_ppt and not has_word:
                return "PPTX"
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def _text_header_is_readable(header: bytes) -> bool:
    if b"\x00" in header:
        return False
    for encoding in ("utf-8", "utf-16", "gb18030"):
        try:
            header.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def validate_file_format(path: Path, spec: DocumentSpec, header: bytes) -> None:
    if spec.document_type == "PDF":
        if not header.startswith(b"%PDF-"):
            raise FileValidationError("FILE_SIGNATURE_INVALID", "文件扩展名与 PDF 文件头不匹配。")
        return
    if spec.document_type in {"DOCX", "PPTX"}:
        detected = _zip_package_kind(path)
        if detected != spec.document_type:
            raise FileValidationError("FILE_SIGNATURE_INVALID", "Office 文件包类型与扩展名不匹配。")
        return
    if not _text_header_is_readable(header):
        raise FileValidationError("FILE_SIGNATURE_INVALID", "文本文件无法按受支持的编码读取。")


def validate_upload_mime(spec: DocumentSpec, supplied_mime: str | None) -> None:
    if not supplied_mime or supplied_mime == "application/octet-stream":
        return
    aliases = {
        "TXT": {"text/plain"},
        "MARKDOWN": {"text/markdown", "text/plain", "text/x-markdown"},
        "PDF": {"application/pdf"},
        "DOCX": {spec.mime_type},
        "PPTX": {spec.mime_type},
    }
    if supplied_mime.casefold() not in aliases[spec.document_type]:
        raise FileValidationError("FILE_MIME_INVALID", "文件 MIME 类型与扩展名不匹配。")


def resolve_storage_path(settings: Settings, relative_path: str) -> Path:
    root = settings.resolved_data_dir.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise FileValidationError("STORAGE_PATH_INVALID", "受控文件路径无效。")
    return path


def validate_managed_content_path(settings: Settings, relative_path: str) -> Path:
    root = settings.resolved_data_dir.resolve()
    candidate = root
    for part in Path(relative_path).parts:
        candidate /= part
        if candidate.exists() and (
            candidate.is_symlink()
            or (hasattr(os.path, "isjunction") and os.path.isjunction(candidate))
        ):
            raise FileValidationError("STORAGE_PATH_INVALID", "受控文件路径包含链接或重解析点。")
    path = resolve_storage_path(settings, relative_path)
    if path.exists() and path.stat().st_nlink > 1:
        raise FileValidationError("STORAGE_PATH_INVALID", "受控文件不允许使用硬链接。")
    return path


def content_relative_path(content_object_id: str, extension: str) -> str:
    safe_extension = (
        extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
    )
    return f"objects/{content_object_id[:2]}/{content_object_id}{safe_extension}"


def parsed_relative_path(file_id: str) -> str:
    return f"parsed/{file_id}.json"


def promote_staged_file(settings: Settings, staged_path: Path, relative_path: str) -> Path:
    destination = resolve_storage_path(settings, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, destination)
    return destination


def parse_local_text(path: Path) -> tuple[str, dict[str, int]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise FileValidationError("TEXT_ENCODING_UNSUPPORTED", "文本编码无法识别。")
    return text, {"line_count": text.count("\n") + (1 if text else 0), "character_count": len(text)}


def write_parsed_text(
    settings: Settings,
    file_id: str,
    content_hash: str,
    text: str,
    metadata: Mapping[str, object],
    *,
    parser: str = "local-text-v1",
    locations: list[dict[str, object]] | None = None,
) -> None:
    destination = resolve_storage_path(settings, parsed_relative_path(file_id))
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "file_id": file_id,
        "content_hash": content_hash,
        "parser": parser,
        "parsed_at": utc_now().isoformat(),
        "metadata": metadata,
        "locations": locations or [],
        "text": text,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=destination.parent, delete=False, suffix=".partial"
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(temporary, destination)


def parse_document_in_subprocess(path: Path, document_type: str) -> dict[str, object]:
    worker = Path(__file__).with_name("parser_worker.py")
    with tempfile.TemporaryDirectory(prefix="mindmate-parser-") as temporary_value:
        temporary = Path(temporary_value)
        output = temporary / "result.json"
        try:
            result = subprocess.run(
                [sys.executable, "-I", str(worker), document_type, str(path), str(output)],
                cwd=temporary,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=PARSER_TIMEOUT_SECONDS,
                env={"SystemRoot": os.environ.get("SystemRoot", ""), "TEMP": str(temporary), "TMP": str(temporary)},
            )
        except subprocess.TimeoutExpired as exc:
            raise FileValidationError("PARSER_TIMEOUT", "文件解析超时，已安全终止。") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:300]
            raise FileValidationError("PARSER_FAILED", detail or "文件解析失败。")
        if not output.is_file() or output.stat().st_size > MAX_PARSED_OUTPUT_SIZE:
            raise FileValidationError("PARSER_OUTPUT_INVALID", "解析结果不存在或超过安全上限。")
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FileValidationError("PARSER_OUTPUT_INVALID", "解析结果格式无效。") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise FileValidationError("PARSER_OUTPUT_INVALID", "解析结果缺少文本。")
    metadata = payload.get("metadata")
    locations = payload.get("locations")
    if not isinstance(metadata, dict) or not isinstance(locations, list):
        raise FileValidationError("PARSER_OUTPUT_INVALID", "解析结果缺少元数据或定位信息。")
    return payload


def read_parsed_text(settings: Settings, file_id: str) -> dict[str, object] | None:
    path = resolve_storage_path(settings, parsed_relative_path(file_id))
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def delete_parsed_text(settings: Settings, file_id: str) -> None:
    resolve_storage_path(settings, parsed_relative_path(file_id)).unlink(missing_ok=True)


def iter_chunks(path: Path, chunk_size: int = 1024 * 1024) -> Iterable[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in iter_chunks(path):
        digest.update(chunk)
    return digest.hexdigest()


def decode_text_sample(data: bytes) -> str:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        return decoder.decode(data)
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")
