"""Local full-text projection for history search.

Chat and learning owners refresh one object's rows in the same transaction
that publishes, archives, or soft-deletes it. History queries only read the
projection. Backfill is bounded and never runs inside Alembic or request
startup.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from threading import Event, Thread

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm import Session as SessionClass

from mindmate.infrastructure.fts5 import _fields, match_expression
from mindmate.infrastructure.models import (
    Conversation,
    HistorySearchDocument,
    HistorySearchOwner,
    HistorySearchState,
    KnowledgePoint,
    LearningAttempt,
    LearningFeedback,
    LearningQuestion,
    LearningSession,
    Message,
)

OWNER_CONVERSATION = "conversation"
OWNER_LEARNING = "learning"
STATE_KEY = "projection"
BACKFILL_BATCH = 20
MAX_QUERY_PIECES = 12
MAX_FTS_ROWS = 2000
SNIPPET_RADIUS = 18
SNIPPET_LIMIT = 72
MAX_LOCATIONS = 3
FTS_TABLE = "history_search_fts"

_SECTION_RANK = {
    "user_message": 0,
    "assistant_message": 1,
    "question": 2,
    "submitted_answer": 3,
    "feedback": 4,
    "title": 5,
    "topic": 6,
    "goal": 7,
    "knowledge_point": 8,
}

_INSTALLED = False


class HistorySearchBackfill:
    """Catch up missing owners without blocking application startup."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="history-search-backfill", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            session = self._session_factory()
            try:
                status = backfill_history_search(session, limit=BACKFILL_BATCH)
                session.commit()
            except Exception:
                session.rollback()
                _mark_failed(self._session_factory)
                return
            finally:
                session.close()
            if status in {"READY", "FAILED"}:
                return
            self._stop.wait(0.05)


def install_history_search_listener() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from sqlalchemy import event

    event.listen(SessionClass, "before_commit", _before_commit)
    _INSTALLED = True


def search_index_status(session: Session) -> str:
    row = session.get(HistorySearchState, STATE_KEY)
    if row is None or row.status not in {"PENDING", "READY", "FAILED"}:
        return "PENDING"
    return row.status


def backfill_history_search(session: Session, *, limit: int = BACKFILL_BATCH) -> str:
    """Index a bounded set of owners that do not yet have a projection marker."""
    remaining = limit
    for owner_type, model, owner_attr in (
        (OWNER_CONVERSATION, Conversation, Conversation.conversation_id),
        (OWNER_LEARNING, LearningSession, LearningSession.learning_session_id),
    ):
        if remaining <= 0:
            break
        indexed = select(HistorySearchOwner.owner_id).where(
            HistorySearchOwner.owner_type == owner_type
        )
        missing = list(
            session.scalars(
                select(owner_attr)
                .where(
                    model.deleted_at.is_(None),
                    owner_attr.not_in(indexed),
                )
                .order_by(owner_attr)
                .limit(remaining)
            )
        )
        for owner_id in missing:
            if owner_type == OWNER_CONVERSATION:
                sync_conversation_search(session, owner_id)
            else:
                sync_learning_search(session, owner_id)
        remaining -= len(missing)
    _drop_ghosts(session, limit)
    if _missing_owner_count(session) == 0 and _ghost_count(session) == 0:
        verify_history_search_projection(session)
        _set_status(session, "READY", None)
        return "READY"
    _set_status(session, "PENDING", None)
    return "PENDING"


def verify_history_search_projection(session: Session) -> None:
    document_ids = set(session.scalars(select(HistorySearchDocument.document_id)))
    fts_ids = set(
        session.scalars(text(f"SELECT rowid FROM {FTS_TABLE}"))
    )
    if document_ids != fts_ids:
        raise RuntimeError("HISTORY_SEARCH_INCOMPLETE")
    try:
        session.execute(
            text(f"INSERT INTO {FTS_TABLE}({FTS_TABLE}, rank) VALUES ('integrity-check', 1)")
        )
    except Exception as error:
        raise RuntimeError("HISTORY_SEARCH_INCOMPLETE") from error


