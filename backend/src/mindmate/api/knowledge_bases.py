from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from mindmate.api.files import VERSION_CONFLICT_RESPONSES, FileApiError
from mindmate.application.chunking import CHUNK_GENERATION_TASK
from mindmate.application.files import normalize_name, utc_now
from mindmate.application.index_embedding import INDEX_EMBED_TASK
from mindmate.application.index_preprocessing import INDEX_PREPROCESS_TASK
from mindmate.application.knowledge_membership_worker import KNOWLEDGE_MEMBERSHIP_TASK
from mindmate.application.tasks import cancel_task, create_task
from mindmate.infrastructure.models import (
    BackgroundTask,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)
from mindmate.infrastructure.vector_store import SqliteVecAdapter, VectorStoreError

router = APIRouter(prefix="/api/v1")

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("知识库名称不能为 null。")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("知识库名称不能为空。")
        return normalized

    @field_validator("description", "icon")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if not COLOR_PATTERN.fullmatch(normalized):
            raise ValueError("颜色必须使用 #RRGGBB 格式。")
        return normalized.lower()


class KnowledgeBasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=20)
    row_version: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("知识库名称不能为 null。")
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("知识库名称不能为空。")
        return normalized

    @field_validator("description", "icon")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if not COLOR_PATTERN.fullmatch(normalized):
            raise ValueError("颜色必须使用 #RRGGBB 格式。")
        return normalized.lower()


class KnowledgeBaseResponse(BaseModel):
    knowledge_base_id: str
    name: str
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    status: str
    file_count: int
    available_file_count: int
    duplicate_name: bool = False
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    purge_after: datetime | None = None
    row_version: int


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]
    next_cursor: str | None = None


class KnowledgeBaseFilesAdd(BaseModel):
    file_ids: list[str] = Field(min_length=1)


class KnowledgeBaseMemberResponse(BaseModel):
    knowledge_base_file_id: str
    file_id: str
    display_name: str
    document_type: str
    file_status: str
    membership_status: str
    index_state: str
    available_for_retrieval: bool
    unavailable_reason: str | None = None
    added_at: datetime


class KnowledgeBaseMemberListResponse(BaseModel):
    items: list[KnowledgeBaseMemberResponse]


class KnowledgeMembershipTaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    phase: str | None = None
    progress: int | None = None
    knowledge_base_id: str | None = None
    index_version_id: str | None = None
    items: list[dict[str, Any]]
    results: list[dict[str, Any]]
    summary: dict[str, Any] | None = None
    error: str | None = None


def get_session(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise FileApiError("LOCAL_RUNTIME_UNAVAILABLE", "本地数据库会话不可用。", 503)
    with factory() as session:
        yield session


def _counts(session: Session, knowledge_base_id: str) -> tuple[int, int]:
    rows = session.execute(
        select(KnowledgeBaseFile.membership_status, func.count())
        .where(KnowledgeBaseFile.knowledge_base_id == knowledge_base_id)
        .group_by(KnowledgeBaseFile.membership_status)
    ).all()
    counts = {status: count for status, count in rows}
    active = int(counts.get("ACTIVE", 0))
    available = int(
        session.scalar(
            select(func.count())
            .select_from(KnowledgeBaseFile)
            .where(
                KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseFile.membership_status == "ACTIVE",
                KnowledgeBaseFile.index_state == "READY",
            )
        )
        or 0
    )
    return active, available


def _has_duplicate_name(session: Session, record: KnowledgeBase) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(KnowledgeBase)
            .where(
                KnowledgeBase.knowledge_base_id != record.knowledge_base_id,
                KnowledgeBase.deleted_at.is_(None),
                func.lower(KnowledgeBase.name) == normalize_name(record.name),
            )
        )
    )


def _payload(session: Session, record: KnowledgeBase) -> dict[str, Any]:
    file_count, available_file_count = _counts(session, record.knowledge_base_id)
    return {
        "knowledge_base_id": record.knowledge_base_id,
        "name": record.name,
        "description": record.description,
        "icon": record.icon,
        "color": record.color,
        "status": "IN_TRASH" if record.deleted_at is not None else record.status,
        "file_count": file_count,
        "available_file_count": available_file_count,
        "duplicate_name": _has_duplicate_name(session, record),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "deleted_at": record.deleted_at,
        "purge_after": record.purge_after,
        "row_version": record.row_version,
    }


