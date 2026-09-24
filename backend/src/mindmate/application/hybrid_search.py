from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.application.evidence_gate import (
    DEFAULT_EVIDENCE_CONFIG,
    EvidenceAssessment,
    EvidenceSufficiencyConfig,
    assess_evidence,
    unavailable_assessment,
)
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
DEFAULT_FINAL_TOP_K = 8
RANKING_ALGORITHM_VERSION = "rrf-exact-diversity-v1"


@dataclass(frozen=True, slots=True)
class HybridRankingConfig:
    """Versioned, bounded local ranking parameters for internal candidates."""

    rank_constant: int = 60
    final_top_k: int = DEFAULT_FINAL_TOP_K
    exact_phrase_bonus: float = 0.002
    exact_term_bonus: float = 0.0004
    max_exact_bonus: float = 0.004
    same_file_penalty: float = 0.001
    adjacent_overlap_penalty: float = 0.0025
    max_diversity_penalty: float = 0.0035
    overlap_threshold: float = 0.6

    def __post_init__(self) -> None:
        scores = (
            self.exact_phrase_bonus,
            self.exact_term_bonus,
            self.max_exact_bonus,
            self.same_file_penalty,
            self.adjacent_overlap_penalty,
            self.max_diversity_penalty,
        )
        if (
            isinstance(self.rank_constant, bool)
            or not isinstance(self.rank_constant, int)
            or self.rank_constant < 1
            or isinstance(self.final_top_k, bool)
            or not isinstance(self.final_top_k, int)
            or not 1 <= self.final_top_k <= DEFAULT_FINAL_TOP_K
            or any(not math.isfinite(value) or value < 0 for value in scores)
            or isinstance(self.overlap_threshold, bool)
            or not math.isfinite(self.overlap_threshold)
            or not 0 <= self.overlap_threshold <= 1
        ):
            raise ValueError("HYBRID_RANKING_CONFIG_INVALID")


DEFAULT_HYBRID_RANKING_CONFIG = HybridRankingConfig()


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
    sequence_number: int | None = None
    file_title: str | None = None
    heading_path: tuple[str, ...] = ()
    rrf_score: float | None = None
    exact_match_bonus: float = 0.0
    exact_match_terms: tuple[str, ...] = ()
    exact_match_fields: tuple[str, ...] = ()
    diversity_adjustment: float = 0.0
    diversity_reasons: tuple[str, ...] = ()
    ranking_score: float | None = None
    ranking_rank: int | None = None
    ranking_reasons: tuple[str, ...] = ()
    fts_error: str | None = None
    vector_error: str | None = None

    @property
    def degraded(self) -> bool:
        return self.fts_error is not None or self.vector_error is not None


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """Candidate output plus explicit route status for internal callers."""

    candidates: tuple[HybridCandidate, ...]
    fts_error: str | None = None
    vector_error: str | None = None
    ranking_algorithm: str | None = None
    ranking_config: HybridRankingConfig | None = None

    @property
    def degraded(self) -> bool:
        return self.fts_error is not None or self.vector_error is not None


@dataclass(frozen=True, slots=True)
class HybridAssessmentResult:
    """Internal retrieval plus a gate decision, or an explicit unavailable result."""

    retrieval: HybridSearchResult | None
    assessment: EvidenceAssessment
    retrieval_error_code: str | None = None
    retrieval_error_route: str | None = None


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


