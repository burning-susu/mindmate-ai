from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from mindmate.application.index_embedding import validate_embedding_config
from mindmate.infrastructure.models import (
    Chunk,
    EmbeddingConfig,
    EmbeddingRecord,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from mindmate.infrastructure.vector_store import (
    DEFAULT_VECTOR_TOP_K,
    MAX_VECTOR_TOP_K,
    SqliteVecAdapter,
    VectorStoreCandidate,
)


class VectorQueryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class VectorTopKHit:
    """A scope-checked internal vector candidate."""

    chunk_id: str
    file_id: str
    index_version_id: str
    embedding_config_id: str
    vector_store_record_id: str
    distance: float
    score: float
    sqlite_distance: float
    rank: int


class VectorTopKQuery:
    """Read-only use case for the not-yet-public vector retrieval stage."""

    def __init__(self, vector_store: SqliteVecAdapter) -> None:
        self._vector_store = vector_store

    def search(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        index_version_id: str,
        query_vector: NDArray[np.float32] | list[float],
        embedding_config_id: str | None = None,
        k: int = DEFAULT_VECTOR_TOP_K,
    ) -> list[VectorTopKHit]:
        self._validate_top_k(k)
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None or knowledge_base.deleted_at is not None:
            raise VectorQueryError("KNOWLEDGE_BASE_NOT_AVAILABLE")

        version = session.get(IndexVersion, index_version_id)
        if (
            version is None
            or version.scope_type != "KNOWLEDGE_BASE"
            or version.scope_id != knowledge_base_id
            or version.status != "BUILDING"
            or version.vector_engine != "sqlite-vec"
            or version.chunking_status not in {"COMPLETED", "PARTIAL"}
            or version.embedding_status not in {"COMPLETED", "PARTIAL"}
        ):
            raise VectorQueryError("INDEX_VERSION_NOT_AVAILABLE")
        if embedding_config_id is not None and embedding_config_id != version.embedding_config_id:
            raise VectorQueryError("EMBEDDING_CONFIG_MISMATCH")

        config = session.get(EmbeddingConfig, version.embedding_config_id)
        if config is None or not validate_embedding_config(config):
            raise VectorQueryError("EMBEDDING_CONFIG_UNVERIFIED")
        if config.vector_dimension != 512 or not config.normalization or config.distance_metric != "COSINE":
            raise VectorQueryError("EMBEDDING_CONFIG_INCOMPATIBLE")

        scoped_rows = self._scoped_records(session, knowledge_base_id, version, config)
        allowed_record_ids = set(scoped_rows)

        candidates = self._vector_store.search(
            embedding_config_id=config.embedding_config_id,
            index_version_id=version.index_version_id,
            query_vector=query_vector,
            allowed_record_ids=allowed_record_ids,
            k=k,
        )

        hits: list[VectorTopKHit] = []
        for candidate in candidates:
            scoped = scoped_rows.get(candidate.vector_store_record_id)
            if scoped is None:
                continue
            record, chunk, file_record = scoped
            if candidate.chunk_id != record.chunk_id or candidate.vector_hash != record.vector_hash:
                raise VectorQueryError("VECTOR_RECORD_INCONSISTENT")
            cosine_distance = self._cosine_distance(candidate)
            hits.append(
                VectorTopKHit(
                    chunk_id=chunk.chunk_id,
                    file_id=file_record.file_id,
                    index_version_id=version.index_version_id,
                    embedding_config_id=config.embedding_config_id,
                    vector_store_record_id=candidate.vector_store_record_id,
                    distance=cosine_distance,
                    score=1.0 - cosine_distance,
                    sqlite_distance=candidate.distance,
                    rank=0,
                )
            )
        hits.sort(key=lambda hit: (hit.distance, hit.vector_store_record_id))
        return [replace(hit, rank=rank) for rank, hit in enumerate(hits, 1)]

    def query(self, *args: Any, **kwargs: Any) -> list[VectorTopKHit]:
        """Compatibility alias for callers using query terminology."""
        return self.search(*args, **kwargs)

    @staticmethod
    def _scoped_records(
        session: Session,
        knowledge_base_id: str,
        version: IndexVersion,
        config: EmbeddingConfig,
    ) -> dict[str, tuple[EmbeddingRecord, Chunk, FileRecord]]:
        rows = session.execute(
            select(EmbeddingRecord, Chunk, FileRecord)
            .select_from(EmbeddingRecord)
            .join(Chunk, Chunk.chunk_id == EmbeddingRecord.chunk_id)
            .join(
                IndexVersionInput,
                and_(
                    IndexVersionInput.index_version_id == version.index_version_id,
                    IndexVersionInput.file_id == Chunk.file_id,
                    IndexVersionInput.parse_revision_id == Chunk.parse_revision_id,
                ),
            )
            .join(
                KnowledgeBaseFile,
                and_(
                    KnowledgeBaseFile.knowledge_base_file_id
                    == IndexVersionInput.knowledge_base_file_id,
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.file_id == IndexVersionInput.file_id,
                ),
            )
            .join(FileRecord, FileRecord.file_id == Chunk.file_id)
            .where(
                EmbeddingRecord.embedding_config_id == config.embedding_config_id,
                EmbeddingRecord.config_fingerprint == config.config_fingerprint,
                EmbeddingRecord.status == "READY",
                EmbeddingRecord.invalidated_at.is_(None),
                EmbeddingRecord.vector_hash.is_not(None),
                Chunk.invalidated_at.is_(None),
                Chunk.chunking_config_id == version.chunking_config_id,
                IndexVersionInput.status == "PREPARED",
                IndexVersionInput.chunk_status == "CHUNKED",
                IndexVersionInput.embedding_status == "EMBEDDED",
                IndexVersionInput.content_hash == FileRecord.content_hash,
                IndexVersionInput.parse_revision_id == FileRecord.parse_revision_id,
                IndexVersionInput.membership_added_at == KnowledgeBaseFile.added_at,
                KnowledgeBaseFile.membership_status == "ACTIVE",
                FileRecord.deleted_at.is_(None),
                FileRecord.status == "PARSED",
            )
        ).all()
        return {
            record.vector_store_record_id: (record, chunk, file_record)
            for record, chunk, file_record in rows
        }

    @staticmethod
    def _cosine_distance(candidate: VectorStoreCandidate) -> float:
        if not math.isfinite(candidate.distance) or candidate.distance < 0:
            raise VectorQueryError("VECTOR_RECORD_INCONSISTENT")
        # Existing version stores use sqlite-vec's default L2 metric. Since both
        # vectors are unit-normalized, d_l2^2 / 2 is cosine distance.
        distance = min(2.0, max(0.0, (candidate.distance * candidate.distance) / 2.0))
        return distance

    @staticmethod
    def _validate_top_k(k: int) -> None:
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_VECTOR_TOP_K:
            raise VectorQueryError("VECTOR_TOP_K_INVALID")


def query_vector_top_k(
    session: Session,
    vector_store: SqliteVecAdapter,
    *,
    knowledge_base_id: str,
    index_version_id: str,
    query_vector: NDArray[np.float32] | list[float],
    embedding_config_id: str | None = None,
    k: int = DEFAULT_VECTOR_TOP_K,
) -> list[VectorTopKHit]:
    """Functional entry point for internal retrieval callers and tests."""
    return VectorTopKQuery(vector_store).search(
        session,
        knowledge_base_id=knowledge_base_id,
        index_version_id=index_version_id,
        query_vector=query_vector,
        embedding_config_id=embedding_config_id,
        k=k,
    )
