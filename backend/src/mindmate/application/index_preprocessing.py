from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.ai.embeddings.manifest import MODEL_REVISION
from mindmate.application.tasks import create_task
from mindmate.infrastructure.models import (
    BackgroundTask,
    ChunkingConfig,
    EmbeddingConfig,
    FileRecord,
    IndexVersion,
    KnowledgeBaseFile,
)

INDEX_PREPROCESS_TASK = "INDEX_PREPROCESS"
CHUNKING_CONFIG_VERSION = "char-v1"
EMBEDDING_CONFIG_VERSION = "bge-small-zh-v1"
INCREMENTAL_REUSE_REASON_PREFIX = "INCREMENTAL_REUSE:"


def reuse_reason(source_version_id: str) -> str:
    """Persist the reusable source version in the existing input reason field."""
    return f"{INCREMENTAL_REUSE_REASON_PREFIX}{source_version_id}"


def reuse_source_version_id(reason_code: str | None) -> str | None:
    if not isinstance(reason_code, str) or not reason_code.startswith(
        INCREMENTAL_REUSE_REASON_PREFIX
    ):
        return None
    value = reason_code[len(INCREMENTAL_REUSE_REASON_PREFIX) :].strip()
    return value or None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_chunking_payload() -> dict[str, Any]:
    # The final decision is character based. Generic size fields plus an explicit unit
    # avoid silently reinterpreting the older target_tokens terminology.
    return {
        "config_version": CHUNKING_CONFIG_VERSION,
        "algorithm_id": "structure-aware-chinese-v1",
        "measurement_unit": "UNICODE_CHARACTER",
        "target_size": 500,
        "min_size": 250,
        "max_size": 800,
        "overlap_size": 80,
        "structure_rules_hash": fingerprint(
            {"headings": True, "paragraphs": True, "tables": True, "code_blocks": True}
        ),
    }


def default_embedding_payload() -> dict[str, Any]:
    return {
        "config_version": EMBEDDING_CONFIG_VERSION,
        "provider_type": "LOCAL_ONNX",
        "model_name": "BAAI/bge-small-zh-v1.5",
        "model_revision": MODEL_REVISION,
        "vector_dimension": 512,
        "normalization": True,
        "distance_metric": "COSINE",
    }


def get_or_create_default_configs(session: Session) -> tuple[ChunkingConfig, EmbeddingConfig]:
    now = datetime.now(UTC)
    chunk_payload = default_chunking_payload()
    chunk_fingerprint = fingerprint(chunk_payload)
    chunking = session.scalar(
        select(ChunkingConfig).where(ChunkingConfig.config_fingerprint == chunk_fingerprint)
    )
    if chunking is None:
        chunking = ChunkingConfig(
            **chunk_payload,
            config_fingerprint=chunk_fingerprint,
            created_at=now,
        )
        session.add(chunking)
        session.flush()

    embedding_payload = default_embedding_payload()
    embedding_fingerprint = fingerprint(embedding_payload)
    embedding = session.scalar(
        select(EmbeddingConfig).where(EmbeddingConfig.config_fingerprint == embedding_fingerprint)
    )
    if embedding is None:
        embedding = EmbeddingConfig(
            **embedding_payload,
            config_fingerprint=embedding_fingerprint,
            created_at=now,
        )
        session.add(embedding)
        session.flush()
    return chunking, embedding


def enqueue_index_preprocessing(
    session: Session, knowledge_base_id: str, idempotency_key: str
):
    """Create one internal preprocessing task for the current KB snapshot.

    A queued/running task (or a completed preprocessing task whose candidate is
    still the current BUILDING version) is returned for duplicate submissions.
    This keeps retries from creating competing candidates while still allowing a
    new task after the membership snapshot has changed.
    """
    existing = session.scalar(
        select(BackgroundTask)
        .where(BackgroundTask.idempotency_key == idempotency_key)
        .limit(1)
    )
    if existing is not None:
        return existing

    current_values = _current_snapshot_values(session, knowledge_base_id)
    current_hash = fingerprint({"inputs": current_values})
    current_chunking_fingerprint = fingerprint(default_chunking_payload())
    current_embedding_fingerprint = fingerprint(default_embedding_payload())

    active_tasks = session.scalars(
        select(BackgroundTask)
        .where(BackgroundTask.task_type == INDEX_PREPROCESS_TASK)
        .order_by(BackgroundTask.created_at.desc())
    )
    for task in active_tasks:
        if task.status in {"QUEUED", "RUNNING", "INTERRUPTED"}:
            checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
            if checkpoint.get("knowledge_base_id") == knowledge_base_id:
                version_id = checkpoint.get("index_version_id")
                version = (
                    session.get(IndexVersion, version_id)
                    if isinstance(version_id, str)
                    else None
                )
                if version is None or (
                    version.parse_revision_set_hash == current_hash
                    and checkpoint.get("chunking_config_fingerprint")
                    == current_chunking_fingerprint
                    and checkpoint.get("embedding_config_fingerprint")
                    == current_embedding_fingerprint
                ):
                    return task
                continue
        if task.status not in {"COMPLETED", "INTERRUPTED"}:
            continue
        checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
        version_id = checkpoint.get("index_version_id")
        if checkpoint.get("knowledge_base_id") != knowledge_base_id or not isinstance(version_id, str):
            continue
        version = session.get(IndexVersion, version_id)
        if version is None or version.status != "BUILDING":
            continue
        if (
            current_hash == version.parse_revision_set_hash
            and checkpoint.get("chunking_config_fingerprint") == current_chunking_fingerprint
            and checkpoint.get("embedding_config_fingerprint") == current_embedding_fingerprint
        ):
            return task

    return create_task(
        session,
        INDEX_PREPROCESS_TASK,
        idempotency_key,
        {
            "schema_version": 1,
            "knowledge_base_id": knowledge_base_id,
            "index_version_id": None,
            "next_ordinal": 0,
            "results": [],
        },
    )


def _current_snapshot_values(session: Session, knowledge_base_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        select(KnowledgeBaseFile, FileRecord)
        .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
        .where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
        )
        .order_by(KnowledgeBaseFile.knowledge_base_file_id)
    ).all()
    return [
        {
            "membership_id": membership.knowledge_base_file_id,
            "file_id": record.file_id,
            "content_hash": record.content_hash,
            "parse_revision_id": record.parse_revision_id,
            "membership_added_at": _as_utc(membership.added_at).isoformat(),
        }
        for membership, record in rows
    ]
