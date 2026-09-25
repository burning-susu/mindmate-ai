from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from mindmate.application.hybrid_search import HybridAssessmentResult, HybridCandidate
from mindmate.application.index_embedding import validate_embedding_config
from mindmate.infrastructure.models import (
    Chunk,
    EmbeddingConfig,
    EmbeddingRecord,
    FileRecord,
    FtsChunkMap,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    SourceSnapshot,
    new_id,
)

MAX_SOURCE_EXCERPT_CHARACTERS = 1200
SourceStatus = Literal[
    "AVAILABLE",
    "SOURCE_IN_TRASH",
    "SOURCE_DELETED",
    "SOURCE_VERSION_STALE",
    "SOURCE_OUT_OF_SCOPE",
    "INDEX_VERSION_RETIRED",
    "SOURCE_MAPPING_INVALID",
]


class SourceSnapshotError(RuntimeError):
    """A server-side source snapshot could not be safely created or read."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceSnapshotCreated:
    source_snapshot_id: str
    knowledge_base_id: str
    index_version_id: str
    file_id: str
    chunk_id: str
    binding_status: Literal["UNBOUND"]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SourceSnapshotView:
    source_snapshot_id: str
    knowledge_base_id: str
    index_version_id: str
    file_id: str | None
    chunk_id: str | None
    file_name: str
    file_version: str | None
    parse_revision_id: str | None
    heading_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    slide_number: int | None
    line_start: int | None
    line_end: int | None
    excerpt: str | None
    binding_status: Literal["UNBOUND"]
    source_status: SourceStatus
    can_open_source: bool
    created_at: datetime


def create_source_snapshots(
    session_factory: sessionmaker[Session] | Callable[[], Session],
    *,
    knowledge_base_id: str,
    expected_index_version_id: str,
    result: HybridAssessmentResult,
    created_at: datetime | None = None,
) -> tuple[SourceSnapshotCreated, ...]:
    """Persist only gate-approved candidates, reloading every source field from SQLite."""
    if not isinstance(result, HybridAssessmentResult) or result.assessment.status != "supported":
        raise SourceSnapshotError("EVIDENCE_NOT_SUPPORTED")
    if result.retrieval is None:
        raise SourceSnapshotError("RETRIEVAL_RESULT_REQUIRED")

    retrieval_candidates = {
        candidate.chunk_id: candidate for candidate in result.retrieval.candidates
    }
    approved: list[HybridCandidate] = []
    seen: set[str] = set()
    for signal in result.assessment.signals:
        if not signal.supporting:
            continue
        identity = signal.identity
        candidate = retrieval_candidates.get(identity.chunk_id)
        if (
            candidate is None
            or candidate.file_id != identity.file_id
            or candidate.index_version_id != identity.index_version_id
            or identity.index_version_id != expected_index_version_id
        ):
            raise SourceSnapshotError("RETRIEVAL_EVIDENCE_INVALID")
        if candidate.chunk_id not in seen:
            approved.append(candidate)
            seen.add(candidate.chunk_id)
    if not approved:
        raise SourceSnapshotError("EVIDENCE_NOT_SUPPORTED")

    timestamp = created_at or datetime.now(UTC)
    created: list[SourceSnapshotCreated] = []
    with session_factory() as session:
        with session.begin():
            # The first write serializes this check with activation, membership, and purge writes.
            session.execute(
                update(KnowledgeBase)
                .where(KnowledgeBase.knowledge_base_id == knowledge_base_id)
                .values(row_version=KnowledgeBase.row_version)
            )
            session.expire_all()

            knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
            if knowledge_base is None or knowledge_base.deleted_at is not None:
                raise SourceSnapshotError("RETRIEVAL_SCOPE_CHANGED")
            version = session.get(IndexVersion, expected_index_version_id)
            if version is None:
                raise SourceSnapshotError("INDEX_VERSION_CHANGED")
            if version.scope_type != "KNOWLEDGE_BASE" or version.scope_id != knowledge_base_id:
                raise SourceSnapshotError("RETRIEVAL_SCOPE_CHANGED")
            if (
                knowledge_base.active_index_version_id != expected_index_version_id
                or version.status != "READY"
            ):
                raise SourceSnapshotError("INDEX_VERSION_CHANGED")

            for candidate in approved:
                if candidate.index_version_id != expected_index_version_id:
                    raise SourceSnapshotError("INDEX_VERSION_CHANGED")
                chunk, file_record = _load_current_source(
                    session,
                    knowledge_base_id=knowledge_base_id,
                    version=version,
                    candidate=candidate,
                )
                key = _idempotency_key(
                    knowledge_base_id, expected_index_version_id, chunk.chunk_id
                )
                existing = session.scalar(
                    select(SourceSnapshot).where(SourceSnapshot.idempotency_key == key)
                )
                if existing is not None:
                    created.append(_created_view(existing))
                    continue

                excerpt = chunk.content[:MAX_SOURCE_EXCERPT_CHARACTERS]
                record = SourceSnapshot(
                    source_snapshot_id=new_id(),
                    idempotency_key=key,
                    binding_status="UNBOUND",
                    knowledge_base_id=knowledge_base_id,
                    index_version_id=expected_index_version_id,
                    file_id=file_record.file_id,
                    file_name_snapshot=file_record.display_name,
                    file_version_snapshot=file_record.content_hash,
                    parse_revision_snapshot=chunk.parse_revision_id,
                    chunk_id=chunk.chunk_id,
                    chunk_content_sha256=hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                    heading_path_snapshot=_heading_path(chunk.heading_path),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    slide_number=chunk.slide_number,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    excerpt=excerpt,
                    excerpt_sha256=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                    created_at=timestamp,
                )
                session.add(record)
                session.flush()
                created.append(_created_view(record))
    return tuple(created)


def read_source_snapshot(session: Session, source_snapshot_id: str) -> SourceSnapshotView:
    record = session.get(SourceSnapshot, source_snapshot_id)
    if record is None:
        raise SourceSnapshotError("SOURCE_SNAPSHOT_NOT_FOUND")

    status: SourceStatus
    can_open = False
    if record.source_deleted_at is not None or record.file_id is None:
        status = "SOURCE_DELETED"
    else:
        file_record = session.get(FileRecord, record.file_id)
        if file_record is None:
            status = "SOURCE_DELETED"
        elif file_record.deleted_at is not None:
            status = "SOURCE_IN_TRASH"
        elif (
            file_record.status != "PARSED"
            or file_record.content_hash != record.file_version_snapshot
            or file_record.parse_revision_id != record.parse_revision_snapshot
        ):
            status = "SOURCE_VERSION_STALE"
        else:
            chunk = session.get(Chunk, record.chunk_id) if record.chunk_id else None
            if (
                chunk is None
                or chunk.invalidated_at is not None
                or chunk.file_id != file_record.file_id
                or chunk.parse_revision_id != record.parse_revision_snapshot
                or hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
                != record.chunk_content_sha256
            ):
                status = "SOURCE_MAPPING_INVALID"
            else:
                membership = session.scalar(
                    select(KnowledgeBaseFile).where(
                        KnowledgeBaseFile.knowledge_base_id == record.knowledge_base_id,
                        KnowledgeBaseFile.file_id == record.file_id,
                        KnowledgeBaseFile.membership_status == "ACTIVE",
                    )
                )
                if membership is None:
                    status = "SOURCE_OUT_OF_SCOPE"
                else:
                    knowledge_base = session.get(KnowledgeBase, record.knowledge_base_id)
                    if knowledge_base is None or knowledge_base.deleted_at is not None:
                        status = "SOURCE_OUT_OF_SCOPE"
                    elif knowledge_base.active_index_version_id != record.index_version_id:
                        status = "INDEX_VERSION_RETIRED"
                        can_open = True
                    elif membership.index_state != "READY":
                        status = "SOURCE_OUT_OF_SCOPE"
                    else:
                        index_input = session.scalar(
                            select(IndexVersionInput).where(
                                IndexVersionInput.index_version_id == record.index_version_id,
                                IndexVersionInput.file_id == file_record.file_id,
                            )
                        )
                        if (
                            index_input is None
                            or index_input.knowledge_base_file_id
                            != membership.knowledge_base_file_id
                            or index_input.membership_added_at != membership.added_at
                            or index_input.status != "PREPARED"
                            or index_input.chunk_status != "CHUNKED"
                            or index_input.embedding_status != "EMBEDDED"
                            or index_input.fts_status != "INDEXED"
                        ):
                            status = "SOURCE_MAPPING_INVALID"
                        else:
                            status = "AVAILABLE"
                            can_open = True

    return SourceSnapshotView(
        source_snapshot_id=record.source_snapshot_id,
        knowledge_base_id=record.knowledge_base_id,
        index_version_id=record.index_version_id,
        file_id=record.file_id,
        chunk_id=record.chunk_id,
        file_name=record.file_name_snapshot,
        file_version=record.file_version_snapshot,
        parse_revision_id=record.parse_revision_snapshot,
        heading_path=tuple(_heading_path(record.heading_path_snapshot) or ()),
        page_start=record.page_start,
        page_end=record.page_end,
        slide_number=record.slide_number,
        line_start=record.line_start,
        line_end=record.line_end,
        excerpt=(
            record.excerpt
            if record.source_deleted_at is None and record.file_id is not None
            else None
        ),
        binding_status="UNBOUND",
        source_status=status,
        can_open_source=can_open,
        created_at=record.created_at,
    )


def purge_source_snapshots_for_files(
    session: Session, file_ids: list[str], *, deleted_at: datetime | None = None
) -> None:
    if not file_ids:
        return
    stamp = deleted_at or datetime.now(UTC)
    from mindmate.application.citations import sanitize_citations_for_file_purge

    sanitize_citations_for_file_purge(session, file_ids, deleted_at=stamp)
    empty_excerpt_hash = hashlib.sha256(b"").hexdigest()
    session.execute(
        update(SourceSnapshot)
        .where(SourceSnapshot.file_id.in_(file_ids))
        .values(
            file_id=None,
            chunk_id=None,
            file_version_snapshot=None,
            parse_revision_snapshot=None,
            chunk_content_sha256=None,
            excerpt="",
            excerpt_sha256=empty_excerpt_hash,
            source_deleted_at=stamp,
        )
    )


def purge_source_snapshots_for_knowledge_base(session: Session, knowledge_base_id: str) -> None:
    from mindmate.application.citations import sanitize_citations_for_knowledge_base_purge

    sanitize_citations_for_knowledge_base_purge(session, knowledge_base_id)
    session.execute(
        delete(SourceSnapshot).where(SourceSnapshot.knowledge_base_id == knowledge_base_id)
    )


def _load_current_source(
    session: Session,
    *,
    knowledge_base_id: str,
    version: IndexVersion,
    candidate: HybridCandidate,
) -> tuple[Chunk, FileRecord]:
    chunk = session.get(Chunk, candidate.chunk_id)
    if chunk is None or chunk.invalidated_at is not None:
        raise SourceSnapshotError("SOURCE_INVALID")
    if chunk.file_id != candidate.file_id:
        raise SourceSnapshotError("RETRIEVAL_SCOPE_CHANGED")

    membership = session.scalar(
        select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.file_id == chunk.file_id,
        )
    )
    if membership is None or membership.membership_status != "ACTIVE":
        raise SourceSnapshotError("RETRIEVAL_SCOPE_CHANGED")
    if membership.index_state != "READY":
        raise SourceSnapshotError("RETRIEVAL_SCOPE_CHANGED")

    file_record = session.get(FileRecord, chunk.file_id)
    if file_record is None or file_record.deleted_at is not None or file_record.status != "PARSED":
        raise SourceSnapshotError("SOURCE_INVALID")
    if candidate.content != chunk.content or candidate.file_title != file_record.display_name:
        raise SourceSnapshotError("RETRIEVAL_EVIDENCE_INVALID")

    index_input = session.scalar(
        select(IndexVersionInput).where(
            IndexVersionInput.index_version_id == version.index_version_id,
            IndexVersionInput.file_id == file_record.file_id,
        )
    )
    if index_input is None:
        raise SourceSnapshotError("SOURCE_INVALID")
    if (
        index_input.knowledge_base_file_id != membership.knowledge_base_file_id
        or index_input.membership_added_at != membership.added_at
    ):
        raise SourceSnapshotError("RETRIEVAL_SCOPE_CHANGED")
    if (
        file_record.content_hash != index_input.content_hash
        or file_record.parse_revision_id != index_input.parse_revision_id
        or chunk.parse_revision_id != index_input.parse_revision_id
    ):
        raise SourceSnapshotError("SOURCE_VERSION_CHANGED")
    if (
        index_input.status != "PREPARED"
        or index_input.chunk_status != "CHUNKED"
        or index_input.embedding_status != "EMBEDDED"
        or index_input.fts_status != "INDEXED"
        or chunk.chunking_config_id != version.chunking_config_id
    ):
        raise SourceSnapshotError("SOURCE_INVALID")
    if hashlib.sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.content_hash:
        raise SourceSnapshotError("SOURCE_INVALID")

    fts_mapping = session.scalar(
        select(FtsChunkMap).where(
            FtsChunkMap.index_version_id == version.index_version_id,
            FtsChunkMap.chunk_id == chunk.chunk_id,
            FtsChunkMap.file_id == file_record.file_id,
            FtsChunkMap.parse_revision_id == chunk.parse_revision_id,
            FtsChunkMap.chunking_config_id == chunk.chunking_config_id,
            FtsChunkMap.content_hash == chunk.content_hash,
        )
    )
    embedding_config = session.get(EmbeddingConfig, version.embedding_config_id)
    embedding = session.scalar(
        select(EmbeddingRecord).where(
            EmbeddingRecord.chunk_id == chunk.chunk_id,
            EmbeddingRecord.embedding_config_id == version.embedding_config_id,
            EmbeddingRecord.status == "READY",
            EmbeddingRecord.invalidated_at.is_(None),
        )
    )
    if (
        fts_mapping is None
        or embedding_config is None
        or not validate_embedding_config(embedding_config)
        or embedding is None
        or embedding.config_fingerprint != embedding_config.config_fingerprint
        or embedding.vector_hash is None
    ):
        raise SourceSnapshotError("SOURCE_INVALID")
    return chunk, file_record


def _idempotency_key(knowledge_base_id: str, index_version_id: str, chunk_id: str) -> str:
    identity = "\0".join((knowledge_base_id, index_version_id, chunk_id))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _heading_path(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)]


def _created_view(record: SourceSnapshot) -> SourceSnapshotCreated:
    if record.file_id is None or record.chunk_id is None:
        raise SourceSnapshotError("SOURCE_INVALID")
    return SourceSnapshotCreated(
        source_snapshot_id=record.source_snapshot_id,
        knowledge_base_id=record.knowledge_base_id,
        index_version_id=record.index_version_id,
        file_id=record.file_id,
        chunk_id=record.chunk_id,
        binding_status="UNBOUND",
        created_at=record.created_at,
    )