def _normalize_evidence(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    separated = "".join(
        " " if unicodedata.category(character)[0] in {"P", "Z", "S"} else character
        for character in normalized
    )
    return " ".join(separated.split())


def _query_terms(query_text: str) -> tuple[str, ...]:
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", _normalize_evidence(query_text)):
        if token[0].isascii():
            if len(token) >= 2:
                terms.append(token)
        elif len(token) <= 8:
            if len(token) >= 2:
                terms.append(token)
        else:
            terms.extend(token[index : index + 3] for index in range(len(token) - 2))
    return tuple(dict.fromkeys(terms))


def _contains_exact_term(text: str, term: str) -> bool:
    def is_ascii_word(character: str) -> bool:
        return character.isascii() and (character.isalnum() or character == "_")

    start = 0
    while (position := text.find(term, start)) >= 0:
        end = position + len(term)
        if term[0].isascii():
            before_is_word = position > 0 and is_ascii_word(text[position - 1])
            after_is_word = end < len(text) and is_ascii_word(text[end])
            if not before_is_word and not after_is_word:
                return True
        else:
            return True
        start = position + 1
    return False


def _contains_exact_phrase(text: str, phrase: str) -> bool:
    if len(phrase) < 4:
        return False

    def is_ascii_word(character: str) -> bool:
        return character.isascii() and (character.isalnum() or character == "_")

    start = 0
    while (position := text.find(phrase, start)) >= 0:
        end = position + len(phrase)
        before_is_word = position > 0 and is_ascii_word(text[position - 1])
        after_is_word = end < len(text) and is_ascii_word(text[end])
        if not before_is_word and not after_is_word:
            return True
        start = position + 1
    return False


def _exact_match_details(
    candidate: HybridCandidate,
    query_text: str,
    config: HybridRankingConfig,
) -> tuple[float, tuple[str, ...], tuple[str, ...], bool]:
    phrase = _normalize_evidence(query_text)
    terms = _query_terms(query_text)
    fields = {
        "file_title": _normalize_evidence(candidate.file_title or ""),
        "heading": _normalize_evidence(" ".join(candidate.heading_path)),
        "content": _normalize_evidence(candidate.content or ""),
    }
    exact_phrase = any(_contains_exact_phrase(value, phrase) for value in fields.values())
    matches = tuple(
        term for term in terms if any(_contains_exact_term(value, term) for value in fields.values())
    )
    matching_fields = tuple(
        field
        for field, value in fields.items()
        if (exact_phrase and _contains_exact_phrase(value, phrase))
        or any(_contains_exact_term(value, term) for term in matches)
    )
    short_cjk = {term for term in matches if not term[0].isascii() and len(term) == 2}
    term_bonus = sum(
        config.exact_term_bonus * (0.25 if term in short_cjk else 1.0)
        for term in matches
    )
    bonus = min(
        config.max_exact_bonus,
        term_bonus + (config.exact_phrase_bonus if exact_phrase else 0.0),
    )
    return bonus, matches, matching_fields, exact_phrase


def _overlap_coefficient(left: str | None, right: str | None) -> float:
    def grams(value: str | None) -> set[str]:
        text = _normalize_evidence(value or "")
        if not text:
            return set()
        if len(text) < 3:
            return {text}
        return {text[index : index + 3] for index in range(len(text) - 2)}

    left_grams = grams(left)
    right_grams = grams(right)
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / min(len(left_grams), len(right_grams))


def _rrf_score(candidate: HybridCandidate, config: HybridRankingConfig) -> float:
    return sum(
        1.0 / (config.rank_constant + rank)
        for rank in (candidate.fts_rank, candidate.vector_rank)
        if rank is not None
    )


def _base_tie_key(candidate: HybridCandidate) -> tuple[Any, ...]:
    ranks = [rank for rank in (candidate.fts_rank, candidate.vector_rank) if rank is not None]
    return (
        -(candidate.rrf_score or 0.0),
        -candidate.exact_match_bonus,
        min(ranks) if ranks else MAX_CANDIDATE_TOP_K + 1,
        0 if len(ranks) == 2 else 1,
        candidate.fts_rank if candidate.fts_rank is not None else MAX_CANDIDATE_TOP_K + 1,
        candidate.vector_rank if candidate.vector_rank is not None else MAX_CANDIDATE_TOP_K + 1,
        candidate.file_id,
        candidate.sequence_number if candidate.sequence_number is not None else 2**31,
        candidate.chunk_id,
    )


def _diversity_penalty(
    candidate: HybridCandidate,
    selected: Sequence[HybridCandidate],
    config: HybridRankingConfig,
) -> tuple[float, tuple[str, ...]]:
    same_file_count = sum(item.file_id == candidate.file_id for item in selected)
    penalty = min(same_file_count, 2) * config.same_file_penalty
    reasons = ["same_file"] if same_file_count else []
    overlap_matches = [
        _overlap_coefficient(candidate.content, item.content)
        for item in selected
        if item.file_id == candidate.file_id
        and candidate.sequence_number is not None
        and item.sequence_number is not None
        and abs(candidate.sequence_number - item.sequence_number) <= 1
    ]
    highest_overlap = max(overlap_matches, default=0.0)
    if highest_overlap >= config.overlap_threshold:
        penalty += config.adjacent_overlap_penalty
        reasons.append(f"adjacent_overlap:{highest_overlap:.3f}")
    return min(penalty, config.max_diversity_penalty), tuple(reasons)


def rank_candidates(
    candidates: Iterable[HybridCandidate],
    *,
    query_text: str,
    config: HybridRankingConfig = DEFAULT_HYBRID_RANKING_CONFIG,
) -> list[HybridCandidate]:
    """Apply deterministic RRF, bounded exact-match bonuses and soft diversity."""
    prepared: list[HybridCandidate] = []
    for candidate in candidates:
        if (
            candidate.fts_rank is None
            and candidate.vector_rank is None
            or any(
                rank is not None and (isinstance(rank, bool) or rank < 1)
                for rank in (candidate.fts_rank, candidate.vector_rank)
            )
        ):
            raise HybridQueryError("RANKING_CANDIDATE_INVALID")
        rrf = _rrf_score(candidate, config)
        exact_bonus, terms, fields, exact_phrase = _exact_match_details(
            candidate, query_text, config
        )
        reasons = ["RRF_FTS"] if candidate.fts_rank is not None else []
        if candidate.vector_rank is not None:
            reasons.append("RRF_VECTOR")
        if exact_phrase:
            reasons.append("EXACT_PHRASE")
        if terms:
            reasons.append("EXACT_TERM")
        prepared.append(
            replace(
                candidate,
                rrf_score=rrf,
                exact_match_bonus=exact_bonus,
                exact_match_terms=terms,
                exact_match_fields=fields,
                diversity_adjustment=0.0,
                diversity_reasons=(),
                ranking_score=rrf + exact_bonus,
                ranking_rank=None,
                ranking_reasons=tuple(reasons),
            )
        )

    remaining = sorted(prepared, key=_base_tie_key)
    selected: list[HybridCandidate] = []
    while remaining and len(selected) < config.final_top_k:
        scored: list[tuple[tuple[Any, ...], HybridCandidate, float, tuple[str, ...]]] = []
        for candidate in remaining:
            penalty, diversity_reasons = _diversity_penalty(candidate, selected, config)
            adjusted = (candidate.rrf_score or 0.0) + candidate.exact_match_bonus - penalty
            key = (
                -adjusted,
                *_base_tie_key(candidate),
            )
            scored.append((key, candidate, penalty, diversity_reasons))
        _, winner, penalty, diversity_reasons = min(scored, key=lambda item: item[0])
        reasons = (
            *winner.ranking_reasons,
            *(
                "DIVERSITY_SAME_FILE"
                if reason == "same_file"
                else "DIVERSITY_ADJACENT_OVERLAP"
                for reason in diversity_reasons
            ),
        )
        selected.append(
            replace(
                winner,
                diversity_adjustment=-penalty,
                diversity_reasons=diversity_reasons,
                ranking_score=(winner.rrf_score or 0.0) + winner.exact_match_bonus - penalty,
                ranking_rank=len(selected) + 1,
                ranking_reasons=reasons,
            )
        )
        remaining = [candidate for candidate in remaining if candidate.chunk_id != winner.chunk_id]
    return selected


class HybridCandidateQuery:
    """Collect FTS5 and vector Top-K candidates for one immutable version."""

    def __init__(
        self,
        vector_store: SqliteVecAdapter,
        *,
        projection: Fts5Projection | None = None,
        vector_query: _VectorQuery | None = None,
        ranking_config: HybridRankingConfig | None = None,
        evidence_config: EvidenceSufficiencyConfig | None = None,
    ) -> None:
        self._projection = projection or Fts5Projection()
        self._vector_query = vector_query or VectorTopKQuery(vector_store)
        self._ranking_config = ranking_config or DEFAULT_HYBRID_RANKING_CONFIG
        self._evidence_config = evidence_config or DEFAULT_EVIDENCE_CONFIG

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
        candidates = _attach_chunk_context(session, candidates)
        after = self._fresh_scope_signature(session, knowledge_base_id, index_version_id)
        if before != after:
            raise HybridQueryError("RETRIEVAL_SCOPE_CHANGED")
        ranked = rank_candidates(
            candidates,
            query_text=query_text,
            config=self._ranking_config,
        )
        ranked = [
            replace(candidate, fts_error=fts_error, vector_error=vector_error)
            for candidate in ranked
        ]
        return HybridSearchResult(
            tuple(ranked),
            fts_error,
            vector_error,
            RANKING_ALGORITHM_VERSION,
            self._ranking_config,
        )

    def search_and_assess_with_status(
        self,
        session: Session,
        *,
        knowledge_base_id: str,
        index_version_id: str,
        query_text: str,
        query_vector: NDArray[Any] | list[float] | None,
        allow_degraded: bool = False,
        k: int = DEFAULT_CANDIDATE_TOP_K,
    ) -> HybridAssessmentResult:
        """Run the internal Top 8 pipeline, then apply the evidence-only gate."""
        try:
            signature = self._fresh_scope_signature(
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
            if version[5] not in {"COMPLETED", "PARTIAL"}:
                raise HybridQueryError("FTS_INDEX_NOT_READY", route="fts")
            if query_vector is not None and version[6] not in {"COMPLETED", "PARTIAL"}:
                raise HybridQueryError("VECTOR_INDEX_NOT_READY", route="vector")
            retrieval = self.search_with_status(
                session,
                knowledge_base_id=knowledge_base_id,
                index_version_id=index_version_id,
                query_text=query_text,
                query_vector=query_vector,
                allow_degraded=allow_degraded,
                k=k,
            )
        except HybridQueryError as error:
            return HybridAssessmentResult(
                retrieval=None,
                assessment=unavailable_assessment(
                    error.code,
                    query_text=query_text,
                    route=error.route,
                    config=self._evidence_config,
                ),
                retrieval_error_code=error.code,
                retrieval_error_route=error.route,
            )

        assessment = assess_evidence(
            retrieval.candidates,
            query_text=query_text,
            vector_requested=query_vector is not None,
            fts_error=retrieval.fts_error,
            vector_error=retrieval.vector_error,
            config=self._evidence_config,
        )
        return HybridAssessmentResult(retrieval=retrieval, assessment=assessment)

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
                FileRecord.display_name,
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


def _attach_chunk_context(
    session: Session, candidates: Sequence[HybridCandidate]
) -> list[HybridCandidate]:
    if not candidates:
        return []
    expected = {candidate.chunk_id: candidate.file_id for candidate in candidates}
    with Session(
        bind=session.get_bind(), autoflush=False, expire_on_commit=False
    ) as context_session:
        rows = context_session.execute(
            select(
                Chunk.chunk_id,
                Chunk.file_id,
                Chunk.sequence_number,
                Chunk.heading_path,
                Chunk.content,
                Chunk.invalidated_at,
                FileRecord.display_name.label("file_title"),
            )
            .join(FileRecord, FileRecord.file_id == Chunk.file_id)
            .where(Chunk.chunk_id.in_(expected))
        ).mappings()
        contexts = {str(row["chunk_id"]): row for row in rows}
    if contexts.keys() != expected.keys():
        raise HybridQueryError("RETRIEVAL_SCOPE_CHANGED")
    hydrated: list[HybridCandidate] = []
    for candidate in candidates:
        row = contexts[candidate.chunk_id]
        if row["file_id"] != candidate.file_id or row["invalidated_at"] is not None:
            raise HybridQueryError("RETRIEVAL_SCOPE_CHANGED")
        heading_path = row["heading_path"]
        hydrated.append(
            replace(
                candidate,
                content=str(row["content"]),
                sequence_number=int(row["sequence_number"]),
                file_title=str(row["file_title"]),
                heading_path=tuple(
                    item for item in (heading_path or ()) if isinstance(item, str)
                ),
            )
        )
    return hydrated


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
    ranking_config: HybridRankingConfig | None = None,
) -> list[HybridCandidate]:
    """Functional entry point for internal callers and fixed integration tests."""
    return HybridCandidateQuery(vector_store, ranking_config=ranking_config).search(
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
    "DEFAULT_FINAL_TOP_K",
    "DEFAULT_FTS_TOP_K",
    "DEFAULT_HYBRID_RANKING_CONFIG",
    "HybridRankingConfig",
    "DEFAULT_VECTOR_TOP_K",
    "FtsTopKHit",
    "HybridCandidate",
    "HybridCandidateQuery",
    "HybridQueryError",
    "HybridSearchResult",
    "RANKING_ALGORITHM_VERSION",
    "merge_candidates",
    "rank_candidates",
    "query_hybrid_candidates",
]
