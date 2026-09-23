from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from mindmate.application.tasks import create_task
from mindmate.infrastructure.models import IndexVersion

INDEX_FTS_TASK = "INDEX_FTS"


def enqueue_index_fts(
    session: Session,
    index_version_id: str,
    idempotency_key: str,
    *,
    retry_failed: bool = False,
    rebuild: bool = False,
):
    """Queue only the FTS projection stage; this does not activate an index."""
    version = session.get(IndexVersion, index_version_id)
    if version is None:
        raise ValueError("索引版本不存在。")
    if version.status != "BUILDING":
        raise ValueError("只有仍处于 BUILDING 的索引版本可以生成 FTS5 投影。")
    if version.chunking_status not in {"COMPLETED", "PARTIAL"}:
        raise ValueError("Chunk 生成尚未完成。")
    return create_task(
        session,
        INDEX_FTS_TASK,
        idempotency_key,
        {
            "schema_version": 1,
            "index_version_id": index_version_id,
            "knowledge_base_id": version.scope_id,
            "chunking_config_id": version.chunking_config_id,
            "retry_failed": retry_failed,
            "rebuild": rebuild,
            "next_ordinal": 0,
            "results": [],
        },
    )


def fts_summary(
    *,
    indexed: int,
    failed: int,
    skipped: int,
    chunks: int,
    status: str,
) -> dict[str, Any]:
    return {
        "indexed": indexed,
        "failed": failed,
        "skipped": skipped,
        "chunks": chunks,
        "retryable": failed > 0,
        "error_code": None,
        "index_status": "BUILDING",
        "fts_status": status,
        "index_ready": False,
        "available_for_retrieval": False,
    }
