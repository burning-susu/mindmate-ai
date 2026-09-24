from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.application.vector_search import VectorTopKHit, VectorTopKQuery
from mindmate.infrastructure.fts5 import DEFAULT_FTS_TOP_K, Fts5Projection
from mindmate.infrastructure.models import (
    Chunk,
    EmbeddingRecord,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from mindmate.infrastructure.vector_store import DEFAULT_VECTOR_TOP_K, SqliteVecAdapter

DEFAULT_CANDIDATE_TOP_K = 30
MAX_CANDIDATE_TOP_K = 30


class HybridQueryError(RuntimeError):
    """A retrieval route or immutable-scope validation failed."""

    def __init__(self, code: str, *, route: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.route = route


@dataclass(frozen=True, slots=True)
class FtsTopKHit:
    """A scope-checked FTS5 candidate with its original rank and BM25 value."""

    chunk_id: str
    file_id: str
    index_version_id: str
    fts_rank: int
    bm25: float
    content: str | None = None
    parse_revision_id: str | None = None
    chunking_config_id: str | None = None


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    """One chunk after the two retrieval routes have been merged by chunk ID."""

    chunk_id: str
    file_id: str
    index_version_id: str
    fts_rank: int | None = None
    bm25: float | None = None
    vector_rank: int | None = None
    vector_distance: float | None = None
    vector_score: float | None = None
    sqlite_distance: float | None = None
    content: str | None = None
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """Candidate output plus explicit route status for internal callers."""

    candidates: tuple[HybridCandidate, ...]
    fts_error: str | None = None
    vector_error: str | None = None

    @property
    def degraded(self) -> bool:
        return self.fts_error is not None or self.vector_error is not None


class _VectorQuery(Protocol):
    def search(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        index_version_id: str,
        query_vector: NDArray[Any] | list[float],
        k: int,
    ) -> list[VectorTopKHit]: ...


def _validate_top_k(value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_CANDIDATE_TOP_K
    ):
        raise HybridQueryError("CANDIDATE_TOP_K_INVALID")


def _fts_hit(row: FtsTopKHit | dict[str, Any], position: int) -> FtsTopKHit:
    if isinstance(row, FtsTopKHit):
        return row
    try:
        raw_score = row["bm25"] if "bm25" in row else row["score"]
        score = float(raw_score)
        rank = int(row.get("fts_rank", row.get("rank", position)))
        hit = FtsTopKHit(
            chunk_id=str(row["chunk_id"]),
            file_id=str(row["file_id"]),
            index_version_id=str(row["index_version_id"]),
            fts_rank=rank,
            bm25=score,
            content=row.get("content"),
            parse_revision_id=row.get("parse_revision_id"),
            chunking_config_id=row.get("chunking_config_id"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HybridQueryError("FTS_CANDIDATE_INVALID", route="fts") from error
    if hit.fts_rank < 1 or not math.isfinite(hit.bm25):
        raise HybridQueryError("FTS_CANDIDATE_INVALID", route="fts")
    return hit


def _candidate_sort_key(candidate: HybridCandidate) -> tuple[Any, ...]:
    first_rank = min(
        rank for rank in (candidate.fts_rank, candidate.vector_rank) if rank is not None
    )
    both = candidate.fts_rank is not None and candidate.vector_rank is not None
    return (
        first_rank,
        0 if both else 1,
        candidate.fts_rank if candidate.fts_rank is not None else MAX_CANDIDATE_TOP_K + 1,
        candidate.vector_rank
        if candidate.vector_rank is not None
        else MAX_CANDIDATE_TOP_K + 1,
        candidate.chunk_id,
    )


def merge_candidates(
    fts_hits: Iterable[FtsTopKHit | dict[str, Any]],
    vector_hits: Iterable[VectorTopKHit],
) -> list[HybridCandidate]:
    """Merge two already scope-checked routes without manufacturing signals."""
    merged: dict[str, HybridCandidate] = {}
    for position, raw_hit in enumerate(fts_hits, 1):
        hit = _fts_hit(raw_hit, position)
        current = merged.get(hit.chunk_id)
        if current is None:
            merged[hit.chunk_id] = HybridCandidate(
                chunk_id=hit.chunk_id,
                file_id=hit.file_id,
                index_version_id=hit.index_version_id,
                fts_rank=hit.fts_rank,
                bm25=hit.bm25,
                content=hit.content,
                sources=("fts",),
            )
            continue
        if (current.file_id, current.index_version_id) != (
            hit.file_id,
            hit.index_version_id,
        ):
            raise HybridQueryError("CANDIDATE_IDENTITY_MISMATCH")
        if hit.fts_rank < (current.fts_rank or MAX_CANDIDATE_TOP_K + 1):
            merged[hit.chunk_id] = replace(
                current,
                fts_rank=hit.fts_rank,
                bm25=hit.bm25,
                content=hit.content or current.content,
            )

    for hit in vector_hits:
        if hit.rank < 1 or not math.isfinite(hit.distance) or not math.isfinite(hit.score):
            raise HybridQueryError("VECTOR_CANDIDATE_INVALID", route="vector")
        current = merged.get(hit.chunk_id)
        if current is None:
            merged[hit.chunk_id] = HybridCandidate(
                chunk_id=hit.chunk_id,
                file_id=hit.file_id,
                index_version_id=hit.index_version_id,
                vector_rank=hit.rank,
                vector_distance=hit.distance,
                vector_score=hit.score,
                sqlite_distance=hit.sqlite_distance,
                sources=("vector",),
            )
            continue
        if (current.file_id, current.index_version_id) != (hit.file_id, hit.index_version_id):
            raise HybridQueryError("CANDIDATE_IDENTITY_MISMATCH")
        if hit.rank < (current.vector_rank or MAX_CANDIDATE_TOP_K + 1):
            merged[hit.chunk_id] = replace(
                current,
                vector_rank=hit.rank,
                vector_distance=hit.distance,
                vector_score=hit.score,
                sqlite_distance=hit.sqlite_distance,
                sources=tuple(dict.fromkeys((*current.sources, "vector"))),
            )
        elif "vector" not in current.sources:
            merged[hit.chunk_id] = replace(
                current,
                vector_rank=hit.rank,
                vector_distance=hit.distance,
                vector_score=hit.score,
                sqlite_distance=hit.sqlite_distance,
                sources=(*current.sources, "vector"),
            )

    return sorted(merged.values(), key=_candidate_sort_key)


class HybridCandidateQuery:
    """Collect FTS5 and vector Top-K candidates for one immutable version."""

    def __init__(
        self,
        vector_store: SqliteVecAdapter,
        *,
        projection: Fts5Projection | None = None,
        vector_query: _VectorQuery | None = None,
    ) -> None:
        self._projection = projection or Fts5Projection()
        self._vector_query = vector_query or VectorTopKQuery(vector_store)

    def search_with_status(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        index_version_id: str,
        query_text: str,
        query_vector: NDArray[Any] | list[float] | None,
        allow_degraded: bool = False,
        k: int = DEFAULT_CANDIDATE_TOP_K,
    ) -> HybridSearchResult:
        _validate_top_k(k)
        self._validate_version_scope(session, knowledge_base_id, index_version_id)
        before = self._fresh_scope_signature(session, knowledge_base_id, index_version_id)

        fts_rows: list[dict[str, Any]] = []
        fts_error: str | None = None
        try:
            fts_rows = self._projection.match_version(
                session,
                index_version_id,
                query_text,
                limit=k,
                knowledge_base_id=knowledge_base_id,
            )
        except Exception as error:
            fts_error = getattr(error, "code", None)
            if not isinstance(fts_error, str):
                fts_error = "FTS_QUERY_FAILED"
            if not allow_degraded:
                raise HybridQueryError(fts_error, route="fts") from error

        vector_hits: list[VectorTopKHit] = []
        vector_error: str | None = None
        if query_vector is not None:
            try:
                vector_hits = self._vector_query.search(
                    session,
                    knowledge_base_id=knowledge_base_id,
                    index_version_id=index_version_id,
                    query_vector=query_vector,
                    k=k,
                )
            except Exception as error:
                vector_error = getattr(error, "code", None)
                if not isinstance(vector_error, str):
                    vector_error = "VECTOR_QUERY_FAILED"
                if not allow_degraded:
                    raise HybridQueryError(vector_error, route="vector") from error

        after = self._fresh_scope_signature(session, knowledge_base_id, index_version_id)
        if before != after:
            raise HybridQueryError("RETRIEVAL_SCOPE_CHANGED")
        try:
            candidates = merge_candidates(fts_rows, vector_hits)
        except HybridQueryError:
            raise
        return HybridSearchResult(tuple(candidates), fts_error, vector_error)

    def search(self, *args: Any, **kwargs: Any) -> list[HybridCandidate]:
        return list(self.search_with_status(*args, **kwargs).candidates)

    @staticmethod
    def _validate_version_scope(
        session: Session, knowledge_base_id: str, index_version_id: str
    ) -> None:
        signature = HybridCandidateQuery._fresh_scope_signature(
            session, knowledge_base_id, index_version_id
        )
        if signature == (None,):
            raise HybridQueryError("INDEX_VERSION_NOT_AVAILABLE")
        version = signature[0]
        if (
            version[0] != "BUILDING"
            or version[1] != "KNOWLEDGE_BASE"
            or version[2] != knowledge_base_id
            or version[7] is not None
        ):
            raise HybridQueryError("INDEX_VERSION_NOT_AVAILABLE")

    @staticmethod
    def _fresh_scope_signature(
        session: Session, knowledge_base_id: str, index_version_id: str
    ) -> tuple[Any, ...]:
        """Read validation state from a fresh transaction when the DB is shared."""
        bind = session.get_bind()
        with Session(bind=bind, autoflush=False, expire_on_commit=False) as validator:
            return HybridCandidateQuery._scope_signature(
                validator, knowledge_base_id, index_version_id
            )

    @staticmethod
    def _scope_signature(
        session: Session, knowledge_base_id: str, index_version_id: str
    ) -> tuple[Any, ...]:
        version_row = session.execute(
            select(
                IndexVersion.status,
                IndexVersion.scope_type,
                IndexVersion.scope_id,
                IndexVersion.chunking_config_id,
                IndexVersion.embedding_config_id,
                IndexVersion.fts_status,
                IndexVersion.embedding_status,
                KnowledgeBase.deleted_at,
            )
            .join(KnowledgeBase, KnowledgeBase.knowledge_base_id == IndexVersion.scope_id)
            .where(
                IndexVersion.index_version_id == index_version_id,
                IndexVersion.scope_id == knowledge_base_id,
            )
        ).mappings().one_or_none()
        if version_row is None:
            return (None,)

        input_rows = session.execute(
            select(
                IndexVersionInput.file_id,
                IndexVersionInput.knowledge_base_file_id,
                IndexVersionInput.content_hash,
                IndexVersionInput.parse_revision_id,
                IndexVersionInput.membership_added_at,
                IndexVersionInput.status,
                IndexVersionInput.chunk_status,
                IndexVersionInput.embedding_status,
                IndexVersionInput.fts_status,
                KnowledgeBaseFile.membership_status,
                KnowledgeBaseFile.added_at,
                FileRecord.status,
                FileRecord.deleted_at,
                FileRecord.content_hash.label("file_content_hash"),
                FileRecord.parse_revision_id.label("file_parse_revision_id"),
            )
            .join(
                KnowledgeBaseFile,
                KnowledgeBaseFile.knowledge_base_file_id
                == IndexVersionInput.knowledge_base_file_id,
            )
            .join(FileRecord, FileRecord.file_id == IndexVersionInput.file_id)
            .where(
                IndexVersionInput.index_version_id == index_version_id,
                KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            )
        ).all()

        file_ids = [str(row.file_id) for row in input_rows]
        chunk_rows: Sequence[Any] = ()
        embedding_rows: Sequence[Any] = ()
        if file_ids:
            chunk_rows = session.execute(
                select(
                    Chunk.chunk_id,
                    Chunk.file_id,
                    Chunk.parse_revision_id,
                    Chunk.chunking_config_id,
                    Chunk.content_hash,
                    Chunk.invalidated_at,
                ).where(Chunk.file_id.in_(file_ids))
            ).all()
            embedding_rows = session.execute(
                select(
                    EmbeddingRecord.embedding_record_id,
                    EmbeddingRecord.chunk_id,
                    EmbeddingRecord.embedding_config_id,
                    EmbeddingRecord.vector_store_record_id,
                    EmbeddingRecord.vector_hash,
                    EmbeddingRecord.status,
                    EmbeddingRecord.invalidated_at,
                ).where(
                    EmbeddingRecord.embedding_config_id == version_row.embedding_config_id,
                    EmbeddingRecord.chunk_id.in_([str(row.chunk_id) for row in chunk_rows]),
                )
            ).all()

        def normalized(value: Any) -> Any:
            return value.isoformat() if hasattr(value, "isoformat") else value

        return (
            tuple(normalized(version_row[key]) for key in version_row.keys()),
            tuple(
                sorted(
                    (tuple(normalized(value) for value in row) for row in input_rows),
                    key=repr,
                )
            ),
            tuple(
                sorted(
                    (tuple(normalized(value) for value in row) for row in chunk_rows),
                    key=repr,
                )
            ),
            tuple(
                sorted(
                    (tuple(normalized(value) for value in row) for row in embedding_rows),
                    key=repr,
                )
            ),
        )


def query_hybrid_candidates(
    session: Session,
    vector_store: SqliteVecAdapter,
    *,
    knowledge_base_id: str,
    index_version_id: str,
    query_text: str,
    query_vector: NDArray[Any] | list[float] | None,
    allow_degraded: bool = False,
    k: int = DEFAULT_CANDIDATE_TOP_K,
) -> list[HybridCandidate]:
    """Functional entry point for internal callers and fixed integration tests."""
    return HybridCandidateQuery(vector_store).search(
        session,
        knowledge_base_id=knowledge_base_id,
        index_version_id=index_version_id,
        query_text=query_text,
        query_vector=query_vector,
        allow_degraded=allow_degraded,
        k=k,
    )


__all__ = [
    "DEFAULT_CANDIDATE_TOP_K",
    "DEFAULT_FTS_TOP_K",
    "DEFAULT_VECTOR_TOP_K",
    "FtsTopKHit",
    "HybridCandidate",
    "HybridCandidateQuery",
    "HybridQueryError",
    "HybridSearchResult",
    "merge_candidates",
    "query_hybrid_candidates",
]