def collect_hits(
    session: Session, owner_type: str, keyword: str
) -> tuple[dict[str, list[dict[str, str]]], bool]:
    """Return owner id to at most three safe snippets. The bool is a row cap."""
    pieces = _pieces(keyword)
    if len(pieces) > MAX_QUERY_PIECES:
        from mindmate.application.conversation_history import HistoryQueryError

        raise HistoryQueryError(
            "HISTORY_QUERY_INVALID",
            "搜索词的词数过多。请缩短后再查。",
        )
    expression = match_expression(keyword)
    grouped: dict[str, list[dict[str, str]]] = {}
    truncated = False
    if expression:
        rows = session.execute(
            text(
                f"""
                SELECT d.owner_id AS owner_id,
                       d.section AS section,
                       d.record_id AS record_id,
                       d.source_id AS source_id,
                       d.content AS content
                FROM history_search_documents AS d
                JOIN {FTS_TABLE} AS f ON f.rowid = d.document_id
                WHERE d.owner_type = :owner_type
                  AND {FTS_TABLE} MATCH :match
                LIMIT :limit
                """
            ),
            {"owner_type": owner_type, "match": expression, "limit": MAX_FTS_ROWS},
        ).mappings()
        materialized = list(rows)
        truncated = len(materialized) >= MAX_FTS_ROWS
        for row in materialized:
            content = str(row["content"])
            if not _content_matches(content, keyword, pieces):
                continue
            _add_hit(
                grouped,
                str(row["owner_id"]),
                str(row["section"]),
                str(row["record_id"]),
                str(row["source_id"]),
                _snippet(content, keyword, pieces),
            )
        return grouped, truncated
    pattern = _like_pattern(keyword.strip())
    rows = session.execute(
        select(
            HistorySearchDocument.owner_id,
            HistorySearchDocument.section,
            HistorySearchDocument.record_id,
            HistorySearchDocument.source_id,
            HistorySearchDocument.content,
        )
        .where(
            HistorySearchDocument.owner_type == owner_type,
            HistorySearchDocument.content.like(pattern, escape="\\"),
        )
        .limit(MAX_FTS_ROWS)
    )
    materialized = list(rows)
    truncated = len(materialized) >= MAX_FTS_ROWS
    for owner_id, section, record_id, source_id, content in materialized:
        _add_hit(
            grouped,
            owner_id,
            section,
            record_id,
            source_id,
            _snippet(str(content), keyword, pieces),
        )
    return grouped, truncated


def sync_conversation_search(session: Session, conversation_id: str) -> None:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.deleted_at is not None:
        _clear_owner(session, OWNER_CONVERSATION, conversation_id)
        return
    desired = _conversation_documents(session, conversation)
    _replace_if_changed(session, OWNER_CONVERSATION, conversation_id, desired)


def sync_learning_search(session: Session, learning_session_id: str) -> None:
    record = session.get(LearningSession, learning_session_id)
    if record is None or record.deleted_at is not None:
        _clear_owner(session, OWNER_LEARNING, learning_session_id)
        return
    desired = _learning_documents(session, record)
    _replace_if_changed(session, OWNER_LEARNING, learning_session_id, desired)


def _before_commit(session: Session) -> None:
    if session.info.get("history_search_sync"):
        return
    conversations: set[str] = set()
    learning: set[str] = set()
    for obj in (*list(session.new), *list(session.dirty), *list(session.deleted)):
        if isinstance(obj, Conversation):
            conversations.add(obj.conversation_id)
        elif isinstance(obj, Message):
            conversations.add(obj.conversation_id)
        elif isinstance(obj, (LearningSession, LearningQuestion, LearningAttempt)):
            learning.add(obj.learning_session_id)
        elif isinstance(obj, LearningFeedback):
            attempt = session.get(LearningAttempt, obj.attempt_id)
            if attempt is not None:
                learning.add(attempt.learning_session_id)
        elif isinstance(obj, KnowledgePoint):
            learning.update(
                session.scalars(
                    select(LearningQuestion.learning_session_id).where(
                        LearningQuestion.knowledge_point_id == obj.knowledge_point_id
                    )
                )
            )
    if not conversations and not learning:
        return
    session.info["history_search_sync"] = True
    try:
        for conversation_id in conversations:
            sync_conversation_search(session, conversation_id)
        for learning_session_id in learning:
            sync_learning_search(session, learning_session_id)
        session.flush()
    finally:
        session.info["history_search_sync"] = False


