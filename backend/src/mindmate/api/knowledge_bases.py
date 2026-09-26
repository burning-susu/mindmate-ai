from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from mindmate.ai.embeddings.model_manager import ModelManager, ModelStatus
from mindmate.api.files import VERSION_CONFLICT_RESPONSES, FileApiError
from mindmate.application.chunking import CHUNK_GENERATION_TASK
from mindmate.application.embedding_model_install import EMBEDDING_MODEL_INSTALL_TASK
from mindmate.application.evidence_gate import unavailable_assessment
from mindmate.application.files import normalize_name, utc_now
from mindmate.application.hybrid_search import (
    DEFAULT_HYBRID_RANKING_CONFIG,
    RANKING_ALGORITHM_VERSION,
    HybridCandidate,
    HybridCandidateQuery,
    HybridQueryError,
)
from mindmate.application.index_embedding import INDEX_EMBED_TASK, validate_embedding_config
from mindmate.application.index_fts import INDEX_FTS_TASK
from mindmate.application.index_preprocessing import (
    INDEX_PREPROCESS_TASK,
    enqueue_index_preprocessing,
)
from mindmate.application.knowledge_membership_worker import KNOWLEDGE_MEMBERSHIP_TASK
from mindmate.application.retrieval_test_queries import RetrievalQueryEncoderError
from mindmate.application.source_snapshots import purge_source_snapshots_for_knowledge_base
from mindmate.application.tasks import cancel_task, create_task
from mindmate.infrastructure.fts5 import Fts5Projection
from mindmate.infrastructure.models import (
    BackgroundTask,
    EmbeddingConfig,
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
MAX_RETRIEVAL_TEST_RESPONSE_BYTES = 64 * 1024


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


class IndexFileFailureResponse(BaseModel):
    file_id: str
    display_name: str
    stage: str
    reason_code: str
    message: str
    retryable: bool
    diagnostic_id: str | None = None


class IndexTaskStatusResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    phase: str | None = None
    progress: int | None = None
    diagnostic_id: str
    message: str | None = None


class IndexFileCountsResponse(BaseModel):
    total: int
    available: int
    processing: int
    failed: int


class KnowledgeBaseIndexStatusResponse(BaseModel):
    knowledge_base_id: str
    status: str
    active_index_version_id: str | None = None
    active_index_version_status: str | None = None
    target_index_version_id: str | None = None
    target_index_version_status: str | None = None
    target_stage: str | None = None
    file_counts: IndexFileCountsResponse
    failures: list[IndexFileFailureResponse]
    tasks: list[IndexTaskStatusResponse]
    embedding_model_state: str
    embedding_model_error_code: str | None = None
    operation_in_progress: bool
    can_retry_failed: bool
    can_rebuild: bool


class RetryFailedIndexRequest(BaseModel):
    file_ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value))
        if len(unique) != len(value):
            raise ValueError("失败文件不能重复。")
        return unique


class RetrievalTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("检索问题不能为空。")
        return normalized


class RetrievalTestLocation(BaseModel):
    sequence_number: int
    heading_path: list[Annotated[str, Field(max_length=160)]] = Field(max_length=8)
    page_start: int | None = None
    page_end: int | None = None
    slide_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    source_kind: str | None = Field(default=None, max_length=30)


