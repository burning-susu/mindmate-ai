"""Chat-owned soft delete and restore for one conversation.

History must call these use cases instead of writing the conversation table.
Messages, files, knowledge bases and other conversations stay in place.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from mindmate.application.chat_generation import ChatCommandError, utc_now
from mindmate.infrastructure.models import Conversation

TRASH_RETENTION_DAYS = 30


def trash_conversation(
    session: Session, conversation_id: str, *, expected_version: int
) -> Conversation:
    record = session.get(Conversation, conversation_id)
    if record is None:
        raise ChatCommandError("CONVERSATION_NOT_FOUND", "会话不存在。", 404)
    if record.deleted_at is not None:
        return record
    now = utc_now()
    result = session.execute(
        update(Conversation)
        .where(
            Conversation.conversation_id == conversation_id,
            Conversation.row_version == expected_version,
            Conversation.deleted_at.is_(None),
        )
        .values(
            deleted_at=now,
            purge_after=now + timedelta(days=TRASH_RETENTION_DAYS),
            row_version=expected_version + 1,
            updated_at=now,
        )
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        session.rollback()
        session.expire(record)
        session.refresh(record)
        if record.deleted_at is not None:
            return record
        raise ChatCommandError(
            "CONVERSATION_VERSION_CONFLICT",
            "会话已被其他操作更新，请重新加载后再移入回收站。",
            412,
            current_row_version=record.row_version,
        )
    session.commit()
    session.expire(record)
    session.refresh(record)
    return record


def restore_conversation(
    session: Session, conversation_id: str, *, expected_version: int
) -> Conversation:
    record = session.get(Conversation, conversation_id)
    if record is None:
        raise ChatCommandError("CONVERSATION_NOT_FOUND", "会话不存在。", 404)
    if record.deleted_at is None:
        return record
    now = utc_now()
    result = session.execute(
        update(Conversation)
        .where(
            Conversation.conversation_id == conversation_id,
            Conversation.row_version == expected_version,
            Conversation.deleted_at.is_not(None),
        )
        .values(
            deleted_at=None,
            purge_after=None,
            row_version=expected_version + 1,
            updated_at=now,
        )
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        session.rollback()
        session.expire(record)
        session.refresh(record)
        if record.deleted_at is None:
            return record
        raise ChatCommandError(
            "CONVERSATION_VERSION_CONFLICT",
            "会话已被其他操作更新，请重新加载后再恢复。",
            412,
            current_row_version=record.row_version,
        )
    session.commit()
    session.expire(record)
    session.refresh(record)
    return record
