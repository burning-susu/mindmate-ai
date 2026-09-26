"""Minimal learning owner: one evidence-backed question and one graded attempt."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mindmate.application.citations import CitationBindingError, bind_feedback_citations
from mindmate.application.evidence_gate import INSUFFICIENT_MESSAGE
from mindmate.application.hybrid_search import HybridAssessmentResult, HybridCandidate
from mindmate.application.learning_question_draft import (
    MOCK_MODEL,
    MOCK_NOTE,
    MOCK_PROVIDER,
    PROMPT_TEMPLATE_VERSION,
    draft_single_choice,
    feedback_copy,
)
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

FIXED_QUESTION_COUNT = 1
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
) -> LearningSession:
    if target_question_count != FIXED_QUESTION_COUNT:
        raise LearningCommandError(
            "QUESTION_COUNT_NOT_SUPPORTED",
            "这一批演示只接受 1 道题。",
            422,
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
            target_question_count=FIXED_QUESTION_COUNT,
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
        now=utc_now(),
    )
    session.commit()
    return record


def get_learning_session(session: Session, learning_session_id: str) -> LearningSession:
    record = session.get(LearningSession, learning_session_id)
    if record is None or record.deleted_at is not None:
        raise LearningCommandError("LEARNING_SESSION_NOT_FOUND", "学习会话不存在。", 404)
    _refresh_source_state(session, record)
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
) -> LearningAttempt:
    if not idempotency_key or not client_request_id:
        raise LearningCommandError("IDEMPOTENCY_KEY_REQUIRED", "需要 Idempotency-Key。", 400)
    question = session.get(LearningQuestion, question_id)
    if question is None:
        raise LearningCommandError("LEARNING_QUESTION_NOT_FOUND", "题目不存在。", 404)
    record = get_learning_session(session, question.learning_session_id)
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
    record.completed_question_count = 1
    record.updated_at = now
    record.row_version += 1
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
    plan = LearningPlan(
        learning_plan_id=new_id(),
        learning_session_id=record.learning_session_id,
        plan_version=1,
        target_question_count=FIXED_QUESTION_COUNT,
        question_type_mix_json={"SINGLE_CHOICE": 1},
        source_set_hash=scope.source_set_hash,
        index_version_id=scope.index_version_id or "",
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        status="READY",
        created_at=now,
    )
    question = LearningQuestion(
        question_id=new_id(),
        learning_session_id=record.learning_session_id,
        knowledge_point_id=point.knowledge_point_id,
        question_type="SINGLE_CHOICE",
        prompt_text=prompt_text,
        options_json=options,
        difficulty="BASIC",
        answer_key_json={"option_id": correct_option_id},
        acceptable_points_json=None,
        grading_rule_json={"type": "EXACT_OPTION"},
        sequence_number=1,
        status="OPEN",
        generated_request_id=request_id,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        provider=MOCK_PROVIDER,
        row_version=1,
        created_at=now,
    )
    session.add(point)
    session.add(plan)
    session.add(
        LearningPlanItem(
            learning_plan_item_id=new_id(),
            learning_plan_id=plan.learning_plan_id,
            knowledge_point_id=point.knowledge_point_id,
            sequence_number=1,
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
    record.current_knowledge_point_id = point.knowledge_point_id
    record.current_question_id = question.question_id
    record.started_at = now
    record.updated_at = now
    record.row_version += 1
    record.provider = MOCK_PROVIDER
    record.live_model_called = False


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
    if scope is None or record.status != "IN_PROGRESS":
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
    record.updated_at = utc_now()
    record.row_version += 1
    session.commit()


def _fail(
    session: Session, record: LearningSession, *, code: str, detail: str
) -> LearningSession:
    now = utc_now()
    record.status = "FAILED"
    record.failure_code = code[:80]
    record.failure_detail = detail[:500]
    record.current_question_id = None
    record.provider = MOCK_PROVIDER
    record.live_model_called = False
    record.updated_at = now
    record.row_version += 1
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