def _get(session: Session, knowledge_base_id: str, *, deleted: bool = False) -> KnowledgeBase:
    record = session.get(KnowledgeBase, knowledge_base_id)
    if record is None or (record.deleted_at is not None) != deleted:
        raise FileApiError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在。", 404)
    return record


def _member_payload(member: KnowledgeBaseFile, file: FileRecord) -> dict[str, Any]:
    reasons = {
        "QUEUED": "文件等待解析",
        "PARSING": "文件正在解析",
        "PARSE_FAILED": "文件解析失败",
    }
    available = (
        member.membership_status == "ACTIVE"
        and file.deleted_at is None
        and file.status == "PARSED"
        and member.index_state == "READY"
    )
    unavailable_reason = None
    if not available:
        if file.deleted_at is not None:
            unavailable_reason = "文件位于回收站"
        elif file.status != "PARSED":
            unavailable_reason = reasons.get(file.status, "文件当前不可用")
        elif member.index_state != "READY":
            unavailable_reason = "索引待建立"
    return {
        "knowledge_base_file_id": member.knowledge_base_file_id,
        "file_id": file.file_id,
        "display_name": file.display_name,
        "document_type": file.document_type,
        "file_status": "IN_TRASH" if file.deleted_at is not None else file.status,
        "membership_status": member.membership_status,
        "index_state": member.index_state,
        "available_for_retrieval": available,
        "unavailable_reason": unavailable_reason,
        "added_at": member.added_at,
    }


def _membership_task_payload(task: BackgroundTask) -> dict[str, Any]:
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "phase": task.phase,
        "progress": task.progress,
        "knowledge_base_id": str(checkpoint.get("knowledge_base_id", "")),
        "index_version_id": checkpoint.get("index_version_id"),
        "items": checkpoint.get("items", []),
        "results": checkpoint.get("results", []),
        "summary": checkpoint.get("summary"),
        "error": task.error_summary,
    }


def _atomic_update(
    session: Session,
    knowledge_base_id: str,
    expected_version: int,
    values: dict[str, Any],
    *,
    deleted: bool,
) -> KnowledgeBase:
    state = KnowledgeBase.deleted_at.is_not(None) if deleted else KnowledgeBase.deleted_at.is_(None)
    result = session.execute(
        update(KnowledgeBase)
        .where(
            KnowledgeBase.knowledge_base_id == knowledge_base_id,
            state,
            KnowledgeBase.row_version == expected_version,
        )
        .values(**values, row_version=KnowledgeBase.row_version + 1)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        session.rollback()
        current = session.get(KnowledgeBase, knowledge_base_id)
        if current is None or (current.deleted_at is not None) != deleted:
            raise FileApiError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在。", 404)
        raise FileApiError(
            "RESOURCE_VERSION_CONFLICT",
            f"资源已被其他操作更新，当前版本为 {current.row_version}，请刷新后重试。",
            412,
            current_row_version=current.row_version,
        )
    session.commit()
    session.expire_all()
    updated = session.get(KnowledgeBase, knowledge_base_id)
    if updated is None:
        raise FileApiError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在。", 404)
    return updated


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse, tags=["knowledge-bases"])
def list_knowledge_bases(session: Session = Depends(get_session)) -> dict[str, Any]:
    records = session.scalars(
        select(KnowledgeBase)
        .where(KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.knowledge_base_id.desc())
    )
    return {"items": [_payload(session, record) for record in records], "next_cursor": None}


