from __future__ import annotations

# FastAPI's dependency declarations are intentionally evaluated at route definition time.
# ruff: noqa: B008
import json
import mimetypes
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import Session

from mindmate.api.problem import ProblemDetail
from mindmate.application.files import (
    MAX_BATCH_SIZE,
    MAX_FILE_COUNT,
    MAX_FILE_TAGS,
    MAX_FOLDER_DEPTH,
    SUPPORTED_DOCUMENTS,
    FileValidationError,
    content_relative_path,
    copy_stream_to_staging,
    delete_parsed_text,
    document_spec,
    mark_parse_failed,
    mark_parse_succeeded,
    normalize_name,
    promote_staged_file,
    read_parsed_text,
    resolve_storage_path,
    safe_parse_failure_message,
    sanitize_display_name,
    utc_now,
    validate_file_format,
    validate_managed_content_path,
    validate_upload_mime,
)
from mindmate.application.tasks import add_event, cancel_task, create_task
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    Chunk,
    ContentObject,
    FileRecord,
    FileTag,
    Folder,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    Tag,
    new_id,
)

router = APIRouter(prefix="/api/v1")


def _delete_unbuilt_index_snapshots_for_files(session: Session, file_ids: list[str]) -> None:
    if not file_ids:
        return
    version_ids = list(
        session.scalars(
            select(IndexVersionInput.index_version_id)
            .join(
                IndexVersion,
                IndexVersion.index_version_id == IndexVersionInput.index_version_id,
            )
            .where(IndexVersionInput.file_id.in_(file_ids), IndexVersion.status == "BUILDING")
            .distinct()
        )
    )
    if not version_ids:
        return
    session.execute(
        delete(IndexVersionInput).where(IndexVersionInput.index_version_id.in_(version_ids))
    )
    session.execute(
        delete(IndexVersion).where(
            IndexVersion.index_version_id.in_(version_ids),
            IndexVersion.status == "BUILDING",
        )
    )


class FileApiError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        status: int = 400,
        current_row_version: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.current_row_version = current_row_version


class TagResponse(BaseModel):
    tag_id: str
    name: str
    color: str | None = None
    row_version: int
    created_at: datetime
    updated_at: datetime


class FolderResponse(BaseModel):
    folder_id: str
    parent_folder_id: str | None = None
    name: str
    file_count: int
    row_version: int
    created_at: datetime
    updated_at: datetime


class FileItemResponse(BaseModel):
    file_id: str
    display_name: str
    source_name: str
    extension: str
    document_type: str
    folder_id: str | None = None
    folder_name: str | None = None
    status: str
    content_hash: str
    byte_size: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    purge_after: datetime | None = None
    row_version: int
    tags: list[TagResponse]
    parsed_metadata: dict[str, Any] | None = None
    has_parsed_text: bool
    content_available: bool
    parse_failure_stage: str | None = None
    parse_error_id: str | None = None
    parse_retry_count: int
    can_reprocess: bool


class FileListResponse(BaseModel):
    items: list[FileItemResponse]
    next_cursor: str | None = None


class FolderListResponse(BaseModel):
    items: list[FolderResponse]


class TagListResponse(BaseModel):
    items: list[TagResponse]


class ReprocessResponse(BaseModel):
    task_id: str
    file: FileItemResponse


class ImportItemResponse(BaseModel):
    item_index: int
    original_name: str
    status: str
    hash_status: str | None = None
    duplicate_status: str
    file_id: str | None = None
    task_id: str | None = None
    error: str | None = None
    error_code: str | None = None
    parse_status: str | None = None
    parse_error: str | None = None
    parse_failure_stage: str | None = None
    parse_error_id: str | None = None
    parse_retry_count: int | None = None


class ImportTaskResponse(BaseModel):
    import_id: str
    task_id: str
    status: str
    phase: str | None = None
    progress: int | None = None
    items: list[ImportItemResponse]
    folder_id: str | None = None
    tag_ids: list[str]
    knowledge_base_id: str | None = None
    error: str | None = None


class BackgroundTaskResponse(BaseModel):
    import_id: str
    task_id: str
    task_type: str
    status: str
    phase: str | None = None
    progress: int | None = None
    items: list[dict[str, Any]]
    folder_id: str | None = None
    tag_ids: list[str]
    knowledge_base_id: str | None = None
    index_version_id: str | None = None
    results: list[dict[str, Any]]
    summary: dict[str, Any] | None = None
    error: str | None = None


class TrashFolderResponse(BaseModel):
    folder_id: str
    name: str
    row_version: int
    deleted_at: datetime | None = None
    purge_after: datetime | None = None


class TrashResponse(BaseModel):
    files: list[FileItemResponse]
    folders: list[TrashFolderResponse]


VERSION_CONFLICT_RESPONSES: dict[int | str, dict[str, Any]] = {
    412: {"model": ProblemDetail, "description": "资源版本冲突，客户端必须刷新后重试。"}
}


class FilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    folder_id: str | None = None
    row_version: int


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_folder_id: str | None = None


class FolderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    row_version: int


class FolderMove(BaseModel):
    parent_folder_id: str | None = None
    row_version: int


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    color: str | None = Field(default=None, max_length=20)


class TagPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    color: str | None = Field(default=None, max_length=20)
    row_version: int = Field(ge=1)


class DuplicateDecision(BaseModel):
    item_index: int = Field(ge=0)
    decision: str


class DuplicateDecisionRequest(BaseModel):
    decisions: list[DuplicateDecision]


class FileBatchRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1, max_length=100)
    action: str
    folder_id: str | None = None
    tag_id: str | None = None


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise FileApiError("LOCAL_RUNTIME_UNAVAILABLE", "本地运行配置不可用。", 503)
    return settings