class RetrievalTestCandidateResponse(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    chunk_id: str
    file_id: str
    file_name: str = Field(max_length=255)
    location: RetrievalTestLocation
    excerpt: str = Field(max_length=1200)
    rank: int
    fts_rank: int | None = None
    bm25: float | None = None
    vector_rank: int | None = None
    cosine_distance: float | None = None
    cosine_similarity: float | None = None
    rrf_score: float | None = None
    exact_match_bonus: float
    diversity_adjustment: float
    ranking_score: float | None = None
    exact_match_fields: list[Annotated[str, Field(max_length=40)]] = Field(max_length=8)
    ranking_reasons: list[Annotated[str, Field(max_length=80)]] = Field(max_length=8)


class RetrievalTestResponse(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    knowledge_base_id: str
    index_version_id: str | None
    status: Literal["supported", "insufficient", "unavailable"]
    question_type: str = Field(max_length=40)
    ranking_algorithm_version: str = Field(max_length=80)
    evidence_rules_version: str = Field(max_length=80)
    rank_constant: int
    final_candidate_limit: int
    distinct_source_count: int
    reason_codes: list[Annotated[str, Field(max_length=100)]] = Field(max_length=32)
    retrieval_error_code: str | None = Field(default=None, max_length=100)
    retrieval_error_route: Literal["embedding", "scope", "fts", "vector"] | None = None
    candidates: list[RetrievalTestCandidateResponse] = Field(max_length=8)
    local_message: str | None = Field(default=None, max_length=300)
    suggestions: list[Annotated[str, Field(max_length=160)]] = Field(max_length=4)


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


_INDEX_TASK_TYPES = (
    INDEX_PREPROCESS_TASK,
    CHUNK_GENERATION_TASK,
    INDEX_EMBED_TASK,
    INDEX_FTS_TASK,
)
_INDEX_STAGE_FIELDS = (
    ("PREPROCESSING", "status", None),
    ("CHUNKING", "chunk_status", "chunk_reason_code"),
    ("EMBEDDING", "embedding_status", "embedding_reason_code"),
    ("FTS", "fts_status", "fts_reason_code"),
)
_INDEX_REASON_MESSAGES = {
    "PARSE_FAILED": "文件解析失败，请先在文件详情中重新处理文件。",
    "PARSE_REVISION_UNAVAILABLE": "文件解析版本不可用，请重新处理文件后重试。",
    "PARSED_CONTENT_UNAVAILABLE": "已解析内容校验失败，请重新处理文件后重试。",
    "PARSED_TEXT_EMPTY": "文件没有可建立索引的正文，请检查文件内容。",
    "MODEL_MISSING_OFFLINE": "本地 Embedding 模型缺失；当前操作没有触发下载。恢复模型后可重试。",
    "MODEL_ARTIFACT_INVALID": "本地 Embedding 模型校验失败；当前操作没有触发下载。",
    "EMBEDDING_CONFIG_INVALID": "Embedding 配置未通过校验，请检查本地模型配置后重试。",
    "CHUNK_WRITE_RACE": "切片保存时数据发生变化，可以重试失败文件。",
    "FTS_WRITE_RACE": "关键词索引写入时数据发生变化，可以重试失败文件。",
    "KNOWLEDGE_BASE_IN_TRASH": "知识库已进入回收站，索引任务已跳过。",
    "FILE_IN_TRASH": "文件已进入回收站，无法加入当前索引。",
}


def _safe_index_reason(value: str | None) -> str:
    if value and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", value):
        return value
    return "INDEX_BUILD_FAILED"


def _index_failure_message(reason_code: str) -> str:
    return _INDEX_REASON_MESSAGES.get(
        reason_code,
        "索引阶段未完成。可重试失败文件；如果问题持续，请重建当前知识库并记录诊断 ID。",
    )


def _embedding_model_status(request: Request) -> ModelStatus:
    status = getattr(request.app.state, "embedding_model_status", None)
    if status is None:
        # ModelManager verifies file hashes; task polling must not rehash the model each time.
        status = ModelManager(request.app.state.settings.model_dir).status(offline=True)
        request.app.state.embedding_model_status = status
    return status


def _index_status_payload(
    session: Session,
    record: KnowledgeBase,
    request: Request,
) -> dict[str, Any]:
    knowledge_base_id = record.knowledge_base_id
    members = session.execute(
        select(KnowledgeBaseFile, FileRecord)
        .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
        .where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
            FileRecord.deleted_at.is_(None),
        )
    ).all()
    member_by_file = {file.file_id: (member, file) for member, file in members}
    versions = list(
        session.scalars(
            select(IndexVersion)
            .where(
                IndexVersion.scope_type == "KNOWLEDGE_BASE",
                IndexVersion.scope_id == knowledge_base_id,
            )
            .order_by(IndexVersion.created_at.desc(), IndexVersion.index_version_id.desc())
        )
    )
    active = (
        session.get(IndexVersion, record.active_index_version_id)
        if record.active_index_version_id
        else None
    )
    target = next((version for version in versions if version.status == "BUILDING"), None)
    visible_target = target or (
        versions[0]
        if versions
        and versions[0].index_version_id != record.active_index_version_id
        and versions[0].status in {"FAILED", "SUPERSEDED"}
        else None
    )
    diagnostic_version = visible_target or active or (versions[0] if versions else None)
    task_scope_conditions = [
        BackgroundTask.checkpoint_json["knowledge_base_id"].as_string() == knowledge_base_id
    ]
    relevant_version_ids = {
        version.index_version_id
        for version in (active, visible_target)
        if version is not None
    }
    if relevant_version_ids:
        task_scope_conditions.append(
            BackgroundTask.checkpoint_json["index_version_id"]
            .as_string()
            .in_(relevant_version_ids)
        )
    tasks = list(
        session.scalars(
            select(BackgroundTask)
            .where(
                BackgroundTask.task_type.in_((*_INDEX_TASK_TYPES, KNOWLEDGE_MEMBERSHIP_TASK)),
                or_(*task_scope_conditions),
            )
            .order_by(BackgroundTask.created_at.desc(), BackgroundTask.task_id.desc())
            .limit(64)
        )
    )
    relevant_tasks = tasks
    task_by_version_and_type: dict[tuple[str, str], BackgroundTask] = {}
    for task in relevant_tasks:
        checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
        version_id = checkpoint.get("index_version_id")
        if isinstance(version_id, str):
            key = (version_id, task.task_type)
            current = task_by_version_and_type.get(key)
            if current is None or (task.created_at, task.task_id) > (
                current.created_at,
                current.task_id,
            ):
                task_by_version_and_type[key] = task

    version_inputs: list[IndexVersionInput] = []
    if diagnostic_version is not None:
        version_inputs = list(
            session.scalars(
                select(IndexVersionInput).where(
                    IndexVersionInput.index_version_id == diagnostic_version.index_version_id
                )
            )
        )
    failures_by_file: dict[str, dict[str, Any]] = {}
    for item in version_inputs:
        if item.file_id not in member_by_file:
            continue
        failure_stage: str | None = None
        reason: str | None = None
        if item.status == "FAILED":
            failure_stage, reason = "PREPROCESSING", item.reason_code
        else:
            for stage, state_field, reason_field in _INDEX_STAGE_FIELDS[1:]:
                if getattr(item, state_field) == "FAILED":
                    failure_stage = stage
                    reason = getattr(item, reason_field) if reason_field else None
                    break
        if failure_stage is not None and diagnostic_version is not None:
            task_type = {
                "PREPROCESSING": INDEX_PREPROCESS_TASK,
                "CHUNKING": CHUNK_GENERATION_TASK,
                "EMBEDDING": INDEX_EMBED_TASK,
                "FTS": INDEX_FTS_TASK,
            }[failure_stage]
            diagnostic_task = task_by_version_and_type.get(
                (diagnostic_version.index_version_id, task_type)
            )
            reason_code = _safe_index_reason(reason)
            failures_by_file[item.file_id] = {
                "stage": failure_stage,
                "reason_code": reason_code,
                "diagnostic_id": diagnostic_task.task_id if diagnostic_task else None,
            }

    for member, file in members:
        if file.deleted_at is not None:
            continue
        if file.status == "PARSE_FAILED" and file.file_id not in failures_by_file:
            failures_by_file[file.file_id] = {
                "stage": "PARSING",
                "reason_code": "PARSE_FAILED",
                "diagnostic_id": None,
            }
        elif member.index_state == "FAILED" and file.file_id not in failures_by_file:
            failures_by_file[file.file_id] = {
                "stage": "INDEXING",
                "reason_code": "INDEX_BUILD_FAILED",
                "diagnostic_id": None,
            }

    failures = []
    for file_id, failure in failures_by_file.items():
        member, file = member_by_file[file_id]
        reason_code = str(failure["reason_code"])
        failures.append(
            {
                "file_id": file_id,
                "display_name": file.display_name,
                "stage": str(failure["stage"]),
                "reason_code": reason_code,
                "message": _index_failure_message(reason_code),
                "retryable": file.deleted_at is None and file.status == "PARSED",
                "diagnostic_id": failure["diagnostic_id"],
            }
        )
    failures.sort(key=lambda item: (item["display_name"].casefold(), item["file_id"]))

    available_ids = {
        file.file_id
        for member, file in members
        if member.index_state == "READY" and file.deleted_at is None and file.status == "PARSED"
    }
    failed_ids = set(failures_by_file)
    processing_ids = {
        file.file_id
        for member, file in members
        if (
            file.deleted_at is None
            and (
                file.status in {"QUEUED", "PARSING"}
                or (
                    member.index_state in {"PENDING", "PROCESSING"}
                    and file.status != "PARSE_FAILED"
                )
            )
        )
    }
    if target is not None:
        for item in version_inputs:
            if item.file_id not in member_by_file or item.file_id in failed_ids:
                continue
            if item.status in {"PENDING", "RUNNING"} or any(
                getattr(item, field) in {"PENDING", "RUNNING"}
                for _stage, field, _reason in _INDEX_STAGE_FIELDS[1:]
            ):
                processing_ids.add(item.file_id)
    processing_ids.difference_update(failed_ids)
    active_index_tasks = [
        task
        for task in relevant_tasks
        if task.task_type in _INDEX_TASK_TYPES
        and task.status in {"QUEUED", "RUNNING", "INTERRUPTED"}
    ]
    membership_task_running = any(
        task.task_type == KNOWLEDGE_MEMBERSHIP_TASK
        and task.status in {"QUEUED", "RUNNING", "INTERRUPTED"}
        for task in relevant_tasks
    )
    operation_in_progress = bool(active_index_tasks or membership_task_running or target)

    if not members:
        status = "EMPTY"
    elif len(available_ids) == len(members):
        status = "READY"
    elif available_ids:
        status = "PARTIAL"
    elif operation_in_progress or processing_ids:
        status = "PREPARING"
    elif len(failed_ids) >= len(members):
        status = "FAILED"
    elif record.status == "NEEDS_REBUILD":
        status = "NEEDS_REBUILD"
    else:
        status = "PREPARING"

    target_task = None
    if visible_target is not None:
        target_tasks = [
            task_by_version_and_type[(visible_target.index_version_id, task_type)]
            for task_type in _INDEX_TASK_TYPES
            if (visible_target.index_version_id, task_type) in task_by_version_and_type
        ]
        target_task = next(
            (task for task in target_tasks if task.status in {"QUEUED", "RUNNING", "INTERRUPTED"}),
            None,
        ) or next((task for task in target_tasks if task.status == "FAILED"), None)
    target_stage = target_task.phase if target_task is not None else None
    if visible_target is not None and target_stage is None:
        for stage, field, _reason in _INDEX_STAGE_FIELDS:
            stage_field = {
                "status": "preprocessing_status",
                "chunk_status": "chunking_status",
                "embedding_status": "embedding_status",
                "fts_status": "fts_status",
            }.get(field, field)
            if getattr(visible_target, stage_field) not in {"COMPLETED", "PARTIAL"}:
                target_stage = stage
                break
        if target_stage is None and visible_target.status in {"FAILED", "SUPERSEDED"}:
            target_stage = visible_target.activation_error_code or "ACTIVATION_FAILED"

    recent_tasks = []
    for task in relevant_tasks[:16]:
        message = None
        if task.status == "FAILED":
            message = "任务失败。展开失败文件查看可安全展示的原因和诊断 ID。"
        elif task.status == "CANCELLED":
            message = "任务已取消。"
        recent_tasks.append(
            {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": task.status,
                "phase": task.phase,
                "progress": task.progress,
                "diagnostic_id": task.task_id,
                "message": message,
            }
        )

    model_status = _embedding_model_status(request)
    return {
        "knowledge_base_id": knowledge_base_id,
        "status": status,
        "active_index_version_id": active.index_version_id if active else None,
        "active_index_version_status": active.status if active else None,
        "target_index_version_id": visible_target.index_version_id if visible_target else None,
        "target_index_version_status": visible_target.status if visible_target else None,
        "target_stage": target_stage,
        "file_counts": {
            "total": len(members),
            "available": len(available_ids),
            "processing": len(processing_ids),
            "failed": len(failed_ids),
        },
        "failures": failures,
        "tasks": recent_tasks,
        "embedding_model_state": model_status.state.value,
        "embedding_model_error_code": model_status.error_code,
        "operation_in_progress": operation_in_progress,
        "can_retry_failed": any(failure["retryable"] for failure in failures)
        and not operation_in_progress,
        "can_rebuild": bool(members) and not operation_in_progress,
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


def _create_index_operation(
    knowledge_base_id: str,
    request: Request,
    session: Session,
    *,
    operation: Literal["RETRY_FAILED_FILES", "REBUILD"],
    file_ids: list[str] | None = None,
) -> dict[str, Any]:
    record = _get(session, knowledge_base_id)
    request_key = request.headers.get("idempotency-key") or new_id()
    idempotency_key = "kb-index-op:" + sha256(
        f"{knowledge_base_id}:{operation}:{request_key}".encode()
    ).hexdigest()
    existing = session.scalar(
        select(BackgroundTask).where(BackgroundTask.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return _membership_task_payload(existing)

    status = _index_status_payload(session, record, request)
    if status["file_counts"]["total"] == 0:
        raise FileApiError("INDEX_INPUT_REQUIRED", "当前知识库没有可用成员，无法建立索引。", 409)
    if status["operation_in_progress"]:
        raise FileApiError(
            "INDEX_OPERATION_IN_PROGRESS",
            "当前知识库已有索引或成员任务正在处理，请等待该任务结束。",
            409,
        )
    if operation == "RETRY_FAILED_FILES":
        retryable = {
            failure["file_id"]
            for failure in status["failures"]
            if failure["retryable"]
        }
        requested = set(file_ids or [])
        if not requested or not requested.issubset(retryable):
            raise FileApiError(
                "INDEX_RETRY_SCOPE_INVALID",
                "只能重试当前知识库中仍有效、已解析且确实失败的成员文件。请刷新失败列表后重试。",
                409,
            )

    task = enqueue_index_preprocessing(
        session,
        knowledge_base_id,
        idempotency_key,
        force_new=True,
        full_rebuild=operation == "REBUILD",
    )
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    task.checkpoint_json = {
        **checkpoint,
        "operation": operation,
        "requested_failed_file_ids": sorted(file_ids or []),
    }
    session.commit()
    return _membership_task_payload(task)


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse, tags=["knowledge-bases"])
def list_knowledge_bases(
    session: Session = Depends(get_session),
    limit: int | None = Query(default=None, ge=1, le=100),
) -> dict[str, Any]:
    statement = (
        select(KnowledgeBase)
        .where(KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.knowledge_base_id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    records = session.scalars(statement)
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
    "/knowledge-bases/{knowledge_base_id}/index-status",
    response_model=KnowledgeBaseIndexStatusResponse,
    tags=["knowledge-bases"],
)
def get_knowledge_base_index_status(
    knowledge_base_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _index_status_payload(session, _get(session, knowledge_base_id), request)


@router.post(
    "/knowledge-bases/{knowledge_base_id}/index/retry-failed",
    status_code=202,
    response_model=KnowledgeMembershipTaskResponse,
    tags=["knowledge-bases"],
)
def retry_failed_knowledge_base_index_files(
    knowledge_base_id: str,
    payload: RetryFailedIndexRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _create_index_operation(
        knowledge_base_id,
        request,
        session,
        operation="RETRY_FAILED_FILES",
        file_ids=payload.file_ids,
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/index/rebuild",
    status_code=202,
    response_model=KnowledgeMembershipTaskResponse,
    tags=["knowledge-bases"],
)
def rebuild_knowledge_base_index(
    knowledge_base_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _create_index_operation(
        knowledge_base_id,
        request,
        session,
        operation="REBUILD",
    )


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
        INDEX_FTS_TASK,
        EMBEDDING_MODEL_INSTALL_TASK,
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
    projection = Fts5Projection()
    for version_id, _config_id in versions:
        projection.delete_version(session, version_id)
    purge_source_snapshots_for_knowledge_base(session, knowledge_base_id)
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


def _retrieval_test_candidate(
    candidate: HybridCandidate,
) -> RetrievalTestCandidateResponse:
    return RetrievalTestCandidateResponse(
        chunk_id=candidate.chunk_id,
        file_id=candidate.file_id,
        file_name=(candidate.file_title or "")[:255],
        location=RetrievalTestLocation(
            sequence_number=(candidate.sequence_number or 0),
            heading_path=[part[:160] for part in candidate.heading_path[:8]],
            page_start=candidate.page_start,
            page_end=candidate.page_end,
            slide_number=candidate.slide_number,
            line_start=candidate.line_start,
            line_end=candidate.line_end,
            source_kind=candidate.source_kind,
        ),
        excerpt=(candidate.content or "")[:1200],
        rank=candidate.ranking_rank or 1,
        fts_rank=candidate.fts_rank,
        bm25=candidate.bm25,
        vector_rank=candidate.vector_rank,
        cosine_distance=candidate.vector_distance,
        cosine_similarity=candidate.vector_score,
        rrf_score=candidate.rrf_score,
        exact_match_bonus=candidate.exact_match_bonus,
        diversity_adjustment=candidate.diversity_adjustment,
        ranking_score=candidate.ranking_score,
        exact_match_fields=list(candidate.exact_match_fields[:8]),
        ranking_reasons=list(candidate.ranking_reasons[:8]),
    )


def _retrieval_error_route(value: str | None) -> Literal["embedding", "scope", "fts", "vector"] | None:
    if value == "embedding" or value == "scope" or value == "fts" or value == "vector":
        return value
    return None


def _retrieval_test_response(
    *,
    knowledge_base_id: str,
    index_version_id: str | None,
    assessment: Any,
    retrieval: Any = None,
    retrieval_error_code: str | None = None,
    retrieval_error_route: Literal["embedding", "scope", "fts", "vector"] | None = None,
) -> RetrievalTestResponse:
    ranking_config = retrieval.ranking_config if retrieval is not None else None
    payload = RetrievalTestResponse(
        knowledge_base_id=knowledge_base_id,
        index_version_id=index_version_id,
        status=assessment.status,
        question_type=assessment.question_type,
        ranking_algorithm_version=(
            retrieval.ranking_algorithm if retrieval is not None else RANKING_ALGORITHM_VERSION
        ),
        evidence_rules_version=assessment.rules_version,
        rank_constant=(
            ranking_config.rank_constant
            if ranking_config is not None
            else DEFAULT_HYBRID_RANKING_CONFIG.rank_constant
        ),
        final_candidate_limit=(
            ranking_config.final_top_k
            if ranking_config is not None
            else DEFAULT_HYBRID_RANKING_CONFIG.final_top_k
        ),
        distinct_source_count=assessment.distinct_source_count,
        reason_codes=list(assessment.reason_codes[:32]),
        retrieval_error_code=retrieval_error_code,
        retrieval_error_route=retrieval_error_route,
        candidates=(
            [_retrieval_test_candidate(item) for item in retrieval.candidates[:8]]
            if retrieval is not None
            else []
        ),
        local_message=assessment.local_message,
        suggestions=list(assessment.suggestions[:4]),
    )
    if len(payload.model_dump_json().encode("utf-8")) > MAX_RETRIEVAL_TEST_RESPONSE_BYTES:
        raise FileApiError(
            "RETRIEVAL_TEST_RESPONSE_TOO_LARGE",
            "检索测试结果超过允许的响应大小。",
            500,
        )
    return payload


@router.post(
    "/knowledge-bases/{knowledge_base_id}/retrieval-tests",
    response_model=RetrievalTestResponse,
    tags=["knowledge-bases"],
)
def create_knowledge_base_retrieval_test(
    knowledge_base_id: str,
    payload: RetrievalTestRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> RetrievalTestResponse:
    knowledge_base = _get(session, knowledge_base_id)
    index_version_id = knowledge_base.active_index_version_id
    if index_version_id is None:
        assessment = unavailable_assessment(
            "INDEX_VERSION_NOT_AVAILABLE", query_text=payload.question
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=None,
            assessment=assessment,
            retrieval_error_code="INDEX_VERSION_NOT_AVAILABLE",
            retrieval_error_route="scope",
        )

    version = session.get(IndexVersion, index_version_id)
    if (
        version is None
        or version.status != "READY"
        or version.scope_type != "KNOWLEDGE_BASE"
        or version.scope_id != knowledge_base_id
        or version.vector_engine != "sqlite-vec"
    ):
        assessment = unavailable_assessment(
            "INDEX_VERSION_NOT_AVAILABLE", query_text=payload.question, route="scope"
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            assessment=assessment,
            retrieval_error_code="INDEX_VERSION_NOT_AVAILABLE",
            retrieval_error_route="scope",
        )
    if version.fts_status not in {"COMPLETED", "PARTIAL"}:
        assessment = unavailable_assessment(
            "FTS_INDEX_NOT_READY", query_text=payload.question, route="fts"
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            assessment=assessment,
            retrieval_error_code="FTS_INDEX_NOT_READY",
            retrieval_error_route="fts",
        )
    if version.embedding_status not in {"COMPLETED", "PARTIAL"}:
        assessment = unavailable_assessment(
            "VECTOR_INDEX_NOT_READY", query_text=payload.question, route="vector"
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            assessment=assessment,
            retrieval_error_code="VECTOR_INDEX_NOT_READY",
            retrieval_error_route="vector",
        )
    config = session.get(EmbeddingConfig, version.embedding_config_id)
    if config is None or not validate_embedding_config(config):
        assessment = unavailable_assessment(
            "EMBEDDING_CONFIG_UNVERIFIED", query_text=payload.question, route="embedding"
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            assessment=assessment,
            retrieval_error_code="EMBEDDING_CONFIG_UNVERIFIED",
            retrieval_error_route="embedding",
        )

    query = HybridCandidateQuery(SqliteVecAdapter(request.app.state.settings.vectors_dir))
    try:
        expected_scope_signature = query.capture_scope_signature(
            session, knowledge_base_id, index_version_id
        )
    except HybridQueryError as error:
        assessment = unavailable_assessment(
            error.code, query_text=payload.question, route="scope"
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            assessment=assessment,
            retrieval_error_code=error.code,
            retrieval_error_route="scope",
        )

    try:
        query_vector = request.app.state.retrieval_query_encoder.embed_query(payload.question)
    except RetrievalQueryEncoderError as error:
        assessment = unavailable_assessment(
            error.code, query_text=payload.question, route="embedding"
        )
        return _retrieval_test_response(
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            assessment=assessment,
            retrieval_error_code=error.code,
            retrieval_error_route="embedding",
        )

    result = query.search_and_assess_with_status(
        session,
        knowledge_base_id=knowledge_base_id,
        index_version_id=index_version_id,
        query_text=payload.question,
        query_vector=query_vector,
        allow_degraded=False,
        expected_scope_signature=expected_scope_signature,
    )
    return _retrieval_test_response(
        knowledge_base_id=knowledge_base_id,
        index_version_id=index_version_id,
        assessment=result.assessment,
        retrieval=result.retrieval,
        retrieval_error_code=result.retrieval_error_code,
        retrieval_error_route=_retrieval_error_route(result.retrieval_error_route),
    )