@router.post(
    "/knowledge-bases",
    status_code=201,
    response_model=KnowledgeBaseResponse,
    tags=["knowledge-bases"],
)
def create_knowledge_base(
    payload: KnowledgeBaseCreate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    now = utc_now()
    record = KnowledgeBase(
        knowledge_base_id=new_id(),
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
        color=payload.color,
        status="EMPTY",
        created_at=now,
        updated_at=now,
        row_version=1,
    )
    session.add(record)
    session.commit()
    return _payload(session, record)


@router.get(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    tags=["knowledge-bases"],
)
def get_knowledge_base(
    knowledge_base_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return _payload(session, _get(session, knowledge_base_id))


@router.get(
    "/knowledge-bases/{knowledge_base_id}/files",
    response_model=KnowledgeBaseMemberListResponse,
    tags=["knowledge-bases"],
)
def list_knowledge_base_files(
    knowledge_base_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _get(session, knowledge_base_id)
    rows = session.execute(
        select(KnowledgeBaseFile, FileRecord)
        .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
        .where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
        )
        .order_by(KnowledgeBaseFile.added_at.desc())
    ).all()
    return {"items": [_member_payload(member, file) for member, file in rows]}


@router.post(
    "/knowledge-bases/{knowledge_base_id}/files",
    status_code=202,
    response_model=KnowledgeMembershipTaskResponse,
    tags=["knowledge-bases"],
)
def add_knowledge_base_files(
    knowledge_base_id: str,
    payload: KnowledgeBaseFilesAdd,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _get(session, knowledge_base_id)
    unique_file_ids = list(dict.fromkeys(payload.file_ids))
    request_time = utc_now()
    raw_key = request.headers.get("idempotency-key", "")
    idempotency_key = "kb-members:" + sha256(
        f"{knowledge_base_id}:{raw_key}".encode()
    ).hexdigest()
    task = create_task(
        session,
        KNOWLEDGE_MEMBERSHIP_TASK,
        idempotency_key,
        {
            "knowledge_base_id": knowledge_base_id,
            "items": [
                {"file_id": file_id, "requested_at": request_time.isoformat()}
                for file_id in unique_file_ids
            ],
            "results": [],
        },
    )
    if task.task_type != KNOWLEDGE_MEMBERSHIP_TASK:
        raise FileApiError("IDEMPOTENCY_CONFLICT", "幂等键已用于其他操作。", 409)
    session.commit()
    return _membership_task_payload(task)


@router.delete(
    "/knowledge-bases/{knowledge_base_id}/files/{file_id}",
    tags=["knowledge-bases"],
)
def remove_knowledge_base_file(
    knowledge_base_id: str,
    file_id: str,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    knowledge_base = _get(session, knowledge_base_id)
    membership = session.scalar(
        select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.file_id == file_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
        )
    )
    if membership is None:
        raise FileApiError("KNOWLEDGE_BASE_MEMBER_NOT_FOUND", "知识库成员不存在。", 404)
    now = utc_now()
    membership.membership_status = "REMOVED"
    membership.index_state = "PENDING"
    membership.removed_at = now
    remaining = session.scalar(
        select(KnowledgeBaseFile.knowledge_base_file_id)
        .where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
            KnowledgeBaseFile.file_id != file_id,
        )
        .limit(1)
    )
    knowledge_base.status = "PREPARING" if remaining is not None else "EMPTY"
    knowledge_base.updated_at = now
    knowledge_base.row_version += 1
    session.commit()
    return {"knowledge_base_id": knowledge_base_id, "file_id": file_id, "status": "REMOVED"}


@router.get(
    "/files/{file_id}/knowledge-bases",
    response_model=KnowledgeBaseListResponse,
    tags=["knowledge-bases"],
)
def list_file_knowledge_bases(
    file_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    if session.get(FileRecord, file_id) is None:
        raise FileApiError("FILE_NOT_FOUND", "文件不存在。", 404)
    records = session.scalars(
        select(KnowledgeBase)
        .join(
            KnowledgeBaseFile,
            KnowledgeBaseFile.knowledge_base_id == KnowledgeBase.knowledge_base_id,
        )
        .where(
            KnowledgeBaseFile.file_id == file_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
            KnowledgeBase.deleted_at.is_(None),
        )
        .order_by(KnowledgeBase.updated_at.desc())
    )
    return {"items": [_payload(session, record) for record in records], "next_cursor": None}


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=KnowledgeMembershipTaskResponse,
    tags=["tasks"],
)
def cancel_knowledge_membership_task(
    task_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    task = session.get(BackgroundTask, task_id)
    cancellable_types = {
        KNOWLEDGE_MEMBERSHIP_TASK,
        INDEX_PREPROCESS_TASK,
        CHUNK_GENERATION_TASK,
        INDEX_EMBED_TASK,
    }
    if task is None or task.task_type not in cancellable_types:
        raise FileApiError("TASK_NOT_FOUND", "任务不存在。", 404)
    cancel_task(session, task)
    session.commit()
    return _membership_task_payload(task)


@router.patch(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["knowledge-bases"],
)
def patch_knowledge_base(
    knowledge_base_id: str,
    payload: KnowledgeBasePatch,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    values = payload.model_dump(exclude={"row_version"}, exclude_unset=True)
    values["updated_at"] = utc_now()
    record = _atomic_update(session, knowledge_base_id, payload.row_version, values, deleted=False)
    return _payload(session, record)


@router.delete(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["knowledge-bases"],
)
def trash_knowledge_base(
    knowledge_base_id: str,
    expected_version: int = Query(ge=1),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    now = utc_now()
    record = _atomic_update(
        session,
        knowledge_base_id,
        expected_version,
        {"deleted_at": now, "purge_after": now + timedelta(days=30), "updated_at": now},
        deleted=False,
    )
    return _payload(session, record)


@router.get(
    "/trash/knowledge-bases",
    response_model=KnowledgeBaseListResponse,
    tags=["knowledge-bases"],
)
def list_trashed_knowledge_bases(session: Session = Depends(get_session)) -> dict[str, Any]:
    records = session.scalars(
        select(KnowledgeBase)
        .where(KnowledgeBase.deleted_at.is_not(None))
        .order_by(KnowledgeBase.deleted_at.desc())
    )
    return {"items": [_payload(session, record) for record in records], "next_cursor": None}


@router.post(
    "/trash/knowledge-base/{knowledge_base_id}/restore",
    response_model=KnowledgeBaseResponse,
    responses=VERSION_CONFLICT_RESPONSES,
    tags=["knowledge-bases"],
)
def restore_knowledge_base(
    knowledge_base_id: str,
    expected_version: int = Query(ge=1),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = _get(session, knowledge_base_id, deleted=True)
    restored_status = "EMPTY" if _counts(session, knowledge_base_id)[0] == 0 else "NEEDS_REBUILD"
    record = _atomic_update(
        session,
        knowledge_base_id,
        expected_version,
        {
            "deleted_at": None,
            "purge_after": None,
            "status": restored_status,
            "updated_at": utc_now(),
        },
        deleted=True,
    )
    return _payload(session, record)


@router.delete("/trash/knowledge-base/{knowledge_base_id}", tags=["knowledge-bases"])
def purge_knowledge_base(
    knowledge_base_id: str,
    request: Request,
    expected_version: int = Query(ge=1),
    confirmed: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    if not confirmed:
        raise FileApiError("PURGE_CONFIRMATION_REQUIRED", "永久删除需要明确确认。", 409)
    record = _get(session, knowledge_base_id, deleted=True)
    if record.row_version != expected_version:
        raise FileApiError(
            "RESOURCE_VERSION_CONFLICT",
            f"资源已被其他操作更新，当前版本为 {record.row_version}，请刷新后重试。",
            412,
            current_row_version=record.row_version,
        )
    versions = list(
        session.execute(
            select(IndexVersion.index_version_id, IndexVersion.embedding_config_id).where(
                IndexVersion.scope_type == "KNOWLEDGE_BASE",
                IndexVersion.scope_id == knowledge_base_id,
            )
        ).all()
    )
    store = SqliteVecAdapter(request.app.state.settings.vectors_dir)
    try:
        for version_id, config_id in versions:
            store.delete_version(config_id, version_id)
    except VectorStoreError:
        raise FileApiError(
            "VECTOR_CLEANUP_FAILED",
            "知识库向量产物清理未完成，知识库仍保留在回收站；请检查本地数据目录后重试。",
            503,
        ) from None
    session.execute(
        delete(IndexVersionInput).where(
            IndexVersionInput.index_version_id.in_(
                select(IndexVersion.index_version_id).where(
                    IndexVersion.scope_id == knowledge_base_id,
                    IndexVersion.scope_type == "KNOWLEDGE_BASE",
                )
            )
        )
    )
    session.execute(
        delete(IndexVersion).where(
            IndexVersion.scope_id == knowledge_base_id,
            IndexVersion.scope_type == "KNOWLEDGE_BASE",
        )
    )
    session.execute(
        delete(KnowledgeBaseFile).where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id
        )
    )
    session.delete(record)
    session.commit()
    return {"knowledge_base_id": knowledge_base_id, "status": "PURGED"}
