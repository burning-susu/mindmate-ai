from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from mindmate.infrastructure.models import Chunk, FtsChunkMap

FTS_TABLE = "index_chunk_fts"


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


def match_expression(query: str) -> str:
    """Build safe FTS5 phrases, using overlapping Han bigrams for short Chinese terms."""
    clauses: list[str] = []
    index = 0
    while index < len(query):
        if _is_han(query[index]):
            end = index + 1
            while end < len(query) and _is_han(query[end]):
                end += 1
            run = query[index:end]
            if len(run) == 1:
                clauses.append(f"han_unigrams : {_quoted(run)}")
            else:
                tokens = " ".join(run[offset : offset + 2] for offset in range(len(run) - 1))
                clauses.append(f"han_bigrams : {_quoted(tokens)}")
            index = end
            continue
        if query[index].isalnum():
            end = index + 1
            while end < len(query) and query[end].isalnum() and not _is_han(query[end]):
                end += 1
            clauses.append(f"terms : {_quoted(query[index:end].casefold())}")
            index = end
        else:
            index += 1
    return " AND ".join(clauses)


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
        self, session: Session, index_version_id: str, query: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        expression = match_expression(query)
        if not expression:
            return []
        try:
            rows = session.execute(
                text(
                    f"""
                    SELECT m.chunk_id, m.file_id, m.parse_revision_id, m.chunking_config_id,
                           m.content_hash, index_chunk_fts.content AS content,
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
                      AND v.status = 'BUILDING'
                      AND v.fts_status IN ('COMPLETED', 'PARTIAL')
                      AND i.status = 'PREPARED' AND i.chunk_status = 'CHUNKED'
                      AND i.fts_status = 'INDEXED'
                      AND membership.membership_status = 'ACTIVE'
                      AND membership.added_at = i.membership_added_at
                      AND kb.deleted_at IS NULL AND f.deleted_at IS NULL AND f.status = 'PARSED'
                      AND f.content_hash = i.content_hash AND f.parse_revision_id = i.parse_revision_id
                      AND c.invalidated_at IS NULL AND c.content_hash = m.content_hash
                      AND c.content = index_chunk_fts.content
                      AND c.file_id = m.file_id AND c.parse_revision_id = m.parse_revision_id
                      AND c.chunking_config_id = m.chunking_config_id
                      AND m.chunking_config_id = v.chunking_config_id
                    ORDER BY score
                    LIMIT :limit
                    """
                ),
                {"query": expression, "version_id": index_version_id, "limit": max(1, min(100, limit))},
            ).mappings()
        except Exception as error:
            if "fts5" in str(error).casefold() or "match" in str(error).casefold():
                raise Fts5Error("FTS_QUERY_FAILED") from error
            raise
        return [dict(row) for row in rows]

    @staticmethod
    def count(session: Session, index_version_id: str) -> int:
        return int(
            session.scalar(
                text("SELECT count(*) FROM fts_chunk_map WHERE index_version_id = :version_id"),
                {"version_id": index_version_id},
            )
            or 0
        )
