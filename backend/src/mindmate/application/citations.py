from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from mindmate.application.source_snapshots import (
    SourceSnapshotCreated,
    SourceSnapshotError,
    read_source_snapshot,
)
from mindmate.infrastructure.models import Citation


class CitationBindingError(RuntimeError):
    """A validated retrieval source could not be bound to an answer version."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def bind_answer_citations(
    session: Session,
    *,
    answer_version_id: str,
    snapshots: Iterable[SourceSnapshotCreated],
    created_at: datetime | None = None,
) -> list[Citation]:
    """Copy only live, server-created snapshots into a durable answer owner."""

    return _bind_citations(
        session,
        snapshots,
        answer_version_id=answer_version_id,
        learning_feedback_id=None,
        created_at=created_at,
    )


def bind_feedback_citations(
    session: Session,
    *,
    learning_feedback_id: str,
    snapshots: Iterable[SourceSnapshotCreated],
    created_at: datetime | None = None,
) -> list[Citation]:
    """Bind the same source snapshots to one learning feedback owner."""

    return _bind_citations(
        session,
        snapshots,
        answer_version_id=None,
        learning_feedback_id=learning_feedback_id,
        created_at=created_at,
    )


def _bind_citations(
    session: Session,
    snapshots: Iterable[SourceSnapshotCreated],
    *,
    answer_version_id: str | None,
    learning_feedback_id: str | None,
    created_at: datetime | None,
) -> list[Citation]:
    if (answer_version_id is None) == (learning_feedback_id is None):
        raise CitationBindingError("CITATION_OWNER_REQUIRED")
    timestamp = created_at or datetime.now(UTC)
    citations: list[Citation] = []
    for display_number, snapshot in enumerate(snapshots, start=1):
        owner_filter = (
            Citation.answer_version_id == answer_version_id
            if answer_version_id is not None
            else Citation.learning_feedback_id == learning_feedback_id
        )
        existing = session.scalar(
            select(Citation).where(owner_filter, Citation.display_number == display_number)
        )
        if existing is not None:
            citations.append(existing)
            continue
        try:
            view = read_source_snapshot(session, snapshot.source_snapshot_id)
        except SourceSnapshotError as exc:
            raise CitationBindingError(exc.code) from exc
        if view.source_status != "AVAILABLE" or not view.can_open_source:
            raise CitationBindingError("SOURCE_INVALID")
        if view.file_id is None or view.chunk_id is None:
            raise CitationBindingError("SOURCE_INVALID")
        record = Citation(
            citation_id=_new_citation_id(),
            answer_version_id=answer_version_id,
            learning_feedback_id=learning_feedback_id,
            source_snapshot_id=view.source_snapshot_id,
            display_number=display_number,
            knowledge_base_id=view.knowledge_base_id,
            index_version_id=view.index_version_id,
            file_id=view.file_id,
            chunk_id=view.chunk_id,
            file_name_snapshot=view.file_name,
            file_version_snapshot=view.file_version,
            heading_path_snapshot=list(view.heading_path),
            page_start=view.page_start,
            page_end=view.page_end,
            slide_number=view.slide_number,
            line_start=view.line_start,
            line_end=view.line_end,
            excerpt=view.excerpt,
            excerpt_sha256=(_sha256(view.excerpt) if view.excerpt is not None else None),
            source_status=view.source_status,
            created_at=timestamp,
        )
        session.add(record)
        citations.append(record)
    session.flush()
    return citations


def citation_payload(session: Session, record: Citation) -> dict[str, Any]:
    """Return a citation with a fresh source status and sanitized excerpt."""

    source_status = record.source_status
    can_open = False
    excerpt = record.excerpt
    file_id = record.file_id
    chunk_id = record.chunk_id
    if record.source_snapshot_id is not None:
        try:
            view = read_source_snapshot(session, record.source_snapshot_id)
        except SourceSnapshotError:
            view = None
        if view is not None:
            source_status = view.source_status
            can_open = view.can_open_source
            excerpt = view.excerpt if view.excerpt is not None else record.excerpt
            file_id = view.file_id or file_id
            chunk_id = view.chunk_id or chunk_id
    if source_status in {"SOURCE_DELETED", "SOURCE_IN_TRASH", "SOURCE_OUT_OF_SCOPE"}:
        can_open = False
    return {
        "citation_id": record.citation_id,
        "answer_version_id": record.answer_version_id,
        "learning_feedback_id": record.learning_feedback_id,
        "source_snapshot_id": record.source_snapshot_id,
        "display_number": record.display_number,
        "knowledge_base_id": record.knowledge_base_id,
        "index_version_id": record.index_version_id,
        "file_id": file_id,
        "chunk_id": chunk_id,
        "file_name": record.file_name_snapshot,
        "file_version": record.file_version_snapshot,
        "heading_path": list(record.heading_path_snapshot or []),
        "page_start": record.page_start,
        "page_end": record.page_end,
        "slide_number": record.slide_number,
        "line_start": record.line_start,
        "line_end": record.line_end,
        "excerpt": excerpt,
        "source_status": source_status,
        "can_open_source": can_open,
        "created_at": record.created_at,
    }


def list_answer_citations(session: Session, answer_version_id: str) -> list[Citation]:
    return list(
        session.scalars(
            select(Citation)
            .where(Citation.answer_version_id == answer_version_id)
            .order_by(Citation.display_number)
        )
    )


def list_feedback_citations(session: Session, learning_feedback_id: str) -> list[Citation]:
    return list(
        session.scalars(
            select(Citation)
            .where(Citation.learning_feedback_id == learning_feedback_id)
            .order_by(Citation.display_number)
        )
    )


def sanitize_citations_for_file_purge(
    session: Session, file_ids: list[str], *, deleted_at: datetime | None = None
) -> None:
    if not file_ids:
        return
    stamp = deleted_at or datetime.now(UTC)
    session.execute(
        update(Citation)
        .where(Citation.file_id.in_(file_ids))
        .values(
            file_id=None,
            chunk_id=None,
            excerpt=None,
            excerpt_sha256=None,
            source_status="SOURCE_DELETED",
            source_deleted_at=stamp,
        )
    )


def sanitize_citations_for_knowledge_base_purge(
    session: Session, knowledge_base_id: str, *, deleted_at: datetime | None = None
) -> None:
    stamp = deleted_at or datetime.now(UTC)
    session.execute(
        update(Citation)
        .where(Citation.knowledge_base_id == knowledge_base_id)
        .values(
            source_snapshot_id=None,
            file_id=None,
            chunk_id=None,
            excerpt=None,
            excerpt_sha256=None,
            source_status="SOURCE_DELETED",
            source_deleted_at=stamp,
        )
    )


def _sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_citation_id() -> str:
    from mindmate.infrastructure.models import new_id

    return new_id()


__all__ = [
    "CitationBindingError",
    "bind_answer_citations",
    "bind_feedback_citations",
    "citation_payload",
    "list_answer_citations",
    "list_feedback_citations",
    "sanitize_citations_for_file_purge",
    "sanitize_citations_for_knowledge_base_purge",
]