def _conversation_documents(
    session: Session, conversation: Conversation
) -> list[tuple[str, str, str, str]]:
    documents: list[tuple[str, str, str, str]] = []
    title = conversation.title.strip()
    if title:
        documents.append(("title", conversation.conversation_id, conversation.conversation_id, title))
    messages = session.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.conversation_id,
            Message.archived_at.is_(None),
        )
        .order_by(Message.sequence_number)
    )
    for message in messages:
        content = message.content.strip()
        if not content:
            continue
        if message.role == "USER" and message.status == "SENT":
            documents.append(("user_message", message.message_id, message.message_id, message.content))
        elif message.role == "ASSISTANT" and message.status == "COMPLETED":
            documents.append(
                ("assistant_message", message.message_id, message.message_id, message.content)
            )
    return documents


def _learning_documents(
    session: Session, record: LearningSession
) -> list[tuple[str, str, str, str]]:
    documents: list[tuple[str, str, str, str]] = []
    if record.topic.strip():
        documents.append(("topic", record.learning_session_id, record.learning_session_id, record.topic))
    if record.goal_text.strip():
        documents.append(("goal", record.learning_session_id, record.learning_session_id, record.goal_text))
    questions = list(
        session.scalars(
            select(LearningQuestion)
            .where(LearningQuestion.learning_session_id == record.learning_session_id)
            .order_by(LearningQuestion.sequence_number)
        )
    )
    seen_points: set[str] = set()
    for question in questions:
        prompt = question.prompt_text.strip()
        if prompt:
            documents.append(("question", question.question_id, question.question_id, question.prompt_text))
        if question.knowledge_point_id not in seen_points:
            point = session.get(KnowledgePoint, question.knowledge_point_id)
            if point is not None and point.canonical_title.strip():
                seen_points.add(question.knowledge_point_id)
                documents.append(
                    (
                        "knowledge_point",
                        question.knowledge_point_id,
                        question.knowledge_point_id,
                        point.canonical_title,
                    )
                )
        attempts = session.scalars(
            select(LearningAttempt)
            .where(LearningAttempt.question_id == question.question_id)
            .order_by(LearningAttempt.attempt_number)
        )
        for attempt in attempts:
            feedback = session.scalar(
                select(LearningFeedback).where(LearningFeedback.attempt_id == attempt.attempt_id)
            )
            if feedback is None:
                continue
            label = _option_label(question.options_json, attempt.selected_option)
            submitted = label or (attempt.answer_content or "").strip()
            if submitted:
                documents.append(
                    ("submitted_answer", question.question_id, attempt.attempt_id, submitted)
                )
            if feedback.explanation.strip():
                documents.append(
                    ("feedback", question.question_id, feedback.feedback_id, feedback.explanation)
                )
    return documents


def _option_label(options: list[dict[str, str]], option_id: str) -> str:
    for option in options:
        if option.get("option_id") == option_id:
            return str(option.get("label") or "").strip()
    return ""


