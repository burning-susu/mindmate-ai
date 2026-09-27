"""Read-only projection of persisted learning sessions.

The list reads session identity and the local search projection. It does not
copy questions, and it does not return unsubmitted answer keys.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from mindmate.application.conversation_history import HistoryQueryError
from mindmate.application.history_search_index import (
    OWNER_LEARNING,
    collect_hits,
    locations_for,
    search_index_status,
)
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
QUERY_LIMIT = 80
SCAN_BATCH = 50


def list_learning_history(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
    q: str | None = None,
    goal_type: str | None = None,
    status: str | None = None,
    source_status: str | None = None,
    active_from: datetime | None = None,
    active_before: datetime | None = None,
) -> dict[str, object]:
    """Active sessions only. A keyword reads the local search projection.

    Blank keywords keep the unfiltered list. Unsubmitted answer keys stay out.
    """
    keyword = _keyword(q)
    signature = _filter_signature(
        q=keyword,
        goal_type=goal_type,
        status=status,
        source_status=source_status,
        active_from=active_from,
        active_before=active_before,
    )
    stamp, learning_session_id = _decode_cursor(cursor, signature)
    hits: dict[str, list[dict[str, str]]] = {}
    truncated = False
    if keyword is not None:
        hits, truncated = collect_hits(session, OWNER_LEARNING, keyword)
        if not hits:
            return {
                "items": [],
                "next_cursor": None,
                "search_index_status": search_index_status(session),
                "search_truncated": truncated,
            }
    collected: list[dict[str, object]] = []
    seek_stamp = stamp
    seek_id = learning_session_id
    while len(collected) <= limit:
        statement = _active_statement(
            owner_ids=set(hits) if keyword is not None else None,
            goal_type=goal_type,
            active_from=active_from,
            active_before=active_before,
            seek_stamp=seek_stamp,
            seek_id=seek_id,
        )
        rows = list(
            session.scalars(
                statement.order_by(
                    LearningSession.updated_at.desc(),
                    LearningSession.learning_session_id.desc(),
                ).limit(SCAN_BATCH)
            )
        )
        if not rows:
            break
        filled = False
        for row in rows:
            seek_stamp = row.updated_at
            seek_id = row.learning_session_id
            item = _item(session, row)
            if status is not None and item["status"] != status:
                continue
            if source_status is not None and item["source_status"] != source_status:
                continue
            item["locations"] = locations_for(hits, row.learning_session_id) if keyword else []
            collected.append(item)
            if len(collected) > limit:
                filled = True
                break
        if filled or len(rows) < SCAN_BATCH:
            break
    page = collected[:limit]
    next_cursor = None
    if len(collected) > limit and page:
        updated = page[-1]["updated_at"]
        if isinstance(updated, datetime):
            next_cursor = _encode_cursor(
                updated, str(page[-1]["learning_session_id"]), signature
            )
    return {
        "items": page,
        "next_cursor": next_cursor,
        "search_index_status": search_index_status(session),
        "search_truncated": truncated,
    }


def list_trashed_learning_sessions(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, object]:
    stamp, learning_session_id = _decode_trash_cursor(cursor)
    statement = select(LearningSession).where(LearningSession.deleted_at.is_not(None))
    if stamp is not None and learning_session_id is not None:
        statement = statement.where(
            or_(
                LearningSession.deleted_at < stamp,
                and_(
                    LearningSession.deleted_at == stamp,
                    LearningSession.learning_session_id < learning_session_id,
                ),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(
                LearningSession.deleted_at.desc(),
                LearningSession.learning_session_id.desc(),
            ).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [
        {
            "object_type": "learning_session",
            "object_id": row.learning_session_id,
            "title": row.topic,
            "deleted_at": row.deleted_at,
            "row_version": row.row_version,
        }
        for row in page
    ]
    next_cursor = None
    if has_more and page and page[-1].deleted_at is not None:
        next_cursor = _encode_trash_cursor(page[-1].deleted_at, page[-1].learning_session_id)
    return {"items": items, "next_cursor": next_cursor}


def _active_statement(
    *,
    owner_ids: set[str] | None,
    goal_type: str | None,
    active_from: datetime | None,
    active_before: datetime | None,
    seek_stamp: datetime | None,
    seek_id: str | None,
):
    statement = select(LearningSession).where(LearningSession.deleted_at.is_(None))
    if owner_ids is not None:
        statement = statement.where(LearningSession.learning_session_id.in_(owner_ids))
    if goal_type is not None:
        statement = statement.where(LearningSession.goal_type == goal_type)
    if active_from is not None:
        statement = statement.where(LearningSession.updated_at >= active_from)
    if active_before is not None:
        statement = statement.where(LearningSession.updated_at < active_before)
    if seek_stamp is not None and seek_id is not None:
        statement = statement.where(
            or_(
                LearningSession.updated_at < seek_stamp,
                and_(
                    LearningSession.updated_at == seek_stamp,
                    LearningSession.learning_session_id < seek_id,
                ),
            )
        )
    return statement


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
        "row_version": record.row_version,
        "locations": [],
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


def _keyword(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > QUERY_LIMIT or any(ord(char) < 32 for char in text):
        raise HistoryQueryError("HISTORY_QUERY_INVALID", "搜索词不能超过 80 个字符，且不能包含控制字符。")
    return text


def _filter_signature(
    *,
    q: str | None,
    goal_type: str | None,
    status: str | None,
    source_status: str | None,
    active_from: datetime | None,
    active_before: datetime | None,
) -> str | None:
    parts = {
        "q": q,
        "goal_type": goal_type,
        "status": status,
        "source_status": source_status,
        "active_from": active_from.isoformat() if active_from is not None else None,
        "active_before": active_before.isoformat() if active_before is not None else None,
    }
    active = [f"{key}={value}" for key, value in parts.items() if value]
    if not active:
        return None
    return hashlib.sha256("|".join(active).encode()).hexdigest()[:16]


def _encode_cursor(
    stamp: datetime, learning_session_id: str, signature: str | None = None
) -> str:
    stamp_text = _as_utc(stamp).isoformat()
    if signature is None:
        raw = f"1|{stamp_text}|{learning_session_id}"
    else:
        raw = f"3|{stamp_text}|{learning_session_id}|{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(
    cursor: str | None, signature: str | None
) -> tuple[datetime | None, str | None]:
    if cursor is None or cursor == "":
        return None, None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        parts = raw.split("|")
        if parts[0] == "1" and len(parts) == 3:
            if signature is not None or not parts[2]:
                raise ValueError
            parsed = datetime.fromisoformat(parts[1])
            learning_session_id = parts[2]
        elif parts[0] == "3" and len(parts) == 4:
            if signature is None or parts[3] != signature or not parts[2]:
                raise ValueError
            parsed = datetime.fromisoformat(parts[1])
            learning_session_id = parts[2]
        else:
            raise ValueError
    except (ValueError, UnicodeError):
        raise HistoryQueryError("HISTORY_CURSOR_INVALID", "历史游标无效。") from None
    return _as_utc(parsed), learning_session_id


def _encode_trash_cursor(stamp: datetime, learning_session_id: str) -> str:
    raw = f"2|{_as_utc(stamp).isoformat()}|{learning_session_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_trash_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if cursor is None or cursor == "":
        return None, None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        version, stamp, learning_session_id = raw.split("|", 2)
        if version != "2" or not learning_session_id:
            raise ValueError
        parsed = datetime.fromisoformat(stamp)
    except (ValueError, UnicodeError):
        raise HistoryQueryError("HISTORY_CURSOR_INVALID", "历史游标无效。") from None
    return _as_utc(parsed), learning_session_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
