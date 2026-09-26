"""Read-only projection of persisted learning sessions.

The list reads session, scope and file identity only. It does not load
question prompts, options, answer keys, evidence excerpts or feedback.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from mindmate.application.conversation_history import HistoryQueryError
from mindmate.infrastructure.models import (
    FileRecord,
    IndexVersion,
    KnowledgeBase,
    KnowledgeBaseFile,
    LearningScope,
    LearningScopeFile,
    LearningSession,
)

_AVAILABLE = "AVAILABLE"


def list_learning_history(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, object]:
    stamp, learning_session_id = _decode_cursor(cursor)
    statement = select(LearningSession).where(LearningSession.deleted_at.is_(None))
    if stamp is not None and learning_session_id is not None:
        statement = statement.where(
            or_(
                LearningSession.updated_at < stamp,
                and_(
                    LearningSession.updated_at == stamp,
                    LearningSession.learning_session_id < learning_session_id,
                ),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(
                LearningSession.updated_at.desc(),
                LearningSession.learning_session_id.desc(),
            ).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [_item(session, row) for row in page]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.updated_at, last.learning_session_id)
    return {"items": items, "next_cursor": next_cursor}


def _item(session: Session, record: LearningSession) -> dict[str, object]:
    scope = session.scalar(
        select(LearningScope).where(
            LearningScope.learning_session_id == record.learning_session_id
        )
    )
    knowledge_base = session.get(KnowledgeBase, record.knowledge_base_id)
    source_status = _source_status(session, record, scope, knowledge_base)
    scope_name = knowledge_base.name if knowledge_base is not None else None
    file_count = 0
    if scope is not None:
        file_count = int(
            session.scalar(
                select(func.count())
                .select_from(LearningScopeFile)
                .where(LearningScopeFile.learning_scope_id == scope.learning_scope_id)
            )
            or 0
        )
    status = "SOURCE_INVALID" if source_status != _AVAILABLE else record.status
    return {
        "learning_session_id": record.learning_session_id,
        "topic": record.topic,
        "goal_type": record.goal_type,
        "scope_name": scope_name,
        "scope_file_count": file_count,
        "status": status,
        "source_status": source_status,
        "answered_count": record.completed_question_count,
        "target_question_count": record.target_question_count,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _source_status(
    session: Session,
    record: LearningSession,
    scope: LearningScope | None,
    knowledge_base: KnowledgeBase | None,
) -> str:
    if scope is None or knowledge_base is None:
        return "SOURCE_DELETED"
    if knowledge_base.deleted_at is not None:
        return "SOURCE_IN_TRASH"
    version = (
        session.get(IndexVersion, scope.index_version_id) if scope.index_version_id else None
    )
    if (
        knowledge_base.status != "READY"
        or version is None
        or version.status != "READY"
        or knowledge_base.active_index_version_id != scope.index_version_id
    ):
        return "INDEX_VERSION_RETIRED"
    file_ids = list(
        session.scalars(
            select(LearningScopeFile.file_id).where(
                LearningScopeFile.learning_scope_id == scope.learning_scope_id
            )
        )
    )
    if not file_ids:
        return _AVAILABLE if record.status == "FAILED" else "SOURCE_DELETED"
    statuses = {_file_status(session, knowledge_base.knowledge_base_id, scope, file_id) for file_id in file_ids}
    if statuses == {_AVAILABLE}:
        return _AVAILABLE
    if _AVAILABLE in statuses:
        return "PARTIAL_SOURCE"
    if len(statuses) == 1:
        return next(iter(statuses))
    return "PARTIAL_SOURCE"


def _file_status(
    session: Session,
    knowledge_base_id: str,
    scope: LearningScope,
    file_id: str,
) -> str:
    scope_file = session.scalar(
        select(LearningScopeFile).where(
            LearningScopeFile.learning_scope_id == scope.learning_scope_id,
            LearningScopeFile.file_id == file_id,
        )
    )
    file_record = session.get(FileRecord, file_id)
    if file_record is None:
        return "SOURCE_DELETED"
    if file_record.deleted_at is not None:
        return "SOURCE_IN_TRASH"
    if scope_file is not None and file_record.content_hash != scope_file.content_hash:
        return "SOURCE_VERSION_STALE"
    membership = session.scalar(
        select(KnowledgeBaseFile).where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.file_id == file_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
        )
    )
    if membership is None:
        return "SOURCE_OUT_OF_SCOPE"
    if membership.index_state != "READY":
        return "INDEX_VERSION_RETIRED"
    return _AVAILABLE


def _encode_cursor(stamp: datetime, learning_session_id: str) -> str:
    raw = f"1|{_as_utc(stamp).isoformat()}|{learning_session_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if cursor is None or cursor == "":
        return None, None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        version, stamp, learning_session_id = raw.split("|", 2)
        if version != "1" or not learning_session_id:
            raise ValueError
        parsed = datetime.fromisoformat(stamp)
    except (ValueError, UnicodeError):
        raise HistoryQueryError("HISTORY_CURSOR_INVALID", "历史游标无效。") from None
    return _as_utc(parsed), learning_session_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