def get_session(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise FileApiError("LOCAL_RUNTIME_UNAVAILABLE", "本地数据库会话不可用。", 503)
    with factory() as session:
        yield session


def _folder_depth(session: Session, parent_id: str | None) -> int:
    depth = 0
    seen: set[str] = set()
    current = parent_id
    while current:
        if current in seen:
            raise FileApiError("FOLDER_TREE_INVALID", "文件夹层级存在循环。")
        seen.add(current)
        parent = session.get(Folder, current)
        if parent is None or parent.deleted_at is not None:
            raise FileApiError("FOLDER_NOT_FOUND", "目标文件夹不存在。", 404)
        depth += 1
        current = parent.parent_folder_id
    return depth


def _assert_row_version(current: int, expected: int) -> None:
    if current != expected:
        raise FileApiError(
            "RESOURCE_VERSION_CONFLICT",
            f"资源已被其他操作更新，当前版本为 {current}，本次请求不会覆盖最新数据。请刷新后重试。",
            412,
            current_row_version=current,
        )


def _atomic_folder_update(
    session: Session,
    folder_id: str,
    expected_version: int,
    values: dict[str, Any],
    *,
    deleted: bool,
) -> None:
    state_clause = Folder.deleted_at.is_not(None) if deleted else Folder.deleted_at.is_(None)
    result = session.execute(
        update(Folder)
        .where(
            Folder.folder_id == folder_id,
            state_clause,
            Folder.row_version == expected_version,
        )
        .values(**values, row_version=Folder.row_version + 1)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) == 1:
        return
    session.rollback()
    current = session.get(Folder, folder_id)
    if current is None or (current.deleted_at is not None) != deleted:
        raise FileApiError("FOLDER_NOT_FOUND", "文件夹不存在。", 404)
    _assert_row_version(current.row_version, expected_version)


def _atomic_tag_update(
    session: Session, tag_id: str, expected_version: int, values: dict[str, Any]
) -> None:
    result = session.execute(
        update(Tag)
        .where(Tag.tag_id == tag_id, Tag.row_version == expected_version)
        .values(**values, row_version=Tag.row_version + 1)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) == 1:
        return
    session.rollback()
    current = session.get(Tag, tag_id)
    if current is None:
        raise FileApiError("TAG_NOT_FOUND", "标签不存在。", 404)
    _assert_row_version(current.row_version, expected_version)


def _unique_display_name(
    session: Session, desired: str, folder_id: str | None, exclude_file_id: str | None = None
) -> str:
    candidate = desired
    stem, dot, extension = desired.rpartition(".")
    if not dot:
        stem, extension = desired, ""
    suffix = 2
    while True:
        query = select(FileRecord.file_id).where(
            FileRecord.folder_id == folder_id,
            FileRecord.deleted_at.is_(None),
            func.lower(FileRecord.display_name) == candidate.casefold(),
        )
        if exclude_file_id:
            query = query.where(FileRecord.file_id != exclude_file_id)
        if session.scalar(query) is None:
            return candidate
        candidate = f"{stem} ({suffix}){('.' + extension) if extension else ''}"
        suffix += 1


def _tag_payload(tag: Tag) -> dict[str, Any]:
    return {
        "tag_id": tag.tag_id,
        "name": tag.name,
        "color": tag.color,
        "row_version": tag.row_version,
        "created_at": tag.created_at.isoformat(),
        "updated_at": tag.updated_at.isoformat(),
    }


def _folder_payload(session: Session, folder: Folder) -> dict[str, Any]:
    count = session.scalar(
        select(func.count(FileRecord.file_id)).where(
            FileRecord.folder_id == folder.folder_id, FileRecord.deleted_at.is_(None)
        )
    )
    return {
        "folder_id": folder.folder_id,
        "parent_folder_id": folder.parent_folder_id,
        "name": folder.name,
        "file_count": int(count or 0),
        "row_version": folder.row_version,
        "created_at": folder.created_at.isoformat(),
        "updated_at": folder.updated_at.isoformat(),
    }


def _file_tags(session: Session, file_id: str) -> list[Tag]:
    return list(
        session.scalars(
            select(Tag)
            .join(FileTag, FileTag.tag_id == Tag.tag_id)
            .where(FileTag.file_id == file_id)
            .order_by(Tag.name)
        )
    )


def _file_payload(session: Session, settings: Settings, record: FileRecord) -> dict[str, Any]:
    folder = session.get(Folder, record.folder_id) if record.folder_id else None
    parsed = read_parsed_text(settings, record.file_id)
    content = session.get(ContentObject, record.content_object_id)
    return {
        "file_id": record.file_id,
        "display_name": record.display_name,
        "source_name": record.source_name,
        "extension": record.extension,
        "document_type": record.document_type,
        "folder_id": record.folder_id,
        "folder_name": folder.name if folder else None,
        "status": record.status,
        "content_hash": record.content_hash[:12],
        "byte_size": record.byte_size,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
        "purge_after": record.purge_after.isoformat() if record.purge_after else None,
        "row_version": record.row_version,
        "tags": [_tag_payload(tag) for tag in _file_tags(session, record.file_id)],
        "parsed_metadata": parsed.get("metadata") if parsed else None,
        "has_parsed_text": parsed is not None,
        "content_available": content is not None and content.storage_state == "READY",
        "parse_failure_stage": record.parse_failure_stage,
        "parse_error_id": record.parse_error_id,
        "parse_retry_count": record.parse_retry_count,
        "can_reprocess": (
            record.deleted_at is None and content is not None and content.storage_state == "READY"
        ),
    }


def _safe_parse_failure(error: FileValidationError) -> str:
    return safe_parse_failure_message(error.code)


def _mark_parse_succeeded(record: FileRecord) -> None:
    mark_parse_succeeded(record)


def _mark_parse_failed(record: FileRecord, error: FileValidationError) -> str:
    return mark_parse_failed(record, error)


def _restored_file_status(settings: Settings, record: FileRecord) -> str:
    if read_parsed_text(settings, record.file_id):
        return "PARSED"
    if record.parse_error_id:
        return "PARSE_FAILED"
    return "QUEUED"


def _task_items(task: BackgroundTask) -> list[dict[str, Any]]:
    checkpoint = task.checkpoint_json or {}
    items = checkpoint.get("items", []) if isinstance(checkpoint, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _task_payload(task: BackgroundTask) -> dict[str, Any]:
    checkpoint = task.checkpoint_json or {}
    context = checkpoint.get("context", {}) if isinstance(checkpoint, dict) else {}
    return {
        "import_id": task.task_id,
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "phase": task.phase,
        "progress": task.progress,
        "items": _task_items(task),
        "folder_id": context.get("folder_id"),
        "tag_ids": context.get("tag_ids", []),
        "knowledge_base_id": context.get("knowledge_base_id")
        or (checkpoint.get("knowledge_base_id") if isinstance(checkpoint, dict) else None),
        "index_version_id": checkpoint.get("index_version_id")
        if isinstance(checkpoint, dict)
        else None,
        "results": checkpoint.get("results", []) if isinstance(checkpoint, dict) else [],
        "summary": checkpoint.get("summary") if isinstance(checkpoint, dict) else None,
        "error": task.error_summary,
    }


def _task_contains_file(task: BackgroundTask, file_id: str) -> bool:
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    context = checkpoint.get("context", {})
    if isinstance(context, dict) and context.get("file_id") == file_id:
        return True
    items = checkpoint.get("items", [])
    return isinstance(items, list) and any(
        isinstance(item, dict) and item.get("file_id") == file_id for item in items
    )


def _active_parse_task(session: Session, file_id: str) -> BackgroundTask | None:
    tasks = session.scalars(
        select(BackgroundTask).where(
            BackgroundTask.task_type.in_({"FILE_IMPORT", "FILE_REPROCESS"}),
            BackgroundTask.status.in_({"BLOCKED", "QUEUED", "RUNNING", "INTERRUPTED"}),
        )
    )
    return next((task for task in tasks if _task_contains_file(task, file_id)), None)


def _safe_staging_path(settings: Settings, task_id: str, index: int) -> Path:
    return resolve_storage_path(settings, f"tasks/file-imports/{task_id}/{index}.staging")


def _remove_staging(settings: Settings, item: dict[str, Any]) -> None:
    relative = item.get("staged_relative_path")
    if isinstance(relative, str):
        resolve_storage_path(settings, relative).unlink(missing_ok=True)
        item.pop("staged_relative_path", None)


def _parse_ids(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in value.split(",") if part.strip()]


def _validate_context(
    session: Session, folder_id: str | None, tag_ids: list[str], knowledge_base_id: str | None
) -> None:
    if folder_id:
        folder = session.get(Folder, folder_id)
        if folder is None or folder.deleted_at is not None:
            raise FileApiError("FOLDER_NOT_FOUND", "目标文件夹不存在。", 404)
    if len(tag_ids) > MAX_FILE_TAGS:
        raise FileApiError("TOO_MANY_TAGS", "一个文件最多关联 10 个标签。")
    for tag_id in tag_ids:
        if session.get(Tag, tag_id) is None:
            raise FileApiError("TAG_NOT_FOUND", "标签不存在。", 404)
    if knowledge_base_id and session.get(KnowledgeBase, knowledge_base_id) is None:
        raise FileApiError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在。", 404)


def _attach_tags(session: Session, file_id: str, tag_ids: list[str]) -> None:
    for tag_id in dict.fromkeys(tag_ids):
        session.add(FileTag(file_tag_id=new_id(), file_id=file_id, tag_id=tag_id))


def _attach_knowledge_base(session: Session, file_id: str, knowledge_base_id: str | None) -> None:
    if not knowledge_base_id:
        return
    existing = session.scalar(
        select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.file_id == file_id,
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
        )
    )
    if existing is None:
        session.add(
            KnowledgeBaseFile(
                knowledge_base_file_id=new_id(),
                knowledge_base_id=knowledge_base_id,
                file_id=file_id,
                membership_status="ACTIVE",
                index_state="PENDING",
                added_at=utc_now(),
            )
        )


def _create_record_from_content(
    session: Session,
    settings: Settings,
    content: ContentObject,
    original_name: str,
    spec_extension: str,
    document_type: str,
    folder_id: str | None,
    tag_ids: list[str],
    knowledge_base_id: str | None,
) -> tuple[FileRecord, str | None]:
    file_id = new_id()
    display_name = _unique_display_name(session, original_name, folder_id)
    record = FileRecord(
        file_id=file_id,
        content_object_id=content.content_object_id,
        display_name=display_name,
        extension=spec_extension,
        document_type=document_type,
        folder_id=folder_id,
        status="QUEUED",
        source_name=original_name,
        content_hash=content.sha256,
        byte_size=content.byte_size,
        parse_revision_id=None,
        parse_failure_stage=None,
        parse_error_id=None,
        parse_retry_count=0,
        created_at=utc_now(),
        updated_at=utc_now(),
        row_version=1,
    )
    content.reference_count += 1
    session.add(record)
    session.flush()
    _attach_tags(session, file_id, tag_ids)
    _attach_knowledge_base(session, file_id, knowledge_base_id)
    return record, None


def _promote_new_content(
    session: Session,
    settings: Settings,
    staged: Path,
    sha256: str,
    byte_size: int,
    spec_extension: str,
    mime_type: str,
) -> ContentObject:
    content_id = new_id()
    relative_path = content_relative_path(content_id, spec_extension)
    promote_staged_file(settings, staged, relative_path)
    content = ContentObject(
        content_object_id=content_id,
        sha256=sha256,
        byte_size=byte_size,
        detected_mime_type=mime_type,
        storage_relative_path=relative_path,
        storage_state="READY",
        reference_count=0,
        created_at=utc_now(),
        verified_at=utc_now(),
    )
    session.add(content)
    session.flush()
    return content


def _find_active_content(session: Session, sha256: str) -> ContentObject | None:
    return session.scalar(
        select(ContentObject).where(
            ContentObject.sha256 == sha256,
            ContentObject.storage_state == "READY",
        )
    )


@router.post(
    "/file-imports", status_code=202, response_model=ImportTaskResponse, tags=["files"]
)
async def create_file_import(
    request: Request,
    files: list[UploadFile] = File(...),
    folder_id: str | None = Form(default=None),
    tag_ids: str | None = Form(default=None),
    knowledge_base_id: str | None = Form(default=None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    if not files:
        raise FileApiError("FILES_REQUIRED", "至少选择一个文件。")
    idempotency_key = request.headers.get("idempotency-key")
    if not idempotency_key:
        raise FileApiError("IDEMPOTENCY_KEY_REQUIRED", "导入请求必须携带幂等键。")
    tag_id_list = _parse_ids(tag_ids)
    _validate_context(session, folder_id, tag_id_list, knowledge_base_id)
    existing = session.scalar(
        select(BackgroundTask).where(BackgroundTask.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.task_type != "FILE_IMPORT":
            raise FileApiError("IDEMPOTENCY_KEY_CONFLICT", "幂等键已用于其他操作。", 409)
        return JSONResponse(status_code=202, content=_task_payload(existing))
    task = create_task(
        session,
        "FILE_IMPORT",
        idempotency_key,
        {
            "context": {
                "folder_id": folder_id,
                "tag_ids": tag_id_list,
                "knowledge_base_id": knowledge_base_id,
            },
            "items": [],
        },
    )
    task.status = "RUNNING"
    task.phase = "VALIDATING"
    task.progress = 0
    items: list[dict[str, Any]] = []
    total_bytes = 0
    pending_duplicates = False
    for index, upload in enumerate(files):
        item: dict[str, Any] = {
            "item_index": index,
            "original_name": upload.filename or "",
            "status": "REJECTED",
            "hash_status": "NOT_STARTED",
            "duplicate_status": "NOT_DUPLICATE",
            "file_id": None,
            "task_id": task.task_id,
            "error": None,
        }
        items.append(item)
        if index >= MAX_FILE_COUNT:
            item["error"] = "单次最多导入 20 个文件。"
            item["error_code"] = "TOO_MANY_FILES"
            await upload.close()
            continue
        if total_bytes >= MAX_BATCH_SIZE:
            item["error"] = "单次导入总量不能超过 500 MB。"
            item["error_code"] = "BATCH_TOO_LARGE"
            await upload.close()
            continue
        try:
            safe_name = sanitize_display_name(upload.filename or "")
            spec = document_spec(safe_name)
            validate_upload_mime(spec, upload.content_type)
            staged = _safe_staging_path(settings, task.task_id, index)
            size, digest, header = copy_stream_to_staging(upload.file, staged)
            total_bytes += size
            if total_bytes > MAX_BATCH_SIZE:
                staged.unlink(missing_ok=True)
                item["error"] = "单次导入总量不能超过 500 MB。"
                item["error_code"] = "BATCH_TOO_LARGE"
                continue
            validate_file_format(staged, spec, header)
            item.update(
                {
                    "original_name": safe_name,
                    "extension": spec.extension,
                    "document_type": spec.document_type,
                    "byte_size": size,
                    "sha256": digest,
                    "hash_status": "COMPUTED",
                }
            )
            duplicate = _find_active_content(session, digest)
            if duplicate is not None:
                item.update(
                    {
                        "status": "BLOCKED",
                        "duplicate_status": "PENDING_DECISION",
                        "duplicate_file_id": session.scalar(
                            select(FileRecord.file_id)
                            .where(
                                FileRecord.content_object_id == duplicate.content_object_id,
                                FileRecord.deleted_at.is_(None),
                            )
                            .order_by(FileRecord.created_at)
                            .limit(1)
                        ),
                        "staged_relative_path": str(
                            staged.relative_to(settings.resolved_data_dir).as_posix()
                        ),
                    }
                )
                pending_duplicates = True
                continue
            content = _promote_new_content(
                session,
                settings,
                staged,
                digest,
                size,
                spec.extension,
                spec.mime_type,
            )
            record, parse_error = _create_record_from_content(
                session,
                settings,
                content,
                safe_name,
                spec.extension,
                spec.document_type,
                folder_id,
                tag_id_list,
                knowledge_base_id,
            )
            item.update(
                {
                    "status": "IMPORTED",
                    "file_id": record.file_id,
                    "parse_status": record.status,
                    "parse_error": parse_error,
                    "parse_failure_stage": record.parse_failure_stage,
                    "parse_error_id": record.parse_error_id,
                    "parse_retry_count": record.parse_retry_count,
                }
            )
        except FileValidationError as exc:
            item["error"] = exc.detail
            item["error_code"] = exc.code
        except (OSError, ValueError) as exc:
            item["error"] = "文件无法读取或复制失败。"
            item["error_code"] = "FILE_IMPORT_FAILED"
            task.error_summary = str(exc)[:500]
        finally:
            await upload.close()
    task.checkpoint_json = {
        "context": {
            "folder_id": folder_id,
            "tag_ids": tag_id_list,
            "knowledge_base_id": knowledge_base_id,
        },
        "items": items,
    }
    has_parse_work = any(
        item.get("status") == "IMPORTED" and item.get("file_id") for item in items
    )
    if pending_duplicates:
        task.phase = "WAITING_DUPLICATE_DECISION"
        task.status = "BLOCKED"
        task.progress = 100 if not has_parse_work else 0
        task.completed_at = None
    elif has_parse_work:
        task.phase = "PARSING"
        task.status = "QUEUED"
        task.progress = 0
        task.completed_at = None
    else:
        task.phase = "COMPLETED"
        task.status = "COMPLETED"
        task.progress = 100
        task.completed_at = utc_now()
    task.updated_at = utc_now()
    task.row_version += 1
    add_event(session, task, task.status, {"item_count": len(items)})
    session.commit()
    return JSONResponse(status_code=202, content=_task_payload(task))


@router.get("/file-imports/{import_id}", response_model=ImportTaskResponse, tags=["files"])
def get_file_import(import_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = session.get(BackgroundTask, import_id)
    if task is None or task.task_type != "FILE_IMPORT":
        raise FileApiError("IMPORT_NOT_FOUND", "导入任务不存在。", 404)
    return _task_payload(task)


@router.get(
    "/tasks/{task_id}", response_model=BackgroundTaskResponse, tags=["tasks"]
)
def get_background_task(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = session.get(BackgroundTask, task_id)
    if task is None:
        raise FileApiError("TASK_NOT_FOUND", "任务不存在。", 404)
    return _task_payload(task)


@router.post(
    "/file-imports/{import_id}/duplicate-decisions",
    response_model=ImportTaskResponse,
    tags=["files"],
)
def decide_duplicates(
    import_id: str,
    payload: DuplicateDecisionRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    task = session.get(BackgroundTask, import_id)
    if task is None or task.task_type != "FILE_IMPORT":
        raise FileApiError("IMPORT_NOT_FOUND", "导入任务不存在。", 404)
    if task.status != "BLOCKED":
        return _task_payload(task)
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    context = checkpoint.get("context", {})
    items = _task_items(task)
    decisions = {decision.item_index: decision.decision for decision in payload.decisions}
    for item in items:
        if item.get("duplicate_status") != "PENDING_DECISION":
            continue
        index = int(item["item_index"])
        decision = decisions.get(index)
        if decision not in {"REUSE_EXISTING", "CREATE_SEPARATE_RECORD", "SKIP"}:
            raise FileApiError("DUPLICATE_DECISION_INVALID", "重复文件决策无效。")
        digest = str(item.get("sha256", ""))
        content = _find_active_content(session, digest)
        if content is None:
            item.update({"status": "REJECTED", "error": "重复内容已不可用。"})
            _remove_staging(settings, item)
            continue
        if decision == "REUSE_EXISTING":
            existing_file = session.scalar(
                select(FileRecord)
                .where(
                    FileRecord.content_object_id == content.content_object_id,
                    FileRecord.deleted_at.is_(None),
                )
                .order_by(FileRecord.created_at)
                .limit(1)
            )
            item.update(
                {
                    "status": "REUSED",
                    "duplicate_status": "REUSED",
                    "file_id": existing_file.file_id if existing_file else None,
                }
            )
        elif decision == "CREATE_SEPARATE_RECORD":
            spec = document_spec(str(item["original_name"]))
            record, parse_error = _create_record_from_content(
                session,
                settings,
                content,
                str(item["original_name"]),
                spec.extension,
                str(item["document_type"]),
                context.get("folder_id"),
                [str(tag_id) for tag_id in context.get("tag_ids", [])],
                context.get("knowledge_base_id"),
            )
            item.update(
                {
                    "status": "IMPORTED",
                    "duplicate_status": "SEPARATE_RECORD",
                    "file_id": record.file_id,
                    "parse_status": record.status,
                    "parse_error": parse_error,
                    "parse_failure_stage": record.parse_failure_stage,
                    "parse_error_id": record.parse_error_id,
                    "parse_retry_count": record.parse_retry_count,
                }
            )
        else:
            item.update({"status": "SKIPPED", "duplicate_status": "SKIPPED"})
        _remove_staging(settings, item)
    pending = any(item.get("duplicate_status") == "PENDING_DECISION" for item in items)
    has_parse_work = any(
        item.get("status") == "IMPORTED" and item.get("file_id") for item in items
    )
    task.checkpoint_json = {"context": context, "items": items}
    if pending:
        task.status = "BLOCKED"
        task.phase = "WAITING_DUPLICATE_DECISION"
        task.progress = 0 if has_parse_work else 100
        task.completed_at = None
    elif has_parse_work:
        task.status = "QUEUED"
        task.phase = "PARSING"
        task.progress = 0
        task.completed_at = None
    else:
        task.status = "COMPLETED"
        task.phase = "COMPLETED"
        task.progress = 100
        task.completed_at = utc_now()
    task.updated_at = utc_now()
    task.row_version += 1
    add_event(session, task, task.status, {"decisions": len(payload.decisions)})
    session.commit()
    return _task_payload(task)


@router.post(
    "/file-imports/{import_id}/cancel", response_model=ImportTaskResponse, tags=["files"]
)
def cancel_file_import(
    import_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    task = session.get(BackgroundTask, import_id)
    if task is None or task.task_type != "FILE_IMPORT":
        raise FileApiError("IMPORT_NOT_FOUND", "导入任务不存在。", 404)
    for item in _task_items(task):
        _remove_staging(settings, item)
    cancel_task(session, task)
    task.checkpoint_json = {"context": {}, "items": _task_items(task)}
    session.commit()
    return _task_payload(task)


@router.get("/files", response_model=FileListResponse, tags=["files"])
def list_files(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    q: str | None = None,
    folder_id: str | None = None,
    tag_id: str | None = None,
    document_type: str | None = None,
    status: str | None = None,
    knowledge_base_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    include_deleted: bool = False,
    sort: str = Query(default="updated_at"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    query = select(FileRecord)
    if not include_deleted:
        query = query.where(FileRecord.deleted_at.is_(None))
    if folder_id:
        query = query.where(FileRecord.folder_id == folder_id)
    if document_type:
        query = query.where(FileRecord.document_type == document_type.upper())
    if status:
        query = query.where(FileRecord.status == status.upper())
    if knowledge_base_id:
        query = query.join(
            KnowledgeBaseFile, KnowledgeBaseFile.file_id == FileRecord.file_id
        ).where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
        )
    if created_from:
        query = query.where(FileRecord.created_at >= created_from)
    if created_to:
        query = query.where(FileRecord.created_at <= created_to)
    if tag_id:
        query = query.join(FileTag, FileTag.file_id == FileRecord.file_id).where(
            FileTag.tag_id == tag_id
        )
    if q:
        pattern = f"%{q.strip().casefold()}%"
        normalized_query = q.strip().casefold()
        parsed_match_ids = [
            record.file_id
            for record in session.scalars(select(FileRecord))
            if normalized_query
            in str((read_parsed_text(settings, record.file_id) or {}).get("text", "")).casefold()
        ]
        query = query.where(
            or_(
                func.lower(FileRecord.display_name).like(pattern),
                FileRecord.file_id.in_(parsed_match_ids),
                exists(
                    select(FileTag.file_tag_id)
                    .join(Tag, Tag.tag_id == FileTag.tag_id)
                    .where(
                        FileTag.file_id == FileRecord.file_id,
                        func.lower(Tag.name).like(pattern),
                    )
                ),
            )
        )
    sort_columns = {
        "name": FileRecord.display_name,
        "size": FileRecord.byte_size,
        "type": FileRecord.document_type,
        "created_at": FileRecord.created_at,
        "updated_at": FileRecord.updated_at,
    }
    query = query.order_by(sort_columns.get(sort, FileRecord.updated_at).desc(), FileRecord.file_id)
    try:
        offset = max(0, int(cursor or "0"))
    except ValueError:
        raise FileApiError("CURSOR_INVALID", "分页游标无效。") from None
    records = list(session.scalars(query.offset(offset).limit(limit + 1)))
    has_more = len(records) > limit
    records = records[:limit]
    return {
        "items": [_file_payload(session, settings, record) for record in records],
        "next_cursor": str(offset + limit) if has_more else None,
        "limit": limit,
    }


def _get_file_or_404(session: Session, file_id: str) -> FileRecord:
    record = session.get(FileRecord, file_id)
    if record is None:
        raise FileApiError("FILE_NOT_FOUND", "文件不存在。", 404)
    return record


@router.get("/files/{file_id}", response_model=FileItemResponse, tags=["files"])
def get_file(
    file_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return _file_payload(session, settings, _get_file_or_404(session, file_id))


@router.patch(
    "/files/{file_id}",
    response_model=FileItemResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def patch_file(
    file_id: str,
    payload: FilePatch,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    record = _get_file_or_404(session, file_id)
    _assert_row_version(record.row_version, payload.row_version)
    folder_requested = "folder_id" in payload.model_fields_set
    if payload.display_name is None and not folder_requested:
        raise FileApiError("FILE_PATCH_EMPTY", "至少提供一个需要更新的字段。")
    if payload.display_name is not None:
        safe_name = sanitize_display_name(payload.display_name)
        spec = document_spec(safe_name)
        if spec.document_type != record.document_type:
            raise FileApiError("FILE_EXTENSION_CHANGE_NOT_ALLOWED", "不能通过重命名改变文件类型。")
        record.display_name = _unique_display_name(
            session, safe_name, record.folder_id, exclude_file_id=record.file_id
        )
    if folder_requested:
        if payload.folder_id is not None and session.get(Folder, payload.folder_id) is None:
            raise FileApiError("FOLDER_NOT_FOUND", "目标文件夹不存在。", 404)
        record.folder_id = payload.folder_id
        record.display_name = _unique_display_name(
            session, record.display_name, record.folder_id, exclude_file_id=record.file_id
        )
    record.row_version += 1
    record.updated_at = utc_now()
    session.commit()
    return _file_payload(session, settings, record)


@router.delete(
    "/files/{file_id}",
    response_model=FileItemResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def trash_file(
    file_id: str,
    expected_version: int | None = Query(default=None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    record = _get_file_or_404(session, file_id)
    if expected_version is not None:
        _assert_row_version(record.row_version, expected_version)
    if record.deleted_at is None:
        deleted_at = utc_now()
        record.deleted_at = deleted_at
        record.purge_after = deleted_at + timedelta(days=30)
        record.status = "IN_TRASH"
        record.row_version += 1
        record.updated_at = utc_now()
        session.commit()
    return _file_payload(session, settings, record)


def _record_content_path(session: Session, settings: Settings, record: FileRecord) -> Path:
    content = session.get(ContentObject, record.content_object_id)
    if content is None or content.storage_state != "READY":
        raise FileApiError("FILE_CONTENT_UNAVAILABLE", "文件内容不可用。", 409)
    try:
        path = validate_managed_content_path(settings, content.storage_relative_path)
    except FileValidationError as exc:
        raise FileApiError(exc.code, exc.detail, 409) from exc
    if not path.is_file():
        record.status = "STORAGE_MISSING"
        raise FileApiError("FILE_CONTENT_MISSING", "应用管理的文件副本不存在。", 409)
    return path


@router.get("/files/{file_id}/content", tags=["files"])
def file_content(
    file_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    record = _get_file_or_404(session, file_id)
    path = _record_content_path(session, settings, record)
    media_type = SUPPORTED_DOCUMENTS.get(record.extension, None)
    response = FileResponse(
        path,
        media_type=media_type.mime_type
        if media_type
        else mimetypes.guess_type(record.display_name)[0],
        filename=record.display_name,
        content_disposition_type="inline",
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = (
        f"inline; filename*=UTF-8''{quote(record.display_name, safe='')}"
    )
    return response


@router.get("/files/{file_id}/preview", tags=["files"])
def file_preview(
    file_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    record = _get_file_or_404(session, file_id)
    preview = read_parsed_text(settings, record.file_id)
    return {
        "file_id": file_id,
        "document_type": record.document_type,
        "preview_available": preview is not None,
        "text": preview.get("text") if preview else None,
        "metadata": preview.get("metadata") if preview else None,
    }


@router.get("/files/{file_id}/text", tags=["files"])
def file_text(
    file_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    start: int = Query(default=0, ge=0),
    length: int = Query(default=20000, ge=1, le=100000),
) -> dict[str, Any]:
    record = _get_file_or_404(session, file_id)
    parsed = read_parsed_text(settings, record.file_id)
    if parsed is None:
        raise FileApiError("PARSED_TEXT_UNAVAILABLE", "该文件尚未生成可读取的解析文本。", 409)
    text = str(parsed.get("text", ""))
    return {
        "file_id": file_id,
        "text": text[start : start + length],
        "start": start,
        "length": min(length, max(0, len(text) - start)),
        "total_length": len(text),
        "metadata": parsed.get("metadata"),
    }


@router.get("/files/{file_id}/knowledge-bases", tags=["files"])
def file_knowledge_bases(file_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _get_file_or_404(session, file_id)
    rows = session.execute(
        select(KnowledgeBaseFile, KnowledgeBase)
        .join(KnowledgeBase, KnowledgeBase.knowledge_base_id == KnowledgeBaseFile.knowledge_base_id)
        .where(
            KnowledgeBaseFile.file_id == file_id, KnowledgeBaseFile.membership_status == "ACTIVE"
        )
    ).all()
    return {
        "items": [
            {
                "knowledge_base_id": knowledge_base.knowledge_base_id,
                "name": knowledge_base.name,
                "index_state": relation.index_state,
                "membership_status": relation.membership_status,
            }
            for relation, knowledge_base in rows
        ]
    }


@router.post(
    "/files/{file_id}/reprocess",
    status_code=202,
    response_model=ReprocessResponse,
    tags=["files"],
)
def reprocess_file(
    file_id: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    record = _get_file_or_404(session, file_id)
    if record.deleted_at is not None:
        raise FileApiError("FILE_IN_TRASH", "回收站中的文件不能重新处理。", 409)
    active = _active_parse_task(session, file_id)
    if active is not None:
        return {"task_id": active.task_id, "file": _file_payload(session, settings, record)}
    idempotency_key = (
        request.headers.get("idempotency-key") or f"reprocess:{file_id}:{record.row_version}"
    )
    existing = session.scalar(
        select(BackgroundTask).where(BackgroundTask.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return {"task_id": existing.task_id, "file": _file_payload(session, settings, record)}
    task = create_task(
        session,
        "FILE_REPROCESS",
        idempotency_key,
        {
            "context": {"file_id": file_id},
            "items": [
                {
                    "item_index": 0,
                    "file_id": file_id,
                    "status": "IMPORTED",
                    "parse_status": "QUEUED",
                    "manual_retry": bool(record.parse_error_id),
                }
            ],
        },
    )
    record.status = "QUEUED"
    record.updated_at = utc_now()
    record.row_version += 1
    task.status = "QUEUED"
    task.phase = "PARSING"
    task.progress = 0
    task.updated_at = utc_now()
    task.row_version += 1
    session.commit()
    return {"task_id": task.task_id, "file": _file_payload(session, settings, record)}


@router.post("/files/batch", tags=["files"])
def batch_file_action(
    payload: FileBatchRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if payload.action == "MOVE" and "folder_id" not in payload.model_fields_set:
        raise FileApiError("FOLDER_REQUIRED", "移动文件需要目标文件夹。")
    if payload.action in {"ADD_TAG", "REMOVE_TAG"} and payload.tag_id is None:
        raise FileApiError("TAG_REQUIRED", "标签操作需要标签。")
    if payload.folder_id and session.get(Folder, payload.folder_id) is None:
        raise FileApiError("FOLDER_NOT_FOUND", "目标文件夹不存在。", 404)
    if payload.tag_id and session.get(Tag, payload.tag_id) is None:
        raise FileApiError("TAG_NOT_FOUND", "标签不存在。", 404)
    results: list[dict[str, Any]] = []
    for file_id in dict.fromkeys(payload.file_ids):
        try:
            reprocess_task_id: str | None = None
            record = _get_file_or_404(session, file_id)
            if payload.action == "MOVE":
                record.folder_id = payload.folder_id
                record.display_name = _unique_display_name(
                    session,
                    record.display_name,
                    record.folder_id,
                    exclude_file_id=record.file_id,
                )
                record.row_version += 1
            elif payload.action == "ADD_TAG":
                if (
                    session.scalar(
                        select(FileTag).where(
                            FileTag.file_id == file_id, FileTag.tag_id == payload.tag_id
                        )
                    )
                    is None
                ):
                    if len(_file_tags(session, file_id)) >= MAX_FILE_TAGS:
                        raise FileApiError("TOO_MANY_TAGS", "一个文件最多关联 10 个标签。")
                    session.add(
                        FileTag(file_tag_id=new_id(), file_id=file_id, tag_id=payload.tag_id)
                    )
            elif payload.action == "REMOVE_TAG":
                session.execute(
                    delete(FileTag).where(
                        FileTag.file_id == file_id, FileTag.tag_id == payload.tag_id
                    )
                )
            elif payload.action == "TRASH":
                deleted_at = utc_now()
                record.deleted_at = deleted_at
                record.purge_after = deleted_at + timedelta(days=30)
                record.status = "IN_TRASH"
                record.row_version += 1
            elif payload.action == "REPROCESS":
                if record.deleted_at is not None:
                    raise FileApiError("FILE_IN_TRASH", "回收站中的文件不能重新处理。", 409)
                active = _active_parse_task(session, record.file_id)
                if active is not None:
                    results.append(
                        {"file_id": file_id, "status": "QUEUED", "task_id": active.task_id}
                    )
                    continue
                task_key = f"batch-reprocess:{record.file_id}:{record.row_version}"
                task = create_task(
                    session,
                    "FILE_REPROCESS",
                    task_key,
                    {
                        "context": {"file_id": record.file_id},
                        "items": [
                            {
                                "item_index": 0,
                                "file_id": record.file_id,
                                "status": "IMPORTED",
                                "parse_status": "QUEUED",
                                "manual_retry": bool(record.parse_error_id),
                            }
                        ],
                    },
                )
                record.status = "QUEUED"
                record.updated_at = utc_now()
                record.row_version += 1
                task.status = "QUEUED"
                task.phase = "PARSING"
                task.progress = 0
                task.updated_at = utc_now()
                task.row_version += 1
                reprocess_task_id = task.task_id
            else:
                raise FileApiError("BATCH_ACTION_INVALID", "批量操作类型无效。")
            record.updated_at = utc_now()
            results.append(
                {"file_id": file_id, "status": "QUEUED", "task_id": reprocess_task_id}
                if payload.action == "REPROCESS"
                else {"file_id": file_id, "status": "SUCCEEDED"}
            )
        except FileApiError as exc:
            results.append({"file_id": file_id, "status": "FAILED", "error": exc.detail})
    session.commit()
    return {"items": results}


@router.get("/folders", response_model=FolderListResponse, tags=["files"])
def list_folders(session: Session = Depends(get_session)) -> dict[str, Any]:
    folders = session.scalars(
        select(Folder)
        .where(Folder.deleted_at.is_(None))
        .order_by(Folder.parent_folder_id, Folder.name)
    )
    return {"items": [_folder_payload(session, folder) for folder in folders]}


@router.post("/folders", status_code=201, response_model=FolderResponse, tags=["files"])
def create_folder(payload: FolderCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    name = " ".join(payload.name.strip().split())
    if not name:
        raise FileApiError("FOLDER_NAME_INVALID", "文件夹名称不能为空。")
    if _folder_depth(session, payload.parent_folder_id) >= MAX_FOLDER_DEPTH:
        raise FileApiError("FOLDER_DEPTH_EXCEEDED", "文件夹最多支持 5 层。")
    normalized = normalize_name(name)
    if session.scalar(
        select(Folder).where(
            Folder.parent_folder_id == payload.parent_folder_id,
            Folder.normalized_name == normalized,
            Folder.deleted_at.is_(None),
        )
    ):
        raise FileApiError("FOLDER_NAME_CONFLICT", "同一文件夹下不能有同名子文件夹。", 409)
    folder = Folder(
        folder_id=new_id(),
        parent_folder_id=payload.parent_folder_id,
        name=name,
        normalized_name=normalized,
        sort_order=0,
        created_at=utc_now(),
        updated_at=utc_now(),
        row_version=1,
    )
    session.add(folder)
    session.commit()
    return _folder_payload(session, folder)


@router.get("/folders/{folder_id}", response_model=FolderResponse, tags=["files"])
def get_folder(folder_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise FileApiError("FOLDER_NOT_FOUND", "文件夹不存在。", 404)
    return _folder_payload(session, folder)


@router.patch(
    "/folders/{folder_id}",
    response_model=FolderResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def patch_folder(
    folder_id: str, payload: FolderPatch, session: Session = Depends(get_session)
) -> dict[str, Any]:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise FileApiError("FOLDER_NOT_FOUND", "文件夹不存在。", 404)
    if payload.name is None:
        raise FileApiError("FOLDER_PATCH_EMPTY", "至少提供一个需要更新的字段。")
    values: dict[str, Any] = {"updated_at": utc_now()}
    if payload.name is not None:
        name = " ".join(payload.name.strip().split())
        if not name:
            raise FileApiError("FOLDER_NAME_INVALID", "文件夹名称不能为空。")
        normalized = normalize_name(name)
        if session.scalar(
            select(Folder).where(
                Folder.parent_folder_id == folder.parent_folder_id,
                Folder.normalized_name == normalized,
                Folder.folder_id != folder_id,
                Folder.deleted_at.is_(None),
            )
        ):
            raise FileApiError("FOLDER_NAME_CONFLICT", "同一文件夹下不能有同名子文件夹。", 409)
        values.update(name=name, normalized_name=normalized)
    _atomic_folder_update(
        session, folder_id, payload.row_version, values, deleted=False
    )
    session.commit()
    session.expire_all()
    updated_folder = session.get(Folder, folder_id)
    assert updated_folder is not None
    return _folder_payload(session, updated_folder)


def _folder_descendants(
    session: Session, folder_id: str, include_deleted: bool = False
) -> list[Folder]:
    query = select(Folder)
    if not include_deleted:
        query = query.where(Folder.deleted_at.is_(None))
    all_folders = list(session.scalars(query))
    descendants: list[Folder] = []
    visited = {folder_id}
    queue = [folder_id]
    while queue:
        current = queue.pop()
        for folder in all_folders:
            if folder.parent_folder_id == current:
                if folder.folder_id in visited:
                    raise FileApiError("FOLDER_TREE_INVALID", "文件夹层级存在循环。", 409)
                visited.add(folder.folder_id)
                descendants.append(folder)
                queue.append(folder.folder_id)
    return descendants


def _folder_subtree_height(session: Session, folder_id: str) -> int:
    descendants = _folder_descendants(session, folder_id)
    if not descendants:
        return 0
    direct_children = [
        folder
        for folder in descendants
        if folder.parent_folder_id == folder_id
    ]
    if not direct_children:
        return 0
    return 1 + max(_folder_subtree_height(session, child.folder_id) for child in direct_children)


@router.post(
    "/folders/{folder_id}/move",
    response_model=FolderResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def move_folder(
    folder_id: str, payload: FolderMove, session: Session = Depends(get_session)
) -> dict[str, Any]:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise FileApiError("FOLDER_NOT_FOUND", "文件夹不存在。", 404)
    if payload.parent_folder_id == folder_id:
        raise FileApiError("FOLDER_TREE_INVALID", "文件夹不能移动到自身。")
    descendants = {item.folder_id for item in _folder_descendants(session, folder_id)}
    if payload.parent_folder_id in descendants:
        raise FileApiError("FOLDER_TREE_INVALID", "文件夹不能移动到自己的子目录。")
    if session.scalar(
        select(Folder).where(
            Folder.parent_folder_id == payload.parent_folder_id,
            Folder.normalized_name == normalize_name(folder.name),
            Folder.folder_id != folder_id,
            Folder.deleted_at.is_(None),
        )
    ):
        raise FileApiError("FOLDER_NAME_CONFLICT", "目标目录已有同名文件夹。", 409)
    if (
        _folder_depth(session, payload.parent_folder_id)
        + 1
        + _folder_subtree_height(session, folder_id)
        > MAX_FOLDER_DEPTH
    ):
        raise FileApiError("FOLDER_DEPTH_EXCEEDED", "移动后会超过 5 层限制。")
    _atomic_folder_update(
        session,
        folder_id,
        payload.row_version,
        {"parent_folder_id": payload.parent_folder_id, "updated_at": utc_now()},
        deleted=False,
    )
    session.commit()
    session.expire_all()
    updated_folder = session.get(Folder, folder_id)
    assert updated_folder is not None
    return _folder_payload(session, updated_folder)


@router.delete(
    "/folders/{folder_id}", responses=VERSION_CONFLICT_RESPONSES, tags=["files"]
)
def delete_folder(
    folder_id: str,
    deletion_strategy: str = Query(default="MOVE_CHILDREN"),
    expected_version: int = Query(ge=1),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    folder = session.get(Folder, folder_id)
    if folder is None or folder.deleted_at is not None:
        raise FileApiError("FOLDER_NOT_FOUND", "文件夹不存在。", 404)
    children = _folder_descendants(session, folder_id)
    if deletion_strategy not in {"MOVE_CHILDREN", "TRASH_RECURSIVE"}:
        raise FileApiError("DELETION_STRATEGY_INVALID", "文件夹删除策略无效。")
    now = utc_now()
    if deletion_strategy == "MOVE_CHILDREN":
        _atomic_folder_update(
            session,
            folder_id,
            expected_version,
            {"deleted_at": now, "purge_after": now + timedelta(days=30), "updated_at": now},
            deleted=False,
        )
        session.execute(
            update(Folder)
            .where(Folder.parent_folder_id == folder_id, Folder.deleted_at.is_(None))
            .values(
                parent_folder_id=folder.parent_folder_id,
                updated_at=now,
                row_version=Folder.row_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        session.execute(
            update(FileRecord)
            .where(FileRecord.folder_id == folder_id)
            .values(
                folder_id=folder.parent_folder_id,
                updated_at=now,
                row_version=FileRecord.row_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    else:
        _atomic_folder_update(
            session,
            folder_id,
            expected_version,
            {"deleted_at": now, "purge_after": now + timedelta(days=30), "updated_at": now},
            deleted=False,
        )
        child_ids = [item.folder_id for item in children]
        all_ids = [folder_id, *child_ids]
        if child_ids:
            session.execute(
                update(Folder)
                .where(Folder.folder_id.in_(child_ids), Folder.deleted_at.is_(None))
                .values(
                    deleted_at=now,
                    purge_after=now + timedelta(days=30),
                    updated_at=now,
                    row_version=Folder.row_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        session.execute(
            update(FileRecord)
            .where(FileRecord.folder_id.in_(all_ids))
            .values(
                deleted_at=now,
                purge_after=now + timedelta(days=30),
                status="IN_TRASH",
                updated_at=now,
                row_version=FileRecord.row_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    session.commit()
    return {
        "folder_id": folder_id,
        "status": "TRASHED" if deletion_strategy == "TRASH_RECURSIVE" else "DELETED",
        "row_version": expected_version + 1,
    }


@router.get("/tags", response_model=TagListResponse, tags=["files"])
def list_tags(session: Session = Depends(get_session)) -> dict[str, Any]:
    tags = list(session.scalars(select(Tag).order_by(Tag.name)))
    return {"items": [_tag_payload(tag) for tag in tags]}


@router.post("/tags", status_code=201, response_model=TagResponse, tags=["files"])
def create_tag(payload: TagCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    name = " ".join(payload.name.strip().split())
    normalized = normalize_name(name)
    if not name:
        raise FileApiError("TAG_NAME_INVALID", "标签名称不能为空。")
    if session.scalar(select(Tag).where(Tag.normalized_name == normalized)):
        raise FileApiError("TAG_NAME_CONFLICT", "标签名称已存在。", 409)
    tag = Tag(
        tag_id=new_id(),
        name=name,
        normalized_name=normalized,
        color=payload.color,
        created_at=utc_now(),
        updated_at=utc_now(),
        row_version=1,
    )
    session.add(tag)
    session.commit()
    return _tag_payload(tag)


@router.patch(
    "/tags/{tag_id}",
    response_model=TagResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def patch_tag(
    tag_id: str, payload: TagPatch, session: Session = Depends(get_session)
) -> dict[str, Any]:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise FileApiError("TAG_NOT_FOUND", "标签不存在。", 404)
    if not (payload.model_fields_set - {"row_version"}):
        raise FileApiError("TAG_PATCH_EMPTY", "至少提供一个需要更新的字段。")
    values: dict[str, Any] = {"updated_at": utc_now()}
    if payload.name is not None:
        name = " ".join(payload.name.strip().split())
        if not name:
            raise FileApiError("TAG_NAME_INVALID", "标签名称不能为空。")
        normalized = normalize_name(name)
        other = session.scalar(
            select(Tag).where(Tag.normalized_name == normalized, Tag.tag_id != tag_id)
        )
        if other:
            raise FileApiError("TAG_NAME_CONFLICT", "标签名称已存在。", 409)
        values.update(name=name, normalized_name=normalized)
    if "color" in payload.model_fields_set:
        values["color"] = payload.color
    _atomic_tag_update(session, tag_id, payload.row_version, values)
    session.commit()
    session.expire_all()
    updated_tag = session.get(Tag, tag_id)
    assert updated_tag is not None
    return _tag_payload(updated_tag)


@router.delete("/tags/{tag_id}", responses=VERSION_CONFLICT_RESPONSES, tags=["files"])
def delete_tag(
    tag_id: str,
    expected_version: int = Query(ge=1),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise FileApiError("TAG_NOT_FOUND", "标签不存在。", 404)
    _atomic_tag_update(session, tag_id, expected_version, {"updated_at": utc_now()})
    session.execute(delete(FileTag).where(FileTag.tag_id == tag_id))
    session.execute(
        delete(Tag).where(Tag.tag_id == tag_id, Tag.row_version == expected_version + 1)
    )
    session.commit()
    return {"tag_id": tag_id, "status": "DELETED", "row_version": expected_version + 1}


@router.put("/files/{file_id}/tags/{tag_id}", tags=["files"])
def add_file_tag(
    file_id: str, tag_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _get_file_or_404(session, file_id)
    if session.get(Tag, tag_id) is None:
        raise FileApiError("TAG_NOT_FOUND", "标签不存在。", 404)
    if (
        session.scalar(select(FileTag).where(FileTag.file_id == file_id, FileTag.tag_id == tag_id))
        is None
    ):
        if len(_file_tags(session, file_id)) >= MAX_FILE_TAGS:
            raise FileApiError("TOO_MANY_TAGS", "一个文件最多关联 10 个标签。")
        session.add(FileTag(file_tag_id=new_id(), file_id=file_id, tag_id=tag_id))
        session.commit()
    return {"file_id": file_id, "tag_id": tag_id, "status": "ACTIVE"}


@router.delete("/files/{file_id}/tags/{tag_id}", tags=["files"])
def remove_file_tag(
    file_id: str, tag_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _get_file_or_404(session, file_id)
    session.execute(delete(FileTag).where(FileTag.file_id == file_id, FileTag.tag_id == tag_id))
    session.commit()
    return {"file_id": file_id, "tag_id": tag_id, "status": "REMOVED"}


@router.get("/trash", response_model=TrashResponse, tags=["files"])
def list_trash(
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    files = session.scalars(
        select(FileRecord)
        .where(FileRecord.deleted_at.is_not(None))
        .order_by(FileRecord.deleted_at.desc())
    )
    folders = session.scalars(
        select(Folder).where(Folder.deleted_at.is_not(None)).order_by(Folder.deleted_at.desc())
    )
    return {
        "files": [_file_payload(session, settings, record) for record in files],
        "folders": [
            {
                "folder_id": folder.folder_id,
                "name": folder.name,
                "row_version": folder.row_version,
                "deleted_at": folder.deleted_at.isoformat() if folder.deleted_at else None,
                "purge_after": folder.purge_after.isoformat() if folder.purge_after else None,
            }
            for folder in folders
        ],
    }


@router.post(
    "/trash/{object_type}/{object_id}/restore",
    response_model=FileItemResponse | FolderResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def restore_trash(
    object_type: str,
    object_id: str,
    expected_version: int = Query(ge=1),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if object_type == "file":
        record = _get_file_or_404(session, object_id)
        _assert_row_version(record.row_version, expected_version)
        if record.folder_id:
            folder = session.get(Folder, record.folder_id)
            if folder is None or folder.deleted_at is not None:
                record.folder_id = None
        record.deleted_at = None
        record.purge_after = None
        record.status = _restored_file_status(settings, record)
        record.row_version += 1
        record.updated_at = utc_now()
        session.commit()
        return _file_payload(session, settings, record)
    if object_type == "folder":
        folder = session.get(Folder, object_id)
        if folder is None or folder.deleted_at is None:
            raise FileApiError("FOLDER_NOT_FOUND", "回收站中的文件夹不存在。", 404)
        now = utc_now()
        related_folders = [folder]
        related_folders.extend(
            item
            for item in _folder_descendants(session, object_id, include_deleted=True)
            if item.deleted_at is not None
        )
        folder_ids = [item.folder_id for item in related_folders]
        root_values: dict[str, Any] = {
            "deleted_at": None,
            "purge_after": None,
            "updated_at": now,
        }
        if folder.parent_folder_id:
            parent = session.get(Folder, folder.parent_folder_id)
            if parent is None or parent.deleted_at is not None:
                root_values["parent_folder_id"] = None
        _atomic_folder_update(
            session,
            object_id,
            expected_version,
            root_values,
            deleted=True,
        )
        descendant_ids = [item.folder_id for item in related_folders if item.folder_id != object_id]
        if descendant_ids:
            session.execute(
                update(Folder)
                .where(Folder.folder_id.in_(descendant_ids), Folder.deleted_at.is_not(None))
                .values(
                    deleted_at=None,
                    purge_after=None,
                    updated_at=now,
                    row_version=Folder.row_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        for record in session.scalars(
            select(FileRecord).where(FileRecord.folder_id.in_(folder_ids))
        ):
            record.deleted_at = None
            record.purge_after = None
            record.status = _restored_file_status(settings, record)
            record.row_version += 1
            record.updated_at = now
        session.commit()
        session.expire_all()
        restored_folder = session.get(Folder, object_id)
        assert restored_folder is not None
        return _folder_payload(session, restored_folder)
    raise FileApiError("TRASH_OBJECT_INVALID", "回收站对象类型无效。")


@router.delete(
    "/trash/{object_type}/{object_id}",
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["files"],
)
def purge_trash(
    object_type: str,
    object_id: str,
    confirmed: bool = Query(default=False),
    expected_version: int = Query(ge=1),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not confirmed:
        raise FileApiError("PURGE_CONFIRMATION_REQUIRED", "永久删除需要明确确认。", 400)

    if object_type == "file":
        record = _get_file_or_404(session, object_id)
        if record.deleted_at is None:
            raise FileApiError("FILE_NOT_IN_TRASH", "只有回收站中的文件才能永久删除。", 409)
        _assert_row_version(record.row_version, expected_version)
        content = session.get(ContentObject, record.content_object_id)
        _delete_unbuilt_index_snapshots_for_files(session, [object_id])
        session.execute(delete(Chunk).where(Chunk.file_id == object_id))
        session.execute(delete(FileTag).where(FileTag.file_id == object_id))
        session.execute(delete(KnowledgeBaseFile).where(KnowledgeBaseFile.file_id == object_id))
        session.delete(record)
        session.flush()
        if content is not None:
            content.reference_count = max(0, content.reference_count - 1)
            if content.reference_count == 0:
                resolve_storage_path(settings, content.storage_relative_path).unlink(missing_ok=True)
                content.storage_state = "PURGED"
                session.delete(content)
        delete_parsed_text(settings, object_id)
        session.commit()
        return {"file_id": object_id, "status": "PURGED"}

    if object_type == "folder":
        folder = session.get(Folder, object_id)
        if folder is None or folder.deleted_at is None:
            raise FileApiError("FOLDER_NOT_IN_TRASH", "只有回收站中的文件夹才能永久删除。", 409)
        _atomic_folder_update(
            session,
            object_id,
            expected_version,
            {"updated_at": utc_now()},
            deleted=True,
        )
        folders = [folder]
        folders.extend(
            item
            for item in _folder_descendants(session, object_id, include_deleted=True)
            if item.deleted_at is not None
        )
        folder_ids = [item.folder_id for item in folders]
        records = list(session.scalars(select(FileRecord).where(FileRecord.folder_id.in_(folder_ids))))
        _delete_unbuilt_index_snapshots_for_files(
            session, [record.file_id for record in records]
        )
        contents: dict[str, ContentObject] = {}
        for record in records:
            content = session.get(ContentObject, record.content_object_id)
            if content is not None:
                contents[content.content_object_id] = content
            session.execute(delete(Chunk).where(Chunk.file_id == record.file_id))
            session.execute(delete(FileTag).where(FileTag.file_id == record.file_id))
            session.execute(delete(KnowledgeBaseFile).where(KnowledgeBaseFile.file_id == record.file_id))
            delete_parsed_text(settings, record.file_id)
            session.delete(record)
        session.flush()
        for content in contents.values():
            content.reference_count = max(0, content.reference_count - sum(
                1 for record in records if record.content_object_id == content.content_object_id
            ))
            if content.reference_count == 0:
                resolve_storage_path(settings, content.storage_relative_path).unlink(missing_ok=True)
                content.storage_state = "PURGED"
                session.delete(content)
        # Detach the self-referential tree before deleting rows in one SQL batch.
        session.execute(
            update(Folder)
            .where(Folder.folder_id.in_(folder_ids))
            .values(parent_folder_id=None)
        )
        session.execute(delete(Folder).where(Folder.folder_id.in_(folder_ids)))
        session.commit()
        return {
            "folder_id": object_id,
            "status": "PURGED",
            "row_version": expected_version + 1,
        }

    raise FileApiError("TRASH_OBJECT_INVALID", "回收站对象类型无效。")
