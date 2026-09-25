from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from mindmate.infrastructure.models import Chunk, FtsChunkMap

FTS_TABLE = "index_chunk_fts"
DEFAULT_FTS_TOP_K = 30
MAX_FTS_TOP_K = 30
MAX_RAW_FTS_MATCHES = MAX_FTS_TOP_K * 4

# These are query scaffolding rather than facts users are likely to search for.
# They are removed only from the Han-token fallback; the original query is still
# used by the later evidence gate and is never rewritten for display.
_IGNORED_HAN_TOKENS = frozenset(
    {
        "多少",
        "几个",
        "几种",
        "什么",
        "是否",
        "是不是",
        "如何",
        "怎么",
        "怎样",
        "为什么",
        "哪些",
        "哪种",
        "哪个",
        "么是",
        "是什",
        "什叫",
        "叫什",
        "的什",
        "以及",
        "并且",
        "同时",
        "分别",
    }
)
_TRAILING_HAN_PARTICLES = frozenset("吗呢嘛呀啊")


class Fts5Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _is_han(character: str) -> bool:
    point = ord(character)
    return (
        0x3400 <= point <= 0x4DBF
        or 0x4E00 <= point <= 0x9FFF
        or 0xF900 <= point <= 0xFAFF
        or 0x20000 <= point <= 0x2FA1F
    )


