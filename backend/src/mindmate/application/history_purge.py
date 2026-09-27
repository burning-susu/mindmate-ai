"""Expire soft-deleted chat/learning history and permanently remove owned rows.

Only trashed owners with a non-null ``purge_after <= now`` are eligible.
Shared files, knowledge bases, index artefacts and SourceSnapshot rows stay.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from mindmate.application.history_search_index import (
    OWNER_CONVERSATION,
    OWNER_LEARNING,
    _clear_owner,
)
from mindmate.infrastructure.models import (
    AiOperation,
    AnswerVersion,
    Citation,
    Conversation,
    ConversationScope,
    KnowledgePoint,
    KnowledgePointEvidence,
    LearningAttempt,
    LearningFeedback,
    LearningPlan,
    LearningPlanItem,
    LearningQuestion,
    LearningScope,
    LearningScopeFile,
    LearningSession,
    Message,
    QuestionEvidence,
)

DEFAULT_BATCH = 10


def utc_now() -> datetime:
    return datetime.now(UTC)


class HistoryPurgeError(Exception):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def preview_expired_history(
    session: Session, *, now: datetime | None = None
) -> dict[str, Any]:
    clock = _normalize(now)
    sql_now = _sql_utc(clock)
    conversations = _count_expired(session, Conversation, sql_now)
    learning = _count_expired(session, LearningSession, sql_now)
    missing = _count_missing_purge_after(session)
    return {
        "as_of": clock,
        "eligible_conversations": conversations,
        "eligible_learning_sessions": learning,
        "eligible_total": conversations + learning,
        "trashed_missing_purge_after": missing,
    }


def purge_expired_history(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_BATCH,
) -> dict[str, Any]:
    """Purge up to ``limit`` expired owners. Idempotent and bounded."""
    if limit < 1 or limit > 50:
        raise HistoryPurgeError("HISTORY_PURGE_LIMIT_INVALID", "单批清理数量无效。")
    clock = _normalize(now)
    sql_now = _sql_utc(clock)
    error_codes: list[str] = []
    stats: dict[str, Any] = {
        "as_of": clock,
        "scanned": 0,
        "purged_conversations": 0,
        "purged_learning_sessions": 0,
        "skipped_restored": 0,
        "skipped_not_due": 0,
        "errors": 0,
        "error_codes": error_codes,
    }
    candidates = _scan_expired(session, sql_now, limit)
    stats["scanned"] = len(candidates)
    for object_type, object_id, row_version in candidates:
        try:
            with session.begin_nested():
                outcome = _purge_owner(
                    session,
                    object_type=object_type,
                    object_id=object_id,
                    expected_version=row_version,
                    now=sql_now,
                    require_due=True,
                )
            if outcome == "PURGED":
                if object_type == "conversation":
                    stats["purged_conversations"] += 1
                else:
                    stats["purged_learning_sessions"] += 1
            elif outcome == "SKIPPED_RESTORED":
                stats["skipped_restored"] += 1
            elif outcome == "SKIPPED_NOT_DUE":
                stats["skipped_not_due"] += 1
        except HistoryPurgeError as exc:
            stats["errors"] += 1
            if exc.code not in error_codes and len(error_codes) < 8:
                error_codes.append(exc.code)
        except Exception:
            stats["errors"] += 1
            if "HISTORY_PURGE_FAILED" not in error_codes and len(error_codes) < 8:
                error_codes.append("HISTORY_PURGE_FAILED")
    session.commit()
    return stats


def purge_conversation_permanent(
    session: Session,
    conversation_id: str,
    *,
    expected_version: int,
    confirmed: bool,
    now: datetime | None = None,
    require_due: bool = False,
) -> dict[str, Any]:
    if not confirmed:
        raise HistoryPurgeError(
            "PURGE_CONFIRMATION_REQUIRED", "永久删除需要明确确认。", 400
        )
    clock = _normalize(now)
    sql_now = _sql_utc(clock)
    with session.begin_nested():
        outcome = _purge_owner(
            session,
            object_type="conversation",
            object_id=conversation_id,
            expected_version=expected_version,
            now=sql_now,
            require_due=require_due,
        )
    if outcome == "SKIPPED_RESTORED":
        raise HistoryPurgeError(
            "CONVERSATION_NOT_IN_TRASH", "只有回收站中的对话才能永久删除。", 409
        )
    if outcome == "SKIPPED_NOT_DUE":
        raise HistoryPurgeError(
            "CONVERSATION_NOT_DUE", "该对话尚未到达可永久清理的时间。", 409
        )
    if outcome == "NOT_FOUND":
        raise HistoryPurgeError("CONVERSATION_NOT_FOUND", "会话不存在。", 404)
    session.commit()
    return {"conversation_id": conversation_id, "status": "PURGED"}


def purge_learning_session_permanent(
    session: Session,
    learning_session_id: str,
    *,
    expected_version: int,
    confirmed: bool,
    now: datetime | None = None,
    require_due: bool = False,
) -> dict[str, Any]:
    if not confirmed:
        raise HistoryPurgeError(
            "PURGE_CONFIRMATION_REQUIRED", "永久删除需要明确确认。", 400
        )
    clock = _normalize(now)
    sql_now = _sql_utc(clock)
    with session.begin_nested():
        outcome = _purge_owner(
            session,
            object_type="learning_session",
            object_id=learning_session_id,
            expected_version=expected_version,
            now=sql_now,
            require_due=require_due,
        )
    if outcome == "SKIPPED_RESTORED":
        raise HistoryPurgeError(
            "LEARNING_SESSION_NOT_IN_TRASH",
            "只有回收站中的学习会话才能永久删除。",
            409,
        )
    if outcome == "SKIPPED_NOT_DUE":
        raise HistoryPurgeError(
            "LEARNING_SESSION_NOT_DUE", "该学习会话尚未到达可永久清理的时间。", 409
        )
    if outcome == "NOT_FOUND":
        raise HistoryPurgeError("LEARNING_SESSION_NOT_FOUND", "学习会话不存在。", 404)
    session.commit()
    return {"learning_session_id": learning_session_id, "status": "PURGED"}


def _normalize(value: datetime | None) -> datetime:
    """Return an aware UTC clock for API payloads."""
    clock = value or utc_now()
    if clock.tzinfo is None:
        return clock.replace(tzinfo=UTC)
    return clock.astimezone(UTC)


def _sql_utc(value: datetime | None) -> datetime:
    """SQLite DateTime columns are compared as naive UTC in this project."""
    return _normalize(value).replace(tzinfo=None)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _count_expired(session: Session, model: type[Any], now: datetime) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(
                model.deleted_at.is_not(None),
                model.purge_after.is_not(None),
                model.purge_after <= now,
            )
        )
        or 0
    )


def _count_missing_purge_after(session: Session) -> int:
    conversations = int(
        session.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.deleted_at.is_not(None),
                Conversation.purge_after.is_(None),
            )
        )
        or 0
    )
    learning = int(
        session.scalar(
            select(func.count())
            .select_from(LearningSession)
            .where(
                LearningSession.deleted_at.is_not(None),
                LearningSession.purge_after.is_(None),
            )
        )
        or 0
    )
    return conversations + learning


def _scan_expired(
    session: Session, now: datetime, limit: int
) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int, datetime]] = []
    for object_type, model, id_attr in (
        ("conversation", Conversation, Conversation.conversation_id),
        ("learning_session", LearningSession, LearningSession.learning_session_id),
    ):
        for row in session.execute(
            select(id_attr, model.row_version, model.purge_after)
            .where(
                model.deleted_at.is_not(None),
                model.purge_after.is_not(None),
                model.purge_after <= now,
            )
            .order_by(model.purge_after, id_attr)
            .limit(limit)
        ):
            rows.append((object_type, str(row[0]), int(row[1]), row[2]))
    rows.sort(key=lambda item: (item[3], item[0], item[1]))
    return [(item[0], item[1], item[2]) for item in rows[:limit]]


def _purge_owner(
    session: Session,
    *,
    object_type: str,
    object_id: str,
    expected_version: int,
    now: datetime,
    require_due: bool,
) -> str:
    if object_type == "conversation":
        return _purge_conversation(
            session,
            object_id,
            expected_version=expected_version,
            now=now,
            require_due=require_due,
        )
    if object_type == "learning_session":
        return _purge_learning_session(
            session,
            object_id,
            expected_version=expected_version,
            now=now,
            require_due=require_due,
        )
    raise HistoryPurgeError("HISTORY_PURGE_TYPE_INVALID", "不支持的历史清理类型。")


def _due_cutoff(now: datetime) -> datetime:
    aware = _as_utc(now)
    assert aware is not None
    return aware


def _purge_conversation(
    session: Session,
    conversation_id: str,
    *,
    expected_version: int,
    now: datetime,
    require_due: bool,
) -> str:
    record = session.get(Conversation, conversation_id)
    if record is None:
        return "NOT_FOUND"
    if record.deleted_at is None:
        return "SKIPPED_RESTORED"
    cutoff = _due_cutoff(now)
    purge_after = _as_utc(record.purge_after)
    if require_due and (purge_after is None or purge_after > cutoff):
        return "SKIPPED_NOT_DUE"
    claim_filters = [
        Conversation.conversation_id == conversation_id,
        Conversation.row_version == expected_version,
        Conversation.deleted_at.is_not(None),
    ]
    if require_due:
        claim_filters.extend(
            [
                Conversation.purge_after.is_not(None),
                Conversation.purge_after <= now,
            ]
        )
    claim = session.execute(
        update(Conversation)
        .where(*claim_filters)
        .values(row_version=expected_version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if int(getattr(claim, "rowcount", 0) or 0) != 1:
        session.refresh(record)
        if record.deleted_at is None:
            return "SKIPPED_RESTORED"
        retry_purge_after = _as_utc(record.purge_after)
        if require_due and (retry_purge_after is None or retry_purge_after > cutoff):
            return "SKIPPED_NOT_DUE"
        raise HistoryPurgeError(
            "CONVERSATION_VERSION_CONFLICT",
            "会话已被其他操作更新，请重新加载后再永久删除。",
            412,
        )

    message_ids = list(
        session.scalars(
            select(Message.message_id).where(Message.conversation_id == conversation_id)
        )
    )
    answer_ids = list(
        session.scalars(
            select(AnswerVersion.answer_version_id).where(
                AnswerVersion.assistant_message_id.in_(message_ids)
            )
        )
    ) if message_ids else []
    if answer_ids:
        session.execute(
            delete(Citation).where(Citation.answer_version_id.in_(answer_ids))
        )
        session.execute(
            delete(AnswerVersion).where(AnswerVersion.answer_version_id.in_(answer_ids))
        )
    session.execute(
        delete(AiOperation).where(AiOperation.conversation_id == conversation_id)
    )
    if message_ids:
        session.execute(
            update(Message)
            .where(Message.conversation_id == conversation_id)
            .values(parent_user_message_id=None, conversation_scope_id=None)
        )
        session.execute(
            delete(Message).where(Message.conversation_id == conversation_id)
        )
    session.execute(
        delete(ConversationScope).where(
            ConversationScope.conversation_id == conversation_id
        )
    )
    _clear_owner(session, OWNER_CONVERSATION, conversation_id)
    deleted = session.execute(
        delete(Conversation).where(
            Conversation.conversation_id == conversation_id,
            Conversation.deleted_at.is_not(None),
        )
    )
    if int(getattr(deleted, "rowcount", 0) or 0) != 1:
        raise HistoryPurgeError(
            "HISTORY_PURGE_RACE", "清理过程中会话状态已变化，已中止本次删除。"
        )
    return "PURGED"


def _purge_learning_session(
    session: Session,
    learning_session_id: str,
    *,
    expected_version: int,
    now: datetime,
    require_due: bool,
) -> str:
    record = session.get(LearningSession, learning_session_id)
    if record is None:
        return "NOT_FOUND"
    if record.deleted_at is None:
        return "SKIPPED_RESTORED"
    cutoff = _due_cutoff(now)
    purge_after = _as_utc(record.purge_after)
    if require_due and (purge_after is None or purge_after > cutoff):
        return "SKIPPED_NOT_DUE"
    claim_filters = [
        LearningSession.learning_session_id == learning_session_id,
        LearningSession.row_version == expected_version,
        LearningSession.deleted_at.is_not(None),
    ]
    if require_due:
        claim_filters.extend(
            [
                LearningSession.purge_after.is_not(None),
                LearningSession.purge_after <= now,
            ]
        )
    claim = session.execute(
        update(LearningSession)
        .where(*claim_filters)
        .values(row_version=expected_version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if int(getattr(claim, "rowcount", 0) or 0) != 1:
        session.refresh(record)
        if record.deleted_at is None:
            return "SKIPPED_RESTORED"
        retry_purge_after = _as_utc(record.purge_after)
        if require_due and (retry_purge_after is None or retry_purge_after > cutoff):
            return "SKIPPED_NOT_DUE"
        raise HistoryPurgeError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "学习会话已被其他操作更新，请重新加载后再永久删除。",
            412,
        )

    attempt_ids = list(
        session.scalars(
            select(LearningAttempt.attempt_id).where(
                LearningAttempt.learning_session_id == learning_session_id
            )
        )
    )
    feedback_ids = list(
        session.scalars(
            select(LearningFeedback.feedback_id).where(
                LearningFeedback.attempt_id.in_(attempt_ids)
            )
        )
    ) if attempt_ids else []
    if feedback_ids:
        session.execute(
            delete(Citation).where(Citation.learning_feedback_id.in_(feedback_ids))
        )
        session.execute(
            delete(LearningFeedback).where(
                LearningFeedback.feedback_id.in_(feedback_ids)
            )
        )
    if attempt_ids:
        session.execute(
            delete(LearningAttempt).where(
                LearningAttempt.attempt_id.in_(attempt_ids)
            )
        )

    question_ids = list(
        session.scalars(
            select(LearningQuestion.question_id).where(
                LearningQuestion.learning_session_id == learning_session_id
            )
        )
    )
    point_ids = set(
        session.scalars(
            select(LearningQuestion.knowledge_point_id).where(
                LearningQuestion.learning_session_id == learning_session_id
            )
        )
    )
    plan_ids = list(
        session.scalars(
            select(LearningPlan.learning_plan_id).where(
                LearningPlan.learning_session_id == learning_session_id
            )
        )
    )
    if plan_ids:
        point_ids.update(
            session.scalars(
                select(LearningPlanItem.knowledge_point_id).where(
                    LearningPlanItem.learning_plan_id.in_(plan_ids)
                )
            )
        )
        session.execute(
            delete(LearningPlanItem).where(
                LearningPlanItem.learning_plan_id.in_(plan_ids)
            )
        )
        session.execute(
            delete(LearningPlan).where(LearningPlan.learning_plan_id.in_(plan_ids))
        )
    if question_ids:
        session.execute(
            delete(QuestionEvidence).where(
                QuestionEvidence.question_id.in_(question_ids)
            )
        )
        session.execute(
            delete(LearningQuestion).where(
                LearningQuestion.question_id.in_(question_ids)
            )
        )

    scope_ids = list(
        session.scalars(
            select(LearningScope.learning_scope_id).where(
                LearningScope.learning_session_id == learning_session_id
            )
        )
    )
    if scope_ids:
        session.execute(
            delete(LearningScopeFile).where(
                LearningScopeFile.learning_scope_id.in_(scope_ids)
            )
        )
        session.execute(
            delete(LearningScope).where(LearningScope.learning_scope_id.in_(scope_ids))
        )

    for point_id in point_ids:
        _maybe_delete_knowledge_point(session, point_id)

    _clear_owner(session, OWNER_LEARNING, learning_session_id)
    deleted = session.execute(
        delete(LearningSession).where(
            LearningSession.learning_session_id == learning_session_id,
            LearningSession.deleted_at.is_not(None),
        )
    )
    if int(getattr(deleted, "rowcount", 0) or 0) != 1:
        raise HistoryPurgeError(
            "HISTORY_PURGE_RACE", "清理过程中学习会话状态已变化，已中止本次删除。"
        )
    return "PURGED"


def _maybe_delete_knowledge_point(session: Session, knowledge_point_id: str) -> None:
    """Delete a knowledge point only when no other session still references it."""
    question_refs = int(
        session.scalar(
            select(func.count())
            .select_from(LearningQuestion)
            .where(LearningQuestion.knowledge_point_id == knowledge_point_id)
        )
        or 0
    )
    plan_refs = int(
        session.scalar(
            select(func.count())
            .select_from(LearningPlanItem)
            .where(LearningPlanItem.knowledge_point_id == knowledge_point_id)
        )
        or 0
    )
    if question_refs or plan_refs:
        return
    session.execute(
        delete(KnowledgePointEvidence).where(
            KnowledgePointEvidence.knowledge_point_id == knowledge_point_id
        )
    )
    session.execute(
        delete(KnowledgePoint).where(
            KnowledgePoint.knowledge_point_id == knowledge_point_id
        )
    )