def _replace_if_changed(
    session: Session,
    owner_type: str,
    owner_id: str,
    desired: list[tuple[str, str, str, str]],
) -> None:
    existing = list(
        session.execute(
            select(
                HistorySearchDocument.section,
                HistorySearchDocument.record_id,
                HistorySearchDocument.source_id,
                HistorySearchDocument.content,
            ).where(
                HistorySearchDocument.owner_type == owner_type,
                HistorySearchDocument.owner_id == owner_id,
            )
        )
    )
    current = sorted(
        (section, record_id, source_id, content)
        for section, record_id, source_id, content in existing
    )
    marked = session.get(HistorySearchOwner, (owner_type, owner_id))
    if marked is not None and current == sorted(desired):
        return
    _clear_owner(session, owner_type, owner_id)
    for section, record_id, source_id, content in desired:
        document = HistorySearchDocument(
            owner_type=owner_type,
            owner_id=owner_id,
            section=section,
            record_id=record_id,
            source_id=source_id,
            content=content,
        )
        session.add(document)
        session.flush()
        bigrams, unigrams, terms = _fields(content)
        session.execute(
            text(
                f"INSERT INTO {FTS_TABLE} "
                "(rowid, content, han_bigrams, han_unigrams, terms) "
                "VALUES (:rowid, :content, :han_bigrams, :han_unigrams, :terms)"
            ),
            {
                "rowid": document.document_id,
                "content": content,
                "han_bigrams": bigrams,
                "han_unigrams": unigrams,
                "terms": terms,
            },
        )
    session.add(HistorySearchOwner(owner_type=owner_type, owner_id=owner_id))


