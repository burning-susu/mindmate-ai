"""Minimal learning owner: one evidence-backed question and one graded attempt."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mindmate.application.citations import CitationBindingError, bind_feedback_citations
from mindmate.application.evidence_gate import INSUFFICIENT_MESSAGE
from mindmate.application.history_search_index import sync_learning_search
from mindmate.application.hybrid_search import HybridAssessmentResult, HybridCandidate
from mindmate.application.learning_question_draft import (
    MOCK_MODEL,
    MOCK_NOTE,
    MOCK_PROVIDER,
    PROMPT_TEMPLATE_VERSION,
    draft_single_choice,
    feedback_copy,
)
from mindmate.application.learning_summary import ensure_learning_summary
from mindmate.application.source_snapshots import (
    SourceSnapshotCreated,
    SourceSnapshotError,
    create_source_snapshots,
    read_source_snapshot,
)
from mindmate.infrastructure.models import (
    Chunk,
    FileRecord,
    IndexVersion,
    KnowledgeBase,
    KnowledgeBaseFile,
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
    QuestionEvidence,
    new_id,
)

DEFAULT_QUESTION_COUNT = 1
MAX_DEMO_QUESTION_COUNT = 5
SOURCE_INVALID_DETAIL = "学习范围的资料已失效，不能继续作答，也不会改用普通聊天。"


class LearningCommandError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        status: int = 400,
        *,
        current_row_version: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.current_row_version = current_row_version


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_learning_session(
    session: Session,
    *,
    session_factory: Callable[[], Session],
    topic: str,
    goal_text: str,
    goal_type: str,
    knowledge_base_id: str,
    target_question_count: int,
    idempotency_key: str,
    client_request_id: str,
    request_hash: str,
    request_id: str | None,
    encoder: Any,
    query: Any,
    confirm_provider_charge: bool = False,
    generation_mode: str | None = None,
    provider_runtime: Any = None,
) -> LearningSession:
    if not 1 <= target_question_count <= MAX_DEMO_QUESTION_COUNT:
        raise LearningCommandError(
            "QUESTION_COUNT_NOT_SUPPORTED", "逐题演示支持 1 到 5 道题。", 422
        )
    from mindmate.application.provider_configuration import read_generation_mode

    mode = generation_mode or read_generation_mode(session)
    if mode != "mock":
        from mindmate.application.learning_model_generation import create_provider_learning_session

        return create_provider_learning_session(
            session,
            session_factory=session_factory,
            topic=topic,
            goal_text=goal_text,
            goal_type=goal_type,
            knowledge_base_id=knowledge_base_id,
            target_question_count=target_question_count,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_hash=request_hash,
            request_id=request_id,
            encoder=encoder,
            query=query,
            mode=mode,
            runtime=provider_runtime,
        )
    if not idempotency_key or not client_request_id:
        raise LearningCommandError("IDEMPOTENCY_KEY_REQUIRED", "需要 Idempotency-Key。", 400)
    existing = _existing_session(
        session, idempotency_key=idempotency_key, client_request_id=client_request_id
    )
    if existing is not None and existing.status != "PREPARING":
        _assert_same_request(existing, request_hash)
        return existing
    knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None or knowledge_base.deleted_at is not None:
        raise LearningCommandError("KNOWLEDGE_BASE_NOT_FOUND", "知识库不存在。", 404)
    now = utc_now()
    record = existing
    if record is None:
        record = LearningSession(
            learning_session_id=new_id(),
            topic=topic,
            goal_type=goal_type[:40] or "CUSTOM",
            goal_text=goal_text,
            knowledge_base_id=knowledge_base_id,
            target_question_count=target_question_count,
            status="PREPARING",
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_hash=request_hash,
            provider=MOCK_PROVIDER,
            live_model_called=False,
            created_at=now,
            updated_at=now,
            row_version=1,
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raced = _existing_session(
                session,
                idempotency_key=idempotency_key,
                client_request_id=client_request_id,
            )
            if raced is None:
                raise
            if raced.status != "PREPARING":
                _assert_same_request(raced, request_hash)
                return raced
            record = raced
    else:
        _assert_same_request(record, request_hash)

    version_id = knowledge_base.active_index_version_id
    version = session.get(IndexVersion, version_id) if version_id else None
    ready = (
        version is not None
        and version.status == "READY"
        and version.scope_type == "KNOWLEDGE_BASE"
        and version.scope_id == knowledge_base_id
    )
    members = _active_members(session, knowledge_base_id) if ready else []
    scope = _ensure_scope(
        session,
        record,
        knowledge_base_id=knowledge_base_id,
        index_version_id=version.index_version_id if ready and version is not None else None,
        members=members,
        now=now,
    )
    if not ready or version is None:
        return _fail(
            session,
            record,
            code="INDEX_UNAVAILABLE",
            detail="当前知识库没有可用的活动索引，不能出题。",
        )
    if not members:
        return _fail(
            session,
            record,
            code="EVIDENCE_INSUFFICIENT",
            detail="当前资料范围没有可用文件，不能生成无来源的题目。",
        )
    session.commit()
    try:
        result = _retrieve(
            session,
            encoder=encoder,
            query=query,
            knowledge_base_id=knowledge_base_id,
            index_version_id=version.index_version_id,
            topic=topic,
        )
    except LearningCommandError as exc:
        return _fail(session, record, code=exc.code, detail=exc.detail)
    session.rollback()
    if result.assessment.status == "insufficient":
        reasons = "、".join(result.assessment.reason_codes[:5]) or "EMPTY_RESULTS"
        return _fail(
            session,
            record,
            code="EVIDENCE_INSUFFICIENT",
            detail=f"{INSUFFICIENT_MESSAGE}证据门控：{reasons}。",
        )
    if result.assessment.status != "supported":
        code = result.retrieval_error_code or "RETRIEVAL_UNAVAILABLE"
        return _fail(
            session,
            record,
            code=code,
            detail="索引或检索当前不可用，不能出题，也不会改用普通聊天。",
        )
    approved = _approved_candidates(result)
    if not approved:
        return _fail(
            session,
            record,
            code="EVIDENCE_INSUFFICIENT",
            detail=f"{INSUFFICIENT_MESSAGE}证据门控：EVIDENCE_NOT_SUPPORTED。",
        )
    try:
        snapshots = create_source_snapshots(
            session_factory,
            knowledge_base_id=knowledge_base_id,
            expected_index_version_id=version.index_version_id,
            result=result,
        )
    except SourceSnapshotError as exc:
        return _fail(
            session,
            record,
            code=exc.code,
            detail="来源在出题前已变化或失效，不能生成无来源的题目。",
        )
    excerpts: list[str] = []
    snapshot_by_chunk = {item.chunk_id: item for item in snapshots}
    usable: list[tuple[HybridCandidate, str, SourceSnapshotCreated]] = []
    for candidate in approved:
        chunk = session.get(Chunk, candidate.chunk_id)
        snapshot = snapshot_by_chunk.get(candidate.chunk_id)
        if chunk is None or snapshot is None or not chunk.content.strip():
            continue
        excerpts.append(chunk.content)
        usable.append((candidate, chunk.content, snapshot))
    draft = draft_single_choice(excerpts, source_hash=scope.source_set_hash)
    if draft is None:
        return _fail(
            session,
            record,
            code="CANNOT_FORM_RELIABLE_QUESTION",
            detail="已找到的资料不能确定唯一答案，已停止出题。",
        )
    linked = [
        item
        for item in usable
        if f"{draft.value} {draft.unit}" in _collapse(item[1])
    ][:2]
    if not linked:
        return _fail(
            session,
            record,
            code="CANNOT_FORM_RELIABLE_QUESTION",
            detail="已找到的资料不能确定唯一答案，已停止出题。",
        )
    _persist_question(
        session,
        record=record,
        scope=scope,
        draft_title=draft.knowledge_point_title,
        prompt_text=draft.prompt_text,
        options=[{"option_id": option_id, "label": label} for option_id, label in draft.options],
        correct_option_id=draft.correct_option_id,
        linked=linked,
        request_id=request_id,
        generated_request_hash=request_hash,
        sequence_number=1,
        now=utc_now(),
    )
    session.commit()
    return record


@dataclass(frozen=True, slots=True)
class NextQuestionSources:
    scope: LearningScope
    sequence_number: int
    approved: tuple[HybridCandidate, ...]
    snapshots: tuple[SourceSnapshotCreated, ...]


def create_next_learning_question(
    session: Session,
    *,
    session_factory: Callable[[], Session],
    learning_session_id: str,
    expected_session_version: int,
    idempotency_key: str,
    client_request_id: str,
    request_hash: str,
    request_id: str | None,
    encoder: Any,
    query: Any,
    confirm_provider_charge: bool = False,
    provider_runtime: Any = None,
) -> LearningSession:
    if not idempotency_key or not client_request_id:
        raise LearningCommandError("IDEMPOTENCY_KEY_REQUIRED", "需要 Idempotency-Key。", 400)
    record = get_learning_session(session, learning_session_id)
    replay = session.scalar(
        select(LearningQuestion).where(
            LearningQuestion.learning_session_id == learning_session_id,
            LearningQuestion.generated_request_id == client_request_id,
        )
    )
    if replay is not None:
        if replay.generated_request_hash != request_hash:
            raise LearningCommandError(
                "IDEMPOTENCY_KEY_REUSED", "同一个请求 ID 不能用于不同的下一题请求。", 409
            )
        return record
    if record.pending_question_request_id is not None:
        if record.pending_question_request_id != client_request_id:
            raise LearningCommandError(
                "QUESTION_GENERATION_IN_PROGRESS", "下一题正在处理中，请等待同一次请求完成。", 409
            )
        if record.pending_question_request_hash != request_hash:
            raise LearningCommandError(
                "IDEMPOTENCY_KEY_REUSED", "同一个请求 ID 不能用于不同的下一题请求。", 409
            )
        return record
    if record.status == "IN_PROGRESS" and record.completed_question_count >= record.target_question_count:
        record.status = "COMPLETED"
        record.end_reason = "PLAN_COMPLETED"
        record.completed_at = record.completed_at or utc_now()
        record.updated_at = utc_now()
        record.row_version += 1
        finish_learning_plan(session, record)
        ensure_learning_summary(session, record)
        session.commit()
        return record
    if record.status in {"COMPLETED", "FAILED", "SOURCE_INVALID"}:
        return record
    if record.status != "IN_PROGRESS":
        raise LearningCommandError(
            "LEARNING_SESSION_NOT_READY", "学习会话当前不能生成下一题。", 409
        )
    if record.row_version != expected_session_version:
        raise LearningCommandError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "学习会话已变化，请重新读取后再生成下一题。",
            412,
            current_row_version=record.row_version,
        )
    if record.current_question_id is None:
        raise LearningCommandError(
            "QUESTION_NOT_READY", "当前没有已完成的题目可继续。", 409
        )
    current = session.get(LearningQuestion, record.current_question_id)
    attempt = load_attempt(session, record.current_question_id)
    if current is None or current.status != "ANSWERED" or attempt is None:
        raise LearningCommandError(
            "ANSWER_REQUIRED", "提交并保存当前题目的作答后才能生成下一题。", 409
        )
    if load_feedback(session, attempt.attempt_id) is None:
        raise LearningCommandError(
            "FEEDBACK_NOT_READY", "当前题目的评分尚未保存，不能生成下一题。", 409
        )
    if (record.provider or MOCK_PROVIDER).lower() != MOCK_PROVIDER:
        from mindmate.application.learning_model_generation import (
            _frozen_from_session,
            _require_gates,
        )

        frozen = _frozen_from_session(record, provider_runtime)
        _require_gates(
            session, frozen, provider_runtime, output_tokens=1024
        )

    now = utc_now()
    claimed = session.execute(
        update(LearningSession)
        .where(
            LearningSession.learning_session_id == learning_session_id,
            LearningSession.status == "IN_PROGRESS",
            LearningSession.row_version == expected_session_version,
            LearningSession.pending_question_request_id.is_(None),
        )
        .values(
            status="PREPARING",
            pending_question_request_id=client_request_id,
            pending_question_request_hash=request_hash,
            updated_at=now,
            row_version=expected_session_version + 1,
        )
    )
    if int(getattr(claimed, "rowcount", 0) or 0) != 1:
        session.rollback()
        session.expire(record)
        session.refresh(record)
        # A concurrent same-key request may have committed the question after
        # this transaction's initial snapshot. Re-check the durable idempotency
        # row before turning the lost CAS into a false version conflict.
        replay = session.scalar(
            select(LearningQuestion).where(
                LearningQuestion.learning_session_id == learning_session_id,
                LearningQuestion.generated_request_id == client_request_id,
            )
        )
        if replay is not None:
            if replay.generated_request_hash != request_hash:
                raise LearningCommandError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一个请求 ID 不能用于不同的下一题请求。",
                    409,
                )
            return record
        if (
            record.pending_question_request_id == client_request_id
            and record.pending_question_request_hash == request_hash
        ):
            return record
        raise LearningCommandError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "另一项操作已更新学习会话，请重新读取。",
            412,
            current_row_version=record.row_version,
        )
    session.commit()
    session.expire(record)
    session.refresh(record)
    prepared = _prepare_next_question_sources(
        session,
        record=record,
        session_factory=session_factory,
        encoder=encoder,
        query=query,
    )
    if prepared is None:
        return record
    if (record.provider or MOCK_PROVIDER).lower() == MOCK_PROVIDER:
        return _create_mock_next_question(
            session,
            record=record,
            prepared=prepared,
            client_request_id=client_request_id,
            request_hash=request_hash,
            request_id=request_id,
        )
    from mindmate.application.learning_model_generation import (
        create_provider_next_learning_question,
    )

    return create_provider_next_learning_question(
        session,
        record=record,
        prepared=prepared,
        client_request_id=client_request_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_id=request_id,
        runtime=provider_runtime,
    )


def _prepare_next_question_sources(
    session: Session,
    *,
    record: LearningSession,
    session_factory: Callable[[], Session],
    encoder: Any,
    query: Any,
) -> NextQuestionSources | None:
    scope = load_scope(session, record.learning_session_id)
    knowledge_base = session.get(KnowledgeBase, record.knowledge_base_id)
    version = session.get(IndexVersion, scope.index_version_id) if scope and scope.index_version_id else None
    if (
        scope is None
        or scope.knowledge_base_id != record.knowledge_base_id
        or version is None
        or version.status != "READY"
        or knowledge_base is None
        or knowledge_base.deleted_at is not None
        or knowledge_base.active_index_version_id != scope.index_version_id
        or not _active_members(session, record.knowledge_base_id)
    ):
        _stop_question_generation(
            session,
            record,
            status="SOURCE_INVALID",
            code="SOURCE_INVALID",
            detail=SOURCE_INVALID_DETAIL,
        )
        return None
    assert scope is not None and scope.index_version_id is not None
    try:
        result = _retrieve(
            session,
            encoder=encoder,
            query=query,
            knowledge_base_id=scope.knowledge_base_id,
            index_version_id=scope.index_version_id,
            topic=record.topic,
        )
    except LearningCommandError as exc:
        _stop_question_generation(
            session, record, status="FAILED", code=exc.code, detail=exc.detail
        )
        return None
    session.rollback()
    if result.assessment.status != "supported":
        detail = (
            "当前资料没有足够的新事实支撑下一题。已保留已完成题目。"
            if result.assessment.status == "insufficient"
            else "索引或检索当前不可用，已保留已完成题目。"
        )
        _stop_question_generation(
            session,
            record,
            status="COMPLETED" if result.assessment.status == "insufficient" else "FAILED",
            code="EVIDENCE_INSUFFICIENT" if result.assessment.status == "insufficient" else "RETRIEVAL_UNAVAILABLE",
            detail=detail,
            end_reason="EVIDENCE_EXHAUSTED" if result.assessment.status == "insufficient" else None,
        )
        return None
    approved = _approved_candidates(result)
    if not approved:
        _stop_question_generation(
            session,
            record,
            status="COMPLETED",
            code="EVIDENCE_INSUFFICIENT",
            detail="当前资料没有足够的新事实支撑下一题。已保留已完成题目。",
            end_reason="EVIDENCE_EXHAUSTED",
        )
        return None
    try:
        snapshots = create_source_snapshots(
            session_factory,
            knowledge_base_id=scope.knowledge_base_id,
            expected_index_version_id=scope.index_version_id or "",
            result=result,
        )
    except SourceSnapshotError as exc:
        _stop_question_generation(
            session,
            record,
            status="SOURCE_INVALID",
            code=exc.code,
            detail="来源在出题前已变化或失效。已保留已完成题目。",
        )
        return None
    snapshot_ids = {item.chunk_id for item in snapshots}
    usable = tuple(item for item in approved if item.chunk_id in snapshot_ids)
    if not usable:
        _stop_question_generation(
            session,
            record,
            status="COMPLETED",
            code="EVIDENCE_INSUFFICIENT",
            detail="已批准的来源无法再确认。已保留已完成题目。",
            end_reason="EVIDENCE_EXHAUSTED",
        )
        return None
    return NextQuestionSources(
        scope=scope,
        sequence_number=record.completed_question_count + 1,
        approved=usable,
        snapshots=snapshots,
    )


def _create_mock_next_question(
    session: Session,
    *,
    record: LearningSession,
    prepared: NextQuestionSources,
    client_request_id: str,
    request_hash: str,
    request_id: str | None,
) -> LearningSession:
    snapshot_by_chunk = {item.chunk_id: item for item in prepared.snapshots}
    seen_facts = _known_question_facts(session, record.learning_session_id)
    for candidate in prepared.approved:
        chunk = session.get(Chunk, candidate.chunk_id)
        snapshot = snapshot_by_chunk.get(candidate.chunk_id)
        content = chunk.content if chunk is not None else (candidate.content or "")
        if snapshot is None or not content.strip():
            continue
        draft = draft_single_choice(
            [content],
            source_hash=f"{prepared.scope.source_set_hash}:{prepared.sequence_number}",
            excluded_facts=seen_facts,
        )
        if draft is None:
            continue
        linked = [(candidate, content, snapshot)]
        options = [{"option_id": key, "label": label} for key, label in draft.options]
        if _question_is_duplicate(
            session,
            record.learning_session_id,
            draft.knowledge_point_title,
            draft.prompt_text,
            draft.correct_label,
            linked,
        ):
            continue
        _persist_question(
            session,
            record=record,
            scope=prepared.scope,
            draft_title=draft.knowledge_point_title,
            prompt_text=draft.prompt_text,
            options=options,
            correct_option_id=draft.correct_option_id,
            linked=linked,
            request_id=client_request_id,
            now=utc_now(),
            generated_request_hash=request_hash,
            sequence_number=prepared.sequence_number,
        )
        session.commit()
        sync_learning_search(session, record.learning_session_id)
        session.commit()
        return record
    _stop_question_generation(
        session,
        record,
        status="COMPLETED",
        code="EVIDENCE_INSUFFICIENT",
        detail="当前资料没有足够的新事实支撑下一题。已保留已完成题目。",
        end_reason="EVIDENCE_EXHAUSTED",
    )
    return record


def _stop_question_generation(
    session: Session,
    record: LearningSession,
    *,
    status: str,
    code: str,
    detail: str,
    end_reason: str | None = None,
) -> None:
    now = utc_now()
    record.status = status
    record.failure_code = code[:80]
    record.failure_detail = detail[:500]
    record.end_reason = end_reason
    record.pending_question_request_id = None
    record.pending_question_request_hash = None
    record.completed_at = now if status == "COMPLETED" else record.completed_at
    record.updated_at = now
    record.row_version += 1
    if status in {"COMPLETED", "FAILED", "SOURCE_INVALID"}:
        finish_learning_plan(session, record)
        ensure_learning_summary(session, record)
    session.commit()


def _known_question_facts(session: Session, learning_session_id: str) -> set[tuple[str, str]]:
    facts: set[tuple[str, str]] = set()
    questions = session.scalars(
        select(LearningQuestion).where(
            LearningQuestion.learning_session_id == learning_session_id
        )
    )
    for question in questions:
        point = session.get(KnowledgePoint, question.knowledge_point_id)
        correct_id = str(question.answer_key_json.get("option_id", ""))
        label = next(
            (item["label"] for item in question.options_json if item["option_id"] == correct_id),
            "",
        )
        facts.add((_normalize_fact(point.canonical_title if point else ""), _normalize_fact(label)))
    return facts


def _question_is_duplicate(
    session: Session,
    learning_session_id: str,
    title: str,
    prompt_text: str,
    correct_label: str,
    linked: list[tuple[HybridCandidate, str, SourceSnapshotCreated]],
) -> bool:
    new_title = _normalize_fact(title)
    new_prompt = _normalize_fact(prompt_text)
    new_answer = _normalize_fact(correct_label)
    new_chunks = {item[0].chunk_id for item in linked}
    for previous in session.scalars(
        select(LearningQuestion).where(
            LearningQuestion.learning_session_id == learning_session_id
        )
    ):
        point = session.get(KnowledgePoint, previous.knowledge_point_id)
        previous_title = _normalize_fact(point.canonical_title if point else "")
        previous_prompt = _normalize_fact(previous.prompt_text)
        option_id = str(previous.answer_key_json.get("option_id", ""))
        previous_answer = _normalize_fact(
            next(
                (item["label"] for item in previous.options_json if item["option_id"] == option_id),
                "",
            )
        )
        previous_chunks = set(
            session.scalars(
                select(QuestionEvidence.chunk_id).where(
                    QuestionEvidence.question_id == previous.question_id,
                    QuestionEvidence.chunk_id.is_not(None),
                )
            )
        )
        if new_title == previous_title or new_prompt == previous_prompt:
            return True
        if new_answer == previous_answer and new_chunks.intersection(previous_chunks):
            return True
    return False


def _normalize_fact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]", "", normalized)


def get_learning_session(session: Session, learning_session_id: str) -> LearningSession:
    record = session.get(LearningSession, learning_session_id)
    if record is None or record.deleted_at is not None:
        raise LearningCommandError("LEARNING_SESSION_NOT_FOUND", "学习会话不存在。", 404)
    _refresh_source_state(session, record)
    if (
        record.status == "IN_PROGRESS"
        and record.completed_question_count >= record.target_question_count
    ):
        now = utc_now()
        record.status = "COMPLETED"
        record.end_reason = record.end_reason or "PLAN_COMPLETED"
        record.completed_at = record.completed_at or now
        record.updated_at = now
        record.row_version += 1
        finish_learning_plan(session, record)
        ensure_learning_summary(session, record)
        session.commit()
    return record


def finish_learning_session(
    session: Session,
    learning_session_id: str,
    *,
    expected_session_version: int,
) -> LearningSession:
    record = get_learning_session(session, learning_session_id)
    if record.status == "COMPLETED":
        ensure_learning_summary(session, record)
        session.commit()
        return record
    if record.status == "PREPARING":
        raise LearningCommandError(
            "QUESTION_GENERATION_IN_PROGRESS", "下一题正在处理中，完成后才能结束。", 409
        )
    if record.row_version != expected_session_version:
        raise LearningCommandError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "学习会话已变化，请重新读取后再结束。",
            412,
            current_row_version=record.row_version,
        )
    now = utc_now()
    finish_learning_plan(session, record)
    result = session.execute(
        update(LearningSession)
        .where(
            LearningSession.learning_session_id == learning_session_id,
            LearningSession.row_version == expected_session_version,
            LearningSession.status.in_(["IN_PROGRESS", "FAILED", "SOURCE_INVALID"]),
        )
        .values(
            status="COMPLETED",
            end_reason="USER_ENDED",
            pending_question_request_id=None,
            pending_question_request_hash=None,
            completed_at=now,
            updated_at=now,
            row_version=expected_session_version + 1,
        )
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        session.rollback()
        session.expire(record)
        session.refresh(record)
        if record.status == "COMPLETED":
            return record
        raise LearningCommandError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "学习会话已被其他操作更新，请重新读取。",
            412,
            current_row_version=record.row_version,
        )
    session.expire(record)
    session.refresh(record)
    ensure_learning_summary(session, record)
    sync_learning_search(session, learning_session_id)
    session.commit()
    session.expire(record)
    session.refresh(record)
    return record


def current_question(session: Session, learning_session_id: str) -> LearningQuestion:
    record = get_learning_session(session, learning_session_id)
    if record.current_question_id is None:
        raise LearningCommandError(
            record.failure_code or "QUESTION_NOT_AVAILABLE",
            record.failure_detail or "这次学习没有可作答的题目。",
            409,
        )
    question = session.get(LearningQuestion, record.current_question_id)
    if question is None:
        raise LearningCommandError("QUESTION_NOT_AVAILABLE", "这次学习没有可作答的题目。", 409)
    return question


def submit_learning_attempt(
    session: Session,
    *,
    question_id: str,
    selected_option: str,
    expected_question_version: int,
    idempotency_key: str,
    client_request_id: str,
    confirm_provider_charge: bool = False,
    provider_runtime: Any = None,
) -> LearningAttempt:
    if not idempotency_key or not client_request_id:
        raise LearningCommandError("IDEMPOTENCY_KEY_REQUIRED", "需要 Idempotency-Key。", 400)
    question = session.get(LearningQuestion, question_id)
    if question is None:
        raise LearningCommandError("LEARNING_QUESTION_NOT_FOUND", "题目不存在。", 404)
    record = get_learning_session(session, question.learning_session_id)
    if (record.provider or MOCK_PROVIDER) != MOCK_PROVIDER:
        from mindmate.application.learning_model_generation import submit_provider_learning_attempt

        return submit_provider_learning_attempt(
            session,
            question_id=question_id,
            selected_option=selected_option,
            expected_question_version=expected_question_version,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            confirm_provider_charge=confirm_provider_charge,
            runtime=provider_runtime,
        )
    question = session.get(LearningQuestion, question_id)
    if question is None:
        raise LearningCommandError("LEARNING_QUESTION_NOT_FOUND", "题目不存在。", 404)
    existing = _existing_attempt(
        session,
        question_id=question_id,
        idempotency_key=idempotency_key,
        client_request_id=client_request_id,
    )
    if existing is not None:
        return existing
    if load_attempt(session, question_id) is not None:
        raise LearningCommandError("ANSWER_LOCKED", "这道题已经提交，不能再次计分。", 409)
    if record.status == "SOURCE_INVALID":
        raise LearningCommandError("SOURCE_INVALID", SOURCE_INVALID_DETAIL, 409)
    if record.status != "IN_PROGRESS":
        raise LearningCommandError(
            record.failure_code or "QUESTION_NOT_AVAILABLE",
            record.failure_detail or "这次学习不能作答。",
            409,
        )
    options = {item["option_id"]: item["label"] for item in question.options_json}
    if selected_option not in options:
        raise LearningCommandError("OPTION_NOT_IN_QUESTION", "选项不属于这道题。", 400)
    if question.row_version != expected_question_version or question.status != "OPEN":
        if question.status != "OPEN":
            raise LearningCommandError("ANSWER_LOCKED", "这道题已经提交，不能再次计分。", 409)
        raise LearningCommandError(
            "RESOURCE_VERSION_CONFLICT",
            "题目版本已变化，本次不会覆盖。请刷新后重试。",
            412,
            current_row_version=question.row_version,
        )
    correct_option_id = str(question.answer_key_json["option_id"])
    correct = selected_option == correct_option_id
    correct_label = options[correct_option_id]
    selected_label = options[selected_option]
    explanation, strengths, missing = feedback_copy(
        selected_label=selected_label,
        correct_label=correct_label,
        correct=correct,
    )
    if MOCK_NOTE not in explanation or "DeepSeek" in explanation:
        raise LearningCommandError("LEARNING_FEEDBACK_INVALID", "反馈文案不符合演示边界。", 500)
    now = utc_now()
    claimed = session.execute(
        update(LearningQuestion)
        .where(
            LearningQuestion.question_id == question_id,
            LearningQuestion.status == "OPEN",
            LearningQuestion.row_version == expected_question_version,
        )
        .values(status="ANSWERED", row_version=LearningQuestion.row_version + 1)
    )
    if int(getattr(claimed, "rowcount", 0) or 0) != 1:
        session.rollback()
        replay = _existing_attempt(
            session,
            question_id=question_id,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
        )
        if replay is not None:
            return replay
        raise LearningCommandError("ANSWER_LOCKED", "这道题已经提交，不能再次计分。", 409)
    attempt = LearningAttempt(
        attempt_id=new_id(),
        question_id=question_id,
        learning_session_id=record.learning_session_id,
        attempt_number=1,
        answer_content=selected_label,
        selected_option=selected_option,
        status="SUBMITTED",
        client_request_id=client_request_id,
        idempotency_key=idempotency_key,
        submitted_at=now,
        reviewed_at=now,
    )
    feedback = LearningFeedback(
        feedback_id=new_id(),
        attempt_id=attempt.attempt_id,
        result="CORRECT" if correct else "INCORRECT",
        strengths=strengths or None,
        missing_points=missing or None,
        explanation=explanation,
        learning_signal="CORRECT" if correct else "INCORRECT",
        provider=MOCK_PROVIDER,
        model=MOCK_MODEL,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        created_at=now,
    )
    session.add(attempt)
    session.add(feedback)
    session.flush()
    evidences = list(
        session.scalars(
            select(QuestionEvidence)
            .where(QuestionEvidence.question_id == question_id)
            .order_by(QuestionEvidence.created_at)
        )
    )
    snapshots = [
        SourceSnapshotCreated(
            source_snapshot_id=item.source_snapshot_id or "",
            knowledge_base_id=record.knowledge_base_id,
            index_version_id=item.index_version_id,
            file_id=item.file_id or "",
            chunk_id=item.chunk_id or "",
            binding_status="UNBOUND",
            created_at=now,
        )
        for item in evidences
        if item.source_snapshot_id
    ]
    try:
        bind_feedback_citations(
            session,
            learning_feedback_id=feedback.feedback_id,
            snapshots=snapshots,
            created_at=now,
        )
    except CitationBindingError as exc:
        session.rollback()
        raise LearningCommandError("SOURCE_INVALID", SOURCE_INVALID_DETAIL, 409) from exc
    record.completed_question_count += 1
    if record.completed_question_count >= record.target_question_count:
        record.status = "COMPLETED"
        record.end_reason = "PLAN_COMPLETED"
        record.completed_at = now
    update_learning_plan_after_attempt(session, record, question)
    record.updated_at = now
    record.row_version += 1
    ensure_learning_summary(session, record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = _existing_attempt(
            session,
            question_id=question_id,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
        )
        if replay is not None:
            return replay
        raise LearningCommandError("ANSWER_LOCKED", "这道题已经提交，不能再次计分。", 409) from None
    return attempt


def load_feedback(session: Session, attempt_id: str) -> LearningFeedback | None:
    return session.scalar(
        select(LearningFeedback).where(LearningFeedback.attempt_id == attempt_id)
    )


def load_attempt(session: Session, question_id: str) -> LearningAttempt | None:
    return session.scalar(
        select(LearningAttempt).where(LearningAttempt.question_id == question_id)
    )


def load_plan(session: Session, learning_session_id: str) -> LearningPlan | None:
    return session.scalar(
        select(LearningPlan).where(LearningPlan.learning_session_id == learning_session_id)
    )


def update_learning_plan_after_attempt(
    session: Session, record: LearningSession, question: LearningQuestion
) -> None:
    plan = load_plan(session, record.learning_session_id)
    if plan is None:
        return
    item = session.scalar(
        select(LearningPlanItem).where(
            LearningPlanItem.learning_plan_id == plan.learning_plan_id,
            LearningPlanItem.sequence_number == question.sequence_number,
        )
    )
    if item is not None:
        item.status = "COMPLETED"
    plan.status = (
        "COMPLETED"
        if record.completed_question_count >= record.target_question_count
        else "IN_PROGRESS"
    )


def finish_learning_plan(session: Session, record: LearningSession) -> None:
    plan = load_plan(session, record.learning_session_id)
    if plan is not None:
        plan.status = (
            "COMPLETED"
            if record.completed_question_count >= record.target_question_count
            else "PARTIAL"
        )


def load_scope(session: Session, learning_session_id: str) -> LearningScope | None:
    return session.scalar(
        select(LearningScope).where(LearningScope.learning_session_id == learning_session_id)
    )


def scope_file_ids(session: Session, learning_scope_id: str) -> list[str]:
    return list(
        session.scalars(
            select(LearningScopeFile.file_id)
            .where(LearningScopeFile.learning_scope_id == learning_scope_id)
            .order_by(LearningScopeFile.file_id)
        )
    )


def knowledge_point_title(session: Session, knowledge_point_id: str | None) -> str | None:
    if knowledge_point_id is None:
        return None
    point = session.get(KnowledgePoint, knowledge_point_id)
    return None if point is None else point.canonical_title


def request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _retrieve(
    session: Session,
    *,
    encoder: Any,
    query: Any,
    knowledge_base_id: str,
    index_version_id: str,
    topic: str,
) -> HybridAssessmentResult:
    if encoder is None or query is None:
        raise LearningCommandError(
            "MODEL_UNAVAILABLE",
            "本地检索模型不可用，不能出题。",
            409,
        )
    try:
        signature = query.capture_scope_signature(session, knowledge_base_id, index_version_id)
        vector = encoder.embed_query(topic)
        return query.search_and_assess_with_status(
            session,
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            query_text=topic,
            query_vector=vector,
            allow_degraded=False,
            expected_scope_signature=signature,
        )
    except LearningCommandError:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", "") or "RETRIEVAL_UNAVAILABLE")
        if code == "RetrievalQueryEncoderError":
            code = "MODEL_UNAVAILABLE"
        raise LearningCommandError(
            code,
            "索引或检索当前不可用，不能出题，也不会改用普通聊天。",
            409,
        ) from exc


def _approved_candidates(result: HybridAssessmentResult) -> tuple[HybridCandidate, ...]:
    if result.retrieval is None or result.assessment.status != "supported":
        return ()
    candidates = {candidate.chunk_id: candidate for candidate in result.retrieval.candidates}
    approved: list[HybridCandidate] = []
    seen: set[str] = set()
    for signal in result.assessment.signals:
        if not signal.supporting or signal.identity.chunk_id in seen:
            continue
        candidate = candidates.get(signal.identity.chunk_id)
        if candidate is None:
            continue
        if (
            candidate.file_id != signal.identity.file_id
            or candidate.index_version_id != signal.identity.index_version_id
        ):
            continue
        approved.append(candidate)
        seen.add(candidate.chunk_id)
    return tuple(approved)


def _persist_question(
    session: Session,
    *,
    record: LearningSession,
    scope: LearningScope,
    draft_title: str,
    prompt_text: str,
    options: list[dict[str, str]],
    correct_option_id: str,
    linked: list[tuple[HybridCandidate, str, SourceSnapshotCreated]],
    request_id: str | None,
    now: datetime,
    generated_request_hash: str | None = None,
    sequence_number: int = 1,
    provider: str = MOCK_PROVIDER,
    prompt_template_version: str = PROMPT_TEMPLATE_VERSION,
    difficulty: str = "BASIC",
    live_model_called: bool = False,
    requested_model: str | None = None,
    resolved_model: str | None = None,
) -> None:
    normalized = unicodedata.normalize("NFKC", draft_title).casefold()[:80]
    identity = hashlib.sha256(
        f"{scope.knowledge_base_id}:{scope.index_version_id}:{normalized}".encode()
    ).hexdigest()
    point = KnowledgePoint(
        knowledge_point_id=new_id(),
        canonical_title=draft_title,
        normalized_title=normalized,
        description="由当前资料范围中可唯一判定的数值事实组成。",
        scope_identity_hash=identity,
        source_set_hash=scope.source_set_hash,
        created_at=now,
        updated_at=now,
    )
    plan = load_plan(session, record.learning_session_id)
    if plan is None:
        plan = LearningPlan(
            learning_plan_id=new_id(),
            learning_session_id=record.learning_session_id,
            plan_version=1,
            target_question_count=record.target_question_count,
            question_type_mix_json={"SINGLE_CHOICE": record.target_question_count},
            source_set_hash=scope.source_set_hash,
            index_version_id=scope.index_version_id or "",
            prompt_template_version=prompt_template_version,
            status="READY",
            created_at=now,
        )
        session.add(plan)
    question = LearningQuestion(
        question_id=new_id(),
        learning_session_id=record.learning_session_id,
        knowledge_point_id=point.knowledge_point_id,
        question_type="SINGLE_CHOICE",
        prompt_text=prompt_text,
        options_json=options,
        difficulty=difficulty,
        answer_key_json={"option_id": correct_option_id},
        acceptable_points_json=None,
        grading_rule_json={"type": "EXACT_OPTION"},
        sequence_number=sequence_number,
        status="OPEN",
        generated_request_id=request_id,
        generated_request_hash=generated_request_hash,
        prompt_template_version=prompt_template_version,
        provider=provider,
        row_version=1,
        created_at=now,
    )
    session.add(point)
    session.add(
        LearningPlanItem(
            learning_plan_item_id=new_id(),
            learning_plan_id=plan.learning_plan_id,
            knowledge_point_id=point.knowledge_point_id,
            sequence_number=sequence_number,
            target_question_count=1,
            status="READY",
        )
    )
    session.add(question)
    for candidate, _content, snapshot in linked:
        session.add(
            KnowledgePointEvidence(
                knowledge_point_evidence_id=new_id(),
                knowledge_point_id=point.knowledge_point_id,
                chunk_id=candidate.chunk_id,
                file_id=candidate.file_id,
                index_version_id=candidate.index_version_id,
                created_at=now,
            )
        )
        session.add(
            QuestionEvidence(
                question_evidence_id=new_id(),
                question_id=question.question_id,
                source_snapshot_id=snapshot.source_snapshot_id,
                chunk_id=candidate.chunk_id,
                file_id=candidate.file_id,
                index_version_id=candidate.index_version_id,
                evidence_role="ANSWER_KEY",
                created_at=now,
            )
        )
    record.status = "IN_PROGRESS"
    record.failure_code = None
    record.failure_detail = None
    record.end_reason = None
    record.current_knowledge_point_id = point.knowledge_point_id
    record.current_question_id = question.question_id
    record.started_at = now
    record.updated_at = now
    record.row_version += 1
    record.provider = provider
    record.requested_model = requested_model
    record.resolved_model = resolved_model
    record.live_model_called = live_model_called
    record.pending_question_request_id = None
    record.pending_question_request_hash = None


def _ensure_scope(
    session: Session,
    record: LearningSession,
    *,
    knowledge_base_id: str,
    index_version_id: str | None,
    members: list[tuple[KnowledgeBaseFile, FileRecord]],
    now: datetime,
) -> LearningScope:
    scope = load_scope(session, record.learning_session_id)
    source_hash = _source_hash(members, index_version_id)
    if scope is None:
        scope = LearningScope(
            learning_scope_id=new_id(),
            learning_session_id=record.learning_session_id,
            knowledge_base_id=knowledge_base_id,
            index_version_id=index_version_id,
            source_set_hash=source_hash,
            created_at=now,
        )
        session.add(scope)
        session.flush()
        for membership, file_record in members:
            session.add(
                LearningScopeFile(
                    learning_scope_file_id=new_id(),
                    learning_scope_id=scope.learning_scope_id,
                    file_id=file_record.file_id,
                    content_hash=file_record.content_hash,
                    parse_revision_id=file_record.parse_revision_id,
                    index_version_id=index_version_id,
                    created_at=membership.added_at,
                )
            )
        return scope
    return scope


def _refresh_source_state(session: Session, record: LearningSession) -> None:
    if record.status in {"FAILED", "SOURCE_INVALID"}:
        return
    scope = load_scope(session, record.learning_session_id)
    if scope is None or record.status not in {"IN_PROGRESS", "COMPLETED"}:
        return
    invalid = scope.index_version_id is None
    knowledge_base = session.get(KnowledgeBase, scope.knowledge_base_id)
    version = (
        session.get(IndexVersion, scope.index_version_id) if scope.index_version_id else None
    )
    if (
        knowledge_base is None
        or knowledge_base.deleted_at is not None
        or version is None
        or version.status != "READY"
        or knowledge_base.active_index_version_id != scope.index_version_id
    ):
        invalid = True
    if not invalid:
        for file_id in scope_file_ids(session, scope.learning_scope_id):
            file_record = session.get(FileRecord, file_id)
            scope_file = session.scalar(
                select(LearningScopeFile).where(
                    LearningScopeFile.learning_scope_id == scope.learning_scope_id,
                    LearningScopeFile.file_id == file_id,
                )
            )
            if (
                file_record is None
                or file_record.deleted_at is not None
                or scope_file is None
                or file_record.content_hash != scope_file.content_hash
            ):
                invalid = True
                break
    if not invalid and record.current_question_id is not None:
        evidences = session.scalars(
            select(QuestionEvidence).where(
                QuestionEvidence.question_id == record.current_question_id
            )
        )
        for evidence in evidences:
            if evidence.source_snapshot_id is None:
                invalid = True
                break
            try:
                view = read_source_snapshot(session, evidence.source_snapshot_id)
            except SourceSnapshotError:
                invalid = True
                break
            if view.source_status != "AVAILABLE":
                invalid = True
                break
    if not invalid:
        return
    record.status = "SOURCE_INVALID"
    record.failure_code = "SOURCE_INVALID"
    record.failure_detail = SOURCE_INVALID_DETAIL
    finish_learning_plan(session, record)
    record.updated_at = utc_now()
    record.row_version += 1
    ensure_learning_summary(session, record)
    session.commit()


def _fail(
    session: Session,
    record: LearningSession,
    *,
    code: str,
    detail: str,
    preserve_identity: bool = False,
) -> LearningSession:
    now = utc_now()
    record.status = "FAILED"
    record.failure_code = code[:80]
    record.failure_detail = detail[:500]
    record.end_reason = "EVIDENCE_EXHAUSTED" if code == "EVIDENCE_INSUFFICIENT" else None
    finish_learning_plan(session, record)
    record.pending_question_request_id = None
    record.pending_question_request_hash = None
    if not preserve_identity:
        record.provider = MOCK_PROVIDER
        record.live_model_called = False
        record.requested_model = None
        record.resolved_model = None
    record.updated_at = now
    record.row_version += 1
    ensure_learning_summary(session, record)
    session.commit()
    return record


def _existing_session(
    session: Session, *, idempotency_key: str, client_request_id: str
) -> LearningSession | None:
    by_key = session.scalar(
        select(LearningSession).where(LearningSession.idempotency_key == idempotency_key)
    )
    by_client = session.scalar(
        select(LearningSession).where(LearningSession.client_request_id == client_request_id)
    )
    if by_key is not None and by_client is not None and by_key.learning_session_id != by_client.learning_session_id:
        raise LearningCommandError(
            "CLIENT_REQUEST_ID_REUSED",
            "client_request_id 已用于其他学习请求。",
            409,
        )
    if by_client is not None and by_key is None:
        raise LearningCommandError(
            "CLIENT_REQUEST_ID_REUSED",
            "client_request_id 已用于其他学习请求。",
            409,
        )
    return by_key or by_client


def _assert_same_request(record: LearningSession, request_hash_value: str) -> None:
    if record.request_hash != request_hash_value:
        raise LearningCommandError(
            "IDEMPOTENCY_KEY_REUSED",
            "幂等键已用于不同的学习请求。请为新请求生成新的幂等键。",
            409,
        )


def _existing_attempt(
    session: Session,
    *,
    question_id: str,
    idempotency_key: str,
    client_request_id: str,
) -> LearningAttempt | None:
    by_key = session.scalar(
        select(LearningAttempt).where(
            LearningAttempt.question_id == question_id,
            LearningAttempt.idempotency_key == idempotency_key,
        )
    )
    by_client = session.scalar(
        select(LearningAttempt).where(
            LearningAttempt.question_id == question_id,
            LearningAttempt.client_request_id == client_request_id,
        )
    )
    if (
        by_key is not None
        and by_client is not None
        and by_key.attempt_id != by_client.attempt_id
    ):
        raise LearningCommandError(
            "CLIENT_REQUEST_ID_REUSED",
            "client_request_id 已用于其他作答。",
            409,
        )
    if by_client is not None and by_key is None:
        raise LearningCommandError("ANSWER_LOCKED", "这道题已经提交，不能再次计分。", 409)
    if by_key is not None and by_client is None:
        raise LearningCommandError(
            "IDEMPOTENCY_KEY_REUSED",
            "幂等键已用于不同的作答。",
            409,
        )
    return by_key


def _active_members(
    session: Session, knowledge_base_id: str
) -> list[tuple[KnowledgeBaseFile, FileRecord]]:
    rows = session.execute(
        select(KnowledgeBaseFile, FileRecord)
        .join(FileRecord, FileRecord.file_id == KnowledgeBaseFile.file_id)
        .where(
            KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseFile.membership_status == "ACTIVE",
            KnowledgeBaseFile.removed_at.is_(None),
            FileRecord.deleted_at.is_(None),
            FileRecord.status == "PARSED",
        )
        .order_by(FileRecord.file_id)
    )
    return [(membership, file_record) for membership, file_record in rows]


def _source_hash(
    members: list[tuple[KnowledgeBaseFile, FileRecord]], index_version_id: str | None
) -> str:
    parts = [
        f"{file_record.file_id}:{file_record.content_hash}:{file_record.parse_revision_id or ''}"
        for _membership, file_record in members
    ]
    parts.append(index_version_id or "")
    return hashlib.sha256("\n".join(sorted(parts)).encode()).hexdigest()


def _collapse(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


TRASH_RETENTION_DAYS = 30


def trash_learning_session(
    session: Session, learning_session_id: str, *, expected_version: int
) -> LearningSession:
    """Soft-delete the session row only. Questions, attempts and sources stay."""
    record = session.get(LearningSession, learning_session_id)
    if record is None:
        raise LearningCommandError("LEARNING_SESSION_NOT_FOUND", "学习会话不存在。", 404)
    if record.deleted_at is not None:
        return record
    now = utc_now()
    result = session.execute(
        update(LearningSession)
        .where(
            LearningSession.learning_session_id == learning_session_id,
            LearningSession.row_version == expected_version,
            LearningSession.deleted_at.is_(None),
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
        raise LearningCommandError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "学习会话已被其他操作更新，请重新加载后再移入回收站。",
            412,
            current_row_version=record.row_version,
        )
    session.expire(record)
    session.refresh(record)
    sync_learning_search(session, learning_session_id)
    session.commit()
    session.expire(record)
    session.refresh(record)
    return record


def restore_learning_session(
    session: Session, learning_session_id: str, *, expected_version: int
) -> LearningSession:
    """Restore the same session id. Does not create questions or answers."""
    record = session.get(LearningSession, learning_session_id)
    if record is None:
        raise LearningCommandError("LEARNING_SESSION_NOT_FOUND", "学习会话不存在。", 404)
    if record.deleted_at is None:
        return record
    now = utc_now()
    result = session.execute(
        update(LearningSession)
        .where(
            LearningSession.learning_session_id == learning_session_id,
            LearningSession.row_version == expected_version,
            LearningSession.deleted_at.is_not(None),
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
        raise LearningCommandError(
            "LEARNING_SESSION_VERSION_CONFLICT",
            "学习会话已被其他操作更新，请重新加载后再恢复。",
            412,
            current_row_version=record.row_version,
        )
    session.expire(record)
    session.refresh(record)
    sync_learning_search(session, learning_session_id)
    session.commit()
    session.expire(record)
    session.refresh(record)
    return record
