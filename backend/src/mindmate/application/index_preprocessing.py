from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.application.tasks import create_task
from mindmate.infrastructure.models import ChunkingConfig, EmbeddingConfig

INDEX_PREPROCESS_TASK = "INDEX_PREPROCESS"
CHUNKING_CONFIG_VERSION = "char-v1"
EMBEDDING_CONFIG_VERSION = "bge-small-zh-v1"


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
        # The pinned downloadable revision is a release-time external fact. Null means
        # metadata is reserved but no model was downloaded or validated in this batch.
        "model_revision": None,
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
    """Create an internal preprocessing task without exposing a misleading rebuild API."""
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