def _clear_owner(session: Session, owner_type: str, owner_id: str) -> None:
    ids = list(
        session.scalars(
            select(HistorySearchDocument.document_id).where(
                HistorySearchDocument.owner_type == owner_type,
                HistorySearchDocument.owner_id == owner_id,
            )
        )
    )
    if ids:
        session.execute(
            text(f"DELETE FROM {FTS_TABLE} WHERE rowid IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
        session.execute(
            delete(HistorySearchDocument).where(HistorySearchDocument.document_id.in_(ids))
        )
    session.execute(
        delete(HistorySearchOwner).where(
            HistorySearchOwner.owner_type == owner_type,
            HistorySearchOwner.owner_id == owner_id,
        )
    )


def _drop_ghosts(session: Session, limit: int) -> None:
    conversation_ids = session.execute(
        text(
            """
            SELECT DISTINCT d.owner_id
            FROM history_search_documents AS d
            LEFT JOIN conversations AS c ON c.conversation_id = d.owner_id
            WHERE d.owner_type = 'conversation'
              AND (c.conversation_id IS NULL OR c.deleted_at IS NOT NULL)
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).scalars()
    for owner_id in conversation_ids:
        _clear_owner(session, OWNER_CONVERSATION, owner_id)
    learning_ids = session.execute(
        text(
            """
            SELECT DISTINCT d.owner_id
            FROM history_search_documents AS d
            LEFT JOIN learning_sessions AS s ON s.learning_session_id = d.owner_id
            WHERE d.owner_type = 'learning'
              AND (s.learning_session_id IS NULL OR s.deleted_at IS NOT NULL)
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).scalars()
    for owner_id in learning_ids:
        _clear_owner(session, OWNER_LEARNING, owner_id)


def _missing_owner_count(session: Session) -> int:
    conversation_indexed = select(HistorySearchOwner.owner_id).where(
        HistorySearchOwner.owner_type == OWNER_CONVERSATION
    )
    learning_indexed = select(HistorySearchOwner.owner_id).where(
        HistorySearchOwner.owner_type == OWNER_LEARNING
    )
    conversations = session.scalar(
        select(Conversation.conversation_id)
        .where(
            Conversation.deleted_at.is_(None),
            Conversation.conversation_id.not_in(conversation_indexed),
        )
        .limit(1)
    )
    learning = session.scalar(
        select(LearningSession.learning_session_id)
        .where(
            LearningSession.deleted_at.is_(None),
            LearningSession.learning_session_id.not_in(learning_indexed),
        )
        .limit(1)
    )
    return int(conversations is not None) + int(learning is not None)


def _ghost_count(session: Session) -> int:
    value = session.scalar(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT d.owner_id
                FROM history_search_documents AS d
                LEFT JOIN conversations AS c ON c.conversation_id = d.owner_id
                WHERE d.owner_type = 'conversation'
                  AND (c.conversation_id IS NULL OR c.deleted_at IS NOT NULL)
                UNION
                SELECT d.owner_id
                FROM history_search_documents AS d
                LEFT JOIN learning_sessions AS s ON s.learning_session_id = d.owner_id
                WHERE d.owner_type = 'learning'
                  AND (s.learning_session_id IS NULL OR s.deleted_at IS NOT NULL)
            )
            """
        )
    )
    return int(value or 0)


def _set_status(session: Session, status: str, error_code: str | None) -> None:
    row = session.get(HistorySearchState, STATE_KEY)
    now = datetime.now(UTC)
    if row is None:
        session.add(
            HistorySearchState(
                state_key=STATE_KEY,
                status=status,
                error_code=error_code,
                updated_at=now,
            )
        )
        return
    row.status = status
    row.error_code = error_code
    row.updated_at = now


def _mark_failed(session_factory: sessionmaker[Session]) -> None:
    session = session_factory()
    try:
        _set_status(session, "FAILED", "HISTORY_SEARCH_INCOMPLETE")
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def _add_hit(
    grouped: dict[str, list[dict[str, str]]],
    owner_id: str,
    section: str,
    record_id: str,
    source_id: str,
    snippet: str,
) -> None:
    found = grouped.setdefault(owner_id, [])
    if any(item["source_id"] == source_id and item["section"] == section for item in found):
        return
    found.append(
        {
            "section": section,
            "record_id": record_id,
            "source_id": source_id,
            "snippet": snippet,
        }
    )


def locations_for(hits: dict[str, list[dict[str, str]]], owner_id: str) -> list[dict[str, str]]:
    ranked = sorted(
        hits.get(owner_id, []),
        key=lambda item: (_SECTION_RANK.get(item["section"], 9), item["record_id"], item["source_id"]),
    )
    visible: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in ranked:
        key = (item["section"], item["record_id"])
        if key in seen:
            continue
        seen.add(key)
        visible.append(
            {
                "section": item["section"],
                "snippet": item["snippet"],
                "record_id": item["record_id"],
            }
        )
        if len(visible) >= MAX_LOCATIONS:
            break
    return visible


def _pieces(keyword: str) -> tuple[tuple[str, str], ...]:
    normalized = " ".join(unicodedata.normalize("NFKC", keyword).split())
    pieces: list[tuple[str, str]] = []
    index = 0
    while index < len(normalized):
        if _is_han(normalized[index]):
            end = index + 1
            while end < len(normalized) and _is_han(normalized[end]):
                end += 1
            pieces.append(("han", normalized[index:end]))
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
            pieces.append(("term", normalized[index:end].casefold()))
            index = end
            continue
        if not normalized[index].isspace():
            end = index + 1
            while (
                end < len(normalized)
                and not normalized[end].isalnum()
                and not _is_han(normalized[end])
                and not normalized[end].isspace()
            ):
                end += 1
            pieces.append(("symbol", normalized[index:end]))
            index = end
            continue
        index += 1
    return tuple(pieces)


def _content_matches(content: str, keyword: str, pieces: tuple[tuple[str, str], ...]) -> bool:
    if not pieces:
        return keyword.strip().casefold() in content.casefold()
    folded = content.casefold()
    for kind, value in pieces:
        if kind == "han":
            if value not in content:
                return False
        elif value not in folded:
            return False
    return True


def _snippet(content: str, keyword: str, pieces: tuple[tuple[str, str], ...]) -> str:
    folded = content.casefold()
    needles = [keyword.strip()]
    needles.extend(value for _kind, value in pieces)
    index = -1
    needle = keyword.strip()
    for candidate in needles:
        if not candidate:
            continue
        found = folded.find(candidate.casefold())
        if found >= 0:
            index = found
            needle = candidate
            break
    if index < 0:
        index = 0
        needle = ""
    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(content), index + max(len(needle), 1) + SNIPPET_RADIUS)
    snippet = content[start:end].replace("\n", " ")
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(content):
        snippet = f"{snippet}…"
    if len(snippet) > SNIPPET_LIMIT:
        snippet = snippet[:SNIPPET_LIMIT]
    return snippet


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _is_han(character: str) -> bool:
    point = ord(character)
    return (
        0x3400 <= point <= 0x4DBF
        or 0x4E00 <= point <= 0x9FFF
        or 0xF900 <= point <= 0xFAFF
        or 0x20000 <= point <= 0x2FA1F
    )