def _fields(content: str) -> tuple[str, str, str]:
    bigrams: list[str] = []
    unigrams: list[str] = []
    words: list[str] = []
    index = 0
    while index < len(content):
        if _is_han(content[index]):
            end = index + 1
            while end < len(content) and _is_han(content[end]):
                end += 1
            run = content[index:end]
            unigrams.extend(run)
            bigrams.extend(run[offset : offset + 2] for offset in range(len(run) - 1))
            index = end
            continue
        if content[index].isalnum():
            end = index + 1
            while end < len(content) and content[end].isalnum() and not _is_han(content[end]):
                end += 1
            words.append(content[index:end].casefold())
            index = end
        else:
            index += 1
    return " ".join(bigrams), " ".join(unigrams), " ".join(words)


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def normalize_query(query: str) -> str:
    """Normalize user text without allowing it to become an FTS expression."""
    if not isinstance(query, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", query).split())


@dataclass(frozen=True, slots=True)
class _HanQueryRun:
    bigrams: tuple[str, ...]
    unigrams: tuple[str, ...]


def _query_parts(query: str) -> tuple[tuple[str, ...], tuple[_HanQueryRun, ...]]:
    normalized = normalize_query(query)
    terms: list[str] = []
    runs: list[_HanQueryRun] = []
    index = 0
    while index < len(normalized):
        if _is_han(normalized[index]):
            end = index + 1
            while end < len(normalized) and _is_han(normalized[end]):
                end += 1
            run = normalized[index:end].rstrip("".join(_TRAILING_HAN_PARTICLES))
            if run:
                bigrams = tuple(
                    dict.fromkeys(
                        run[offset : offset + 2]
                        for offset in range(len(run) - 1)
                        if run[offset : offset + 2] not in _IGNORED_HAN_TOKENS
                    )
                )
                # A one-character run needs the auxiliary unigram field. For
                # longer runs, using unigrams as an OR fallback would turn
                # common characters into a whole-corpus query.
                unigrams = (run,) if len(run) == 1 and not bigrams else ()
                if bigrams or unigrams:
                    runs.append(_HanQueryRun(bigrams, unigrams))
            index = end
            continue
        if normalized[index].isalnum():
            end = index + 1
            while (
                end < len(normalized)
                and normalized[end].isalnum()
                and not _is_han(normalized[end])
            ):
                end += 1
            terms.append(normalized[index:end].casefold())
            index = end
            continue
        index += 1
    return tuple(dict.fromkeys(terms)), tuple(runs)


def match_expression(query: str) -> str:
    """Build a bounded, escaped FTS expression for mixed Chinese queries.

    The index stores overlapping Han bigrams as separate tokens. Joining a
    complete Chinese question inside one quoted phrase requires every query
    bigram to occur contiguously in the document, so natural paraphrases never
    reach the keyword channel. Each run is therefore an OR group of its safe
    bigrams, while ASCII words/numbers remain exact AND terms. ``match_version``
    applies a minimum per-run match count after MATCH to keep this fallback from
    becoming a one-common-character whole-corpus query.
    """
    terms, runs = _query_parts(query)
    clauses: list[str] = []
    clauses.extend(f"terms : {_quoted(term)}" for term in terms)
    for run in runs:
        tokens = [
            f"han_bigrams : {_quoted(token)}"
            for token in run.bigrams
        ] or [f"han_unigrams : {_quoted(token)}" for token in run.unigrams]
        clauses.append("(" + " OR ".join(tokens) + ")")
    return " AND ".join(clauses)


def query_debug(query: str) -> dict[str, Any]:
    """Return deterministic query-side token evidence for local diagnostics."""
    terms, runs = _query_parts(query)
    return {
        "normalized_query": normalize_query(query),
        "terms": list(terms),
        "han_runs": [
            {"bigrams": list(run.bigrams), "unigrams": list(run.unigrams)}
            for run in runs
        ],
        "match_expression": match_expression(query),
    }


def _passes_query_filter(row: Any, terms: tuple[str, ...], runs: tuple[_HanQueryRun, ...]) -> bool:
    index_terms = set(str(row["index_terms"] or "").split())
    if any(term not in index_terms for term in terms):
        return False
    strong_identifier = any(any(character.isdigit() for character in term) for term in terms)
    index_bigrams = set(str(row["index_han_bigrams"] or "").split())
    index_unigrams = set(str(row["index_han_unigrams"] or "").split())
    for run in runs:
        if run.bigrams:
            matched = len(index_bigrams.intersection(run.bigrams))
            minimum = 1 if strong_identifier else min(2, len(run.bigrams))
            if matched < minimum:
                return False
        elif run.unigrams and not index_unigrams.intersection(run.unigrams):
            return False
    return True


class Fts5Projection:
    """Versioned FTS5 projection stored transactionally beside its source database."""

    def replace_file(
        self,
        session: Session,
        *,
        index_version_id: str,
        file_id: str,
        parse_revision_id: str,
        chunking_config_id: str,
        chunks: list[Chunk],
    ) -> None:
        self.delete_file(session, index_version_id, file_id)
        mappings = [
            FtsChunkMap(
                index_version_id=index_version_id,
                chunk_id=chunk.chunk_id,
                file_id=file_id,
                parse_revision_id=parse_revision_id,
                chunking_config_id=chunking_config_id,
                content_hash=chunk.content_hash,
            )
            for chunk in chunks
        ]
        session.add_all(mappings)
        session.flush()
        rows: list[dict[str, Any]] = []
        for mapping, chunk in zip(mappings, chunks, strict=True):
            bigrams, unigrams, terms = _fields(chunk.content)
            rows.append(
                {
                    "rowid": mapping.fts_row_id,
                    "content": chunk.content,
                    "han_bigrams": bigrams,
                    "han_unigrams": unigrams,
                    "terms": terms,
                }
            )
        session.execute(
            text(
                f"INSERT INTO {FTS_TABLE} "
                "(rowid, content, han_bigrams, han_unigrams, terms) "
                "VALUES (:rowid, :content, :han_bigrams, :han_unigrams, :terms)"
            ),
            rows,
        )

    def copy_file(
        self,
        session: Session,
        *,
        source_index_version_id: str,
        index_version_id: str,
        file_id: str,
    ) -> int:
        """Copy a verified file projection without rebuilding its FTS fields."""
        source_rows = list(
            session.execute(
                text(
                    f"""
                    SELECT m.chunk_id, m.file_id, m.parse_revision_id,
                           m.chunking_config_id, m.content_hash,
                           f.content, f.han_bigrams, f.han_unigrams, f.terms
                    FROM fts_chunk_map AS m
                    JOIN {FTS_TABLE} AS f ON f.rowid = m.fts_row_id
                    WHERE m.index_version_id = :source_version_id
                      AND m.file_id = :file_id
                    ORDER BY m.fts_row_id
                    """
                ),
                {
                    "source_version_id": source_index_version_id,
                    "file_id": file_id,
                },
            ).mappings()
        )
        if not source_rows:
            return 0
        self.delete_file(session, index_version_id, file_id)
        mappings = [
            FtsChunkMap(
                index_version_id=index_version_id,
                chunk_id=str(row["chunk_id"]),
                file_id=str(row["file_id"]),
                parse_revision_id=str(row["parse_revision_id"]),
                chunking_config_id=str(row["chunking_config_id"]),
                content_hash=str(row["content_hash"]),
            )
            for row in source_rows
        ]
        session.add_all(mappings)
        session.flush()
        rows = [
            {
                "rowid": mapping.fts_row_id,
                "content": row["content"],
                "han_bigrams": row["han_bigrams"],
                "han_unigrams": row["han_unigrams"],
                "terms": row["terms"],
            }
            for mapping, row in zip(mappings, source_rows, strict=True)
        ]
        session.execute(
            text(
                f"INSERT INTO {FTS_TABLE} "
                "(rowid, content, han_bigrams, han_unigrams, terms) "
                "VALUES (:rowid, :content, :han_bigrams, :han_unigrams, :terms)"
            ),
            rows,
        )
        return len(mappings)

    def delete_file(self, session: Session, index_version_id: str, file_id: str) -> int:
        return self._delete(
            session,
            "index_version_id = :version_id AND file_id = :file_id",
            {"version_id": index_version_id, "file_id": file_id},
        )

    def delete_files(self, session: Session, file_ids: list[str]) -> int:
        if not file_ids:
            return 0
        rows = list(
            session.scalars(
                text("SELECT fts_row_id FROM fts_chunk_map WHERE file_id IN :file_ids").bindparams(
                    bindparam("file_ids", expanding=True)
                ),
                {"file_ids": file_ids},
            )
        )
        return self._delete_ids(session, [int(row) for row in rows])

    def delete_version(self, session: Session, index_version_id: str) -> int:
        return self._delete(
            session,
            "index_version_id = :version_id",
            {"version_id": index_version_id},
        )

    def _delete(self, session: Session, where: str, params: dict[str, Any]) -> int:
        row_ids = [
            int(row)
            for row in session.scalars(
                text(f"SELECT fts_row_id FROM fts_chunk_map WHERE {where}"), params
            )
        ]
        return self._delete_ids(session, row_ids)

    @staticmethod
    def _delete_ids(session: Session, row_ids: list[int]) -> int:
        if not row_ids:
            return 0
        session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE rowid = :rowid"),
            [{"rowid": row_id} for row_id in row_ids],
        )
        session.execute(
            text("DELETE FROM fts_chunk_map WHERE fts_row_id = :rowid"),
            [{"rowid": row_id} for row_id in row_ids],
        )
        return len(row_ids)

    def integrity_check(self, session: Session) -> None:
        try:
            session.execute(
                text(f"INSERT INTO {FTS_TABLE}({FTS_TABLE}, rank) VALUES ('integrity-check', 1)")
            )
        except Exception as error:
            raise Fts5Error("FTS_INTEGRITY_CHECK_FAILED") from error

    def consistency_check(self, session: Session, index_version_id: str) -> None:
        mismatch = session.scalar(
            text(
                f"""
                SELECT count(*)
                FROM fts_chunk_map AS m
                LEFT JOIN {FTS_TABLE} AS f ON f.rowid = m.fts_row_id
                LEFT JOIN chunks AS c ON c.chunk_id = m.chunk_id
                WHERE m.index_version_id = :version_id
                  AND (f.rowid IS NULL OR c.chunk_id IS NULL OR f.content != c.content
                       OR c.content_hash != m.content_hash
                       OR c.file_id != m.file_id
                       OR c.parse_revision_id != m.parse_revision_id
                       OR c.chunking_config_id != m.chunking_config_id)
                """
            ),
            {"version_id": index_version_id},
        )
        orphaned = session.scalar(
            text(
                f"""
                SELECT count(*)
                FROM {FTS_TABLE} AS f
                LEFT JOIN fts_chunk_map AS m ON m.fts_row_id = f.rowid
                WHERE m.fts_row_id IS NULL
                """
            )
        )
        if mismatch or orphaned:
            raise Fts5Error("FTS_PROJECTION_INCONSISTENT")

    def rebuild_version(self, session: Session, index_version_id: str) -> int:
        """Recreate only derived rows for a version; callers validate source snapshots first."""
        return self.delete_version(session, index_version_id)

    def match_version(
        self,
        session: Session,
        index_version_id: str,
        query: str,
        limit: int = DEFAULT_FTS_TOP_K,
        *,
        knowledge_base_id: str | None = None,
        require_active_version: bool = False,
    ) -> list[dict[str, Any]]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_FTS_TOP_K
        ):
            raise Fts5Error("FTS_TOP_K_INVALID")
        terms, runs = _query_parts(query)
        expression = match_expression(query)
        if not expression:
            return []
        try:
            rows = list(
                session.execute(
                text(
                    f"""
                    SELECT m.chunk_id, m.file_id, :version_id AS index_version_id,
                           m.parse_revision_id, m.chunking_config_id, m.content_hash,
                           index_chunk_fts.content AS content,
                           index_chunk_fts.han_bigrams AS index_han_bigrams,
                           index_chunk_fts.han_unigrams AS index_han_unigrams,
                           index_chunk_fts.terms AS index_terms,
                           bm25(index_chunk_fts, 0.0, 1.0, 1.0, 1.0) AS score
                    FROM {FTS_TABLE} AS index_chunk_fts
                    JOIN fts_chunk_map AS m ON m.fts_row_id = index_chunk_fts.rowid
                    JOIN index_version_inputs AS i
                      ON i.index_version_id = m.index_version_id
                     AND i.file_id = m.file_id
                     AND i.parse_revision_id = m.parse_revision_id
                    JOIN index_versions AS v ON v.index_version_id = m.index_version_id
                    JOIN knowledge_base_files AS membership
                      ON membership.knowledge_base_file_id = i.knowledge_base_file_id
                    JOIN knowledge_bases AS kb ON kb.knowledge_base_id = v.scope_id
                    JOIN files AS f ON f.file_id = m.file_id
                    JOIN chunks AS c ON c.chunk_id = m.chunk_id
                    WHERE index_chunk_fts MATCH :query
                      AND m.index_version_id = :version_id
                      AND (:knowledge_base_id IS NULL OR v.scope_id = :knowledge_base_id)
                      AND (
                        (:require_active = 1 AND v.status = 'READY'
                         AND kb.active_index_version_id = v.index_version_id)
                        OR (:require_active = 0 AND v.status = 'BUILDING')
                      )
                      AND v.fts_status IN ('COMPLETED', 'PARTIAL')
                      AND i.status = 'PREPARED' AND i.chunk_status = 'CHUNKED'
                      AND i.fts_status = 'INDEXED'
                      AND (:require_active = 0 OR i.embedding_status = 'EMBEDDED')
                      AND membership.membership_status = 'ACTIVE'
                      AND (:require_active = 0 OR membership.index_state = 'READY')
                      AND membership.added_at = i.membership_added_at
                      AND kb.deleted_at IS NULL AND f.deleted_at IS NULL AND f.status = 'PARSED'
                      AND f.content_hash = i.content_hash AND f.parse_revision_id = i.parse_revision_id
                      AND c.invalidated_at IS NULL AND c.content_hash = m.content_hash
                      AND c.content = index_chunk_fts.content
                      AND c.file_id = m.file_id AND c.parse_revision_id = m.parse_revision_id
                      AND c.chunking_config_id = m.chunking_config_id
                      AND m.chunking_config_id = v.chunking_config_id
                     ORDER BY score ASC, m.chunk_id ASC
                     LIMIT :raw_limit
                    """
                ),
                {
                    "query": expression,
                    "version_id": index_version_id,
                    "knowledge_base_id": knowledge_base_id,
                    # The post-MATCH token filter may remove common-token hits;
                    # keep the expansion bounded before returning FTS Top-K.
                    "raw_limit": min(MAX_RAW_FTS_MATCHES, max(limit, limit * 4)),
                    "require_active": int(require_active_version),
                },
                ).mappings()
            )
        except Exception as error:
            if "fts5" in str(error).casefold() or "match" in str(error).casefold():
                raise Fts5Error("FTS_QUERY_FAILED") from error
            raise
        hits: list[dict[str, Any]] = []
        for row in rows:
            if not _passes_query_filter(row, terms, runs):
                continue
            hit = dict(row)
            hit["bm25"] = float(hit["score"])
            hit["fts_rank"] = len(hits) + 1
            hit.pop("index_han_bigrams", None)
            hit.pop("index_han_unigrams", None)
            hit.pop("index_terms", None)
            hits.append(hit)
            if len(hits) >= limit:
                break
        return hits

    @staticmethod
    def count(session: Session, index_version_id: str) -> int:
        return int(
            session.scalar(
                text("SELECT count(*) FROM fts_chunk_map WHERE index_version_id = :version_id"),
                {"version_id": index_version_id},
            )
            or 0
        )
