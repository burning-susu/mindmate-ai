"""Read-only projection of persisted chat conversations.

History does not own conversation rows and does not copy messages.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from mindmate.infrastructure.models import (
    AnswerVersion,
    Citation,
    Conversation,
    ConversationScope,
    FileRecord,
    KnowledgeBase,
    KnowledgeBaseFile,
    Message,
)

SUMMARY_LIMIT = 80
QUERY_LIMIT = 80
SCAN_BATCH = 50
_AVAILABLE = "AVAILABLE"
_NOT_APPLICABLE = "NOT_APPLICABLE"


class HistoryQueryError(RuntimeError):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def list_conversation_history(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
    q: str | None = None,
    mode: str | None = None,
    status: str | None = None,
    source_status: str | None = None,
    active_from: datetime | None = None,
    active_before: datetime | None = None,
) -> dict[str, object]:
    """Active conversations only. Keyword matches title or the saved list summary.

    The summary is the same trimmed latest user message already shown in the list.
    Full message bodies, completed answers and internal prompts are not scanned.
    """
    keyword = _keyword(q)
    stamp, conversation_id = _decode_cursor(cursor)
    collected: list[dict[str, object]] = []
    seek_stamp = stamp
    seek_id = conversation_id
    while len(collected) <= limit:
        statement = _active_statement(
            keyword=keyword,
            mode=mode,
            active_from=active_from,
            active_before=active_before,
            seek_stamp=seek_stamp,
            seek_id=seek_id,
        )
        rows = list(
            session.scalars(
                statement.order_by(
                    Conversation.last_active_at.desc(),
                    Conversation.conversation_id.desc(),
                ).limit(SCAN_BATCH)
            )
        )
        if not rows:
            break
        filled = False
        for row in rows:
            seek_stamp = row.last_active_at
            seek_id = row.conversation_id
            item = _item(session, row)
            if status is not None and item["status"] != status:
                continue
            if source_status is not None and item["source_status"] != source_status:
                continue
            item["locations"] = _locations(keyword, str(item["title"]), str(item["summary"]))
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
            next_cursor = _encode_cursor(updated, str(page[-1]["conversation_id"]))
    return {"items": page, "next_cursor": next_cursor}


def list_trashed_conversations(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
) -> dict[str, object]:
    stamp, conversation_id = _decode_trash_cursor(cursor)
    statement = select(Conversation).where(Conversation.deleted_at.is_not(None))
    if stamp is not None and conversation_id is not None:
        statement = statement.where(
            or_(
                Conversation.deleted_at < stamp,
                and_(
                    Conversation.deleted_at == stamp,
                    Conversation.conversation_id < conversation_id,
                ),
            )
        )
    rows = list(
        session.scalars(
            statement.order_by(
                Conversation.deleted_at.desc(),
                Conversation.conversation_id.desc(),
            ).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [
        {
            "object_type": "conversation",
            "object_id": row.conversation_id,
            "title": row.title,
            "deleted_at": row.deleted_at,
            "row_version": row.row_version,
        }
        for row in page
    ]
    next_cursor = None
    if has_more and page and page[-1].deleted_at is not None:
        next_cursor = _encode_trash_cursor(page[-1].deleted_at, page[-1].conversation_id)
    return {"items": items, "next_cursor": next_cursor}


def _active_statement(
    *,
    keyword: str | None,
    mode: str | None,
    active_from: datetime | None,
    active_before: datetime | None,
    seek_stamp: datetime | None,
    seek_id: str | None,
):
    statement = select(Conversation).where(Conversation.deleted_at.is_(None))
    if mode is not None:
        statement = statement.where(Conversation.current_mode == mode)
    if active_from is not None:
        statement = statement.where(Conversation.last_active_at >= active_from)
    if active_before is not None:
        statement = statement.where(Conversation.last_active_at < active_before)
    if keyword is not None:
        pattern = _like_pattern(keyword)
        latest_summary = (
            select(func.substr(Message.content, 1, SUMMARY_LIMIT))
            .where(
                Message.conversation_id == Conversation.conversation_id,
                Message.archived_at.is_(None),
                Message.role == "USER",
            )
            .order_by(Message.sequence_number.desc())
            .limit(1)
            .scalar_subquery()
        )
        statement = statement.where(
            or_(
                Conversation.title.like(pattern, escape="\\"),
                latest_summary.like(pattern, escape="\\"),
            )
        )
    if seek_stamp is not None and seek_id is not None:
        statement = statement.where(
            or_(
                Conversation.last_active_at < seek_stamp,
                and_(
                    Conversation.last_active_at == seek_stamp,
                    Conversation.conversation_id < seek_id,
                ),
            )
        )
    return statement


def _item(session: Session, conversation: Conversation) -> dict[str, object]:
    scope = session.scalar(
        select(ConversationScope)
        .where(
            ConversationScope.conversation_id == conversation.conversation_id,
            ConversationScope.ended_at.is_(None),
        )
        .order_by(ConversationScope.scope_version.desc())
        .limit(1)
    )
    knowledge_base = None
    scope_name = None
    if scope is not None and scope.knowledge_base_id:
        knowledge_base = session.get(KnowledgeBase, scope.knowledge_base_id)
        scope_name = knowledge_base.name if knowledge_base is not None else None
    source_status = _source_status(session, conversation, scope, knowledge_base)
    assistant_status = session.scalar(
        select(Message.status)
        .where(
            Message.conversation_id == conversation.conversation_id,
            Message.archived_at.is_(None),
            Message.role == "ASSISTANT",
        )
        .order_by(Message.sequence_number.desc())
        .limit(1)
    )
    if source_status not in {_NOT_APPLICABLE, _AVAILABLE}:
        status = "SOURCE_INVALID"
    elif assistant_status == "INTERRUPTED":
        status = "INTERRUPTED"
    else:
        status = conversation.status
    message_count = session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation.conversation_id,
            Message.archived_at.is_(None),
        )
    ) or 0
    summary = session.scalar(
        select(func.substr(Message.content, 1, SUMMARY_LIMIT + 1))
        .where(
            Message.conversation_id == conversation.conversation_id,
            Message.archived_at.is_(None),
            Message.role == "USER",
        )
        .order_by(Message.sequence_number.desc())
        .limit(1)
    )
    return {
        "conversation_id": conversation.conversation_id,
        "title": conversation.title,
        "summary": _trim_summary(summary or conversation.title),
        "current_mode": conversation.current_mode,
        "scope_name": scope_name,
        "status": status,
        "source_status": source_status,
        "message_count": int(message_count),
        "created_at": conversation.created_at,
        "updated_at": conversation.last_active_at,
        "row_version": conversation.row_version,
        "locations": [],
    }


def _source_status(
    session: Session,
    conversation: Conversation,
    scope: ConversationScope | None,
    knowledge_base: KnowledgeBase | None,
) -> str:
    if conversation.current_mode != "KNOWLEDGE_CHAT":
        return _NOT_APPLICABLE
    if scope is None or not scope.knowledge_base_id or knowledge_base is None:
        return "SOURCE_DELETED"
    if knowledge_base.deleted_at is not None:
        return "SOURCE_IN_TRASH"
    if (
        knowledge_base.status != "READY"
        or knowledge_base.active_index_version_id != scope.index_version_id
    ):
        return "INDEX_VERSION_RETIRED"
    answer_id = session.scalar(
        select(AnswerVersion.answer_version_id)
        .join(Message, Message.message_id == AnswerVersion.assistant_message_id)
        .where(
            Message.conversation_id == conversation.conversation_id,
            Message.archived_at.is_(None),
        )
        .order_by(Message.sequence_number.desc(), AnswerVersion.version_number.desc())
        .limit(1)
    )
    if answer_id is None:
        return _AVAILABLE
    citations = session.execute(
        select(Citation.file_id, Citation.source_deleted_at).where(
            Citation.answer_version_id == answer_id
        )
    ).all()
    if not citations:
        return _AVAILABLE
    statuses = {
        _citation_status(session, knowledge_base.knowledge_base_id, file_id, deleted_at)
        for file_id, deleted_at in citations
    }
    if statuses == {_AVAILABLE}:
        return _AVAILABLE
    if _AVAILABLE in statuses:
        return "PARTIAL_SOURCE"
    if len(statuses) == 1:
        return next(iter(statuses))
    return "PARTIAL_SOURCE"


def _citation_status(
    session: Session,
    knowledge_base_id: str,
    file_id: str | None,
    source_deleted_at: datetime | None,
) -> str:
    if source_deleted_at is not None or file_id is None:
        return "SOURCE_DELETED"
    file_record = session.get(FileRecord, file_id)
    if file_record is None:
        return "SOURCE_DELETED"
    if file_record.deleted_at is not None:
        return "SOURCE_IN_TRASH"
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


def _trim_summary(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) <= SUMMARY_LIMIT:
        return compact
    return f"{compact[:SUMMARY_LIMIT]}…"


def _keyword(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > QUERY_LIMIT or any(ord(char) < 32 for char in text):
        raise HistoryQueryError("HISTORY_QUERY_INVALID", "搜索词不能超过 80 个字符，且不能包含控制字符。")
    return text


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _locations(keyword: str | None, title: str, summary: str) -> list[dict[str, str]]:
    if keyword is None:
        return []
    found: list[dict[str, str]] = []
    title_snippet = _window(title, keyword)
    if title_snippet is not None:
        found.append({"section": "title", "snippet": title_snippet})
    summary_snippet = _window(summary, keyword)
    if summary_snippet is not None and summary_snippet != title_snippet:
        found.append({"section": "summary", "snippet": summary_snippet})
    return found[:2]


def _window(text: str, keyword: str) -> str | None:
    index = text.casefold().find(keyword.casefold())
    if index < 0:
        return None
    start = max(0, index - 16)
    end = min(len(text), index + len(keyword) + 16)
    return text[start:end]


def _encode_cursor(stamp: datetime, conversation_id: str) -> str:
    raw = f"1|{_as_utc(stamp).isoformat()}|{conversation_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if cursor is None or cursor == "":
        return None, None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        version, stamp, conversation_id = raw.split("|", 2)
        if version != "1" or not conversation_id:
            raise ValueError
        parsed = datetime.fromisoformat(stamp)
    except (ValueError, UnicodeError):
        raise HistoryQueryError("HISTORY_CURSOR_INVALID", "历史游标无效。") from None
    return _as_utc(parsed), conversation_id


def _encode_trash_cursor(stamp: datetime, conversation_id: str) -> str:
    raw = f"2|{_as_utc(stamp).isoformat()}|{conversation_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_trash_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    if cursor is None or cursor == "":
        return None, None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        version, stamp, conversation_id = raw.split("|", 2)
        if version != "2" or not conversation_id:
            raise ValueError
        parsed = datetime.fromisoformat(stamp)
    except (ValueError, UnicodeError):
        raise HistoryQueryError("HISTORY_CURSOR_INVALID", "历史游标无效。") from None
    return _as_utc(parsed), conversation_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
