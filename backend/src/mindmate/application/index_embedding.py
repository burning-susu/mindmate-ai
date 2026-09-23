from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from mindmate.ai.embeddings.manifest import MODEL_ARTIFACT_FINGERPRINT, MODEL_REVISION
from mindmate.application.index_preprocessing import fingerprint
from mindmate.application.tasks import create_task
from mindmate.infrastructure.models import EmbeddingConfig, IndexVersion

INDEX_EMBED_TASK = "INDEX_EMBED"
EMBEDDING_CONFIG_VERSION = "bge-small-zh-v1"


def embedding_config_payload(config: EmbeddingConfig) -> dict[str, Any]:
    return {
        "config_version": config.config_version,
        "provider_type": config.provider_type,
        "model_name": config.model_name,
        "model_revision": config.model_revision,
        "vector_dimension": config.vector_dimension,
        "normalization": config.normalization,
        "distance_metric": config.distance_metric,
    }


def validate_embedding_config(config: EmbeddingConfig) -> bool:
    payload = embedding_config_payload(config)
    return (
        config.config_version == EMBEDDING_CONFIG_VERSION
        and config.provider_type == "LOCAL_ONNX"
        and config.model_name == "BAAI/bge-small-zh-v1.5"
        and config.model_revision == MODEL_REVISION
        and config.vector_dimension == 512
        and config.normalization is True
        and config.distance_metric == "COSINE"
        and config.config_fingerprint == fingerprint(payload)
    )


def enqueue_index_embedding(
    session: Session,
    index_version_id: str,
    idempotency_key: str,
    *,
    retry_failed: bool = False,
):
    """Queue embeddings for one version after preprocessing and chunking have finished."""
    version = session.get(IndexVersion, index_version_id)
    if version is None:
        raise ValueError("索引版本不存在。")
    if version.status != "BUILDING":
        raise ValueError("只有仍处于 BUILDING 的索引版本可以生成 Embedding。")
    if version.preprocessing_status not in {"COMPLETED", "PARTIAL"}:
        raise ValueError("索引输入快照尚未完成。")
    if version.chunking_status not in {"COMPLETED", "PARTIAL"}:
        raise ValueError("Chunk 生成尚未完成。")
    config = session.get(EmbeddingConfig, version.embedding_config_id)
    if config is None or not validate_embedding_config(config):
        raise ValueError("Embedding 配置未通过固定模型与 tokenizer 指纹校验。")
    return create_task(
        session,
        INDEX_EMBED_TASK,
        idempotency_key,
        {
            "schema_version": 1,
            "index_version_id": index_version_id,
            "knowledge_base_id": version.scope_id,
            "embedding_config_id": version.embedding_config_id,
            "embedding_config_fingerprint": config.config_fingerprint,
            "model_revision": MODEL_REVISION,
            "tokenizer_fingerprint": MODEL_ARTIFACT_FINGERPRINT,
            "retry_failed": retry_failed,
            "next_ordinal": 0,
            "results": [],
        },
    )
