"""Minimal learning session API. Responses never include the answer key."""

from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from mindmate.api.files import get_session
from mindmate.application.citations import citation_payload, list_feedback_citations
from mindmate.application.hybrid_search import HybridCandidateQuery
from mindmate.application.learning_question_draft import MOCK_MODEL, MOCK_PROVIDER
from mindmate.application.learning_sessions import (
    LearningCommandError,
    create_learning_session,
    current_question,
    get_learning_session,
    knowledge_point_title,
    load_attempt,
    load_feedback,
    load_plan,
    load_scope,
    request_hash,
    scope_file_ids,
    submit_learning_attempt,
)
from mindmate.infrastructure.vector_store import SqliteVecAdapter

router = APIRouter(prefix="/api/v1")


class LearningApiError(Exception):
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


class LearningSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_base_id: str = Field(min_length=1, max_length=36)
    topic: str = Field(min_length=1, max_length=80)
    goal_text: str = Field(min_length=1, max_length=200)
    goal_type: str = Field(default="CUSTOM", min_length=1, max_length=40)
    target_question_count: int = Field(default=1)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)


class LearningAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_option: str = Field(min_length=1, max_length=32)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_question_version: int = Field(ge=1)


class LearningOptionResponse(BaseModel):
    option_id: str
    label: str


class LearningCitationResponse(BaseModel):
    citation_id: str
    display_number: int
    file_name: str
    file_id: str | None
    chunk_id: str | None
    line_start: int | None
    line_end: int | None
    page_start: int | None
    page_end: int | None
    excerpt: str | None
    source_status: str
    can_open_source: bool


class LearningFeedbackResponse(BaseModel):
    feedback_id: str
    attempt_id: str
    selected_option: str
    result: str
    explanation: str
    provider: str
    model: str
    live_model_called: bool
    citations: list[LearningCitationResponse]


class LearningQuestionResponse(BaseModel):
    question_id: str
    learning_session_id: str
    question_type: str
    prompt_text: str
    options: list[LearningOptionResponse]
    sequence_number: int
    status: str
    difficulty: str
    row_version: int
    feedback: LearningFeedbackResponse | None = None


class LearningPlanResponse(BaseModel):
    learning_plan_id: str
    status: str
    target_question_count: int
    knowledge_point_title: str | None
    prompt_template_version: str


class LearningScopeResponse(BaseModel):
    knowledge_base_id: str
    index_version_id: str | None
    source_set_hash: str
    file_ids: list[str]


class LearningSessionResponse(BaseModel):
    learning_session_id: str
    topic: str
    goal_type: str
    goal_text: str
    knowledge_base_id: str
    target_question_count: int
    status: str
    failure_code: str | None
    failure_detail: str | None
    completed_question_count: int
    current_question_id: str | None
    provider: str
    model: str
    live_model_called: bool
    row_version: int
    created_at: datetime
    started_at: datetime | None
    scope: LearningScopeResponse | None
    plan: LearningPlanResponse | None
    question: LearningQuestionResponse | None


def _command_error(exc: LearningCommandError) -> LearningApiError:
    return LearningApiError(
        exc.code,
        exc.detail,
        exc.status,
        current_row_version=exc.current_row_version,
    )


def _encoder(request: Request) -> Any:
    getter = getattr(request.app.state, "learning_encoder_getter", None)
    if getter is not None:
        return getter()
    return getattr(request.app.state, "retrieval_query_encoder", None)


def _query(request: Request) -> Any:
    getter = getattr(request.app.state, "learning_query_getter", None)
    if getter is not None:
        return getter(request.app.state.settings)
    settings = request.app.state.settings
    return HybridCandidateQuery(SqliteVecAdapter(settings.vectors_dir))


def _feedback_payload(
    session: Session, attempt_id: str, selected_option: str
) -> LearningFeedbackResponse | None:
    feedback = load_feedback(session, attempt_id)
    if feedback is None:
        return None
    citations = [
        LearningCitationResponse(
            citation_id=item["citation_id"],
            display_number=item["display_number"],
            file_name=item["file_name"],
            file_id=item["file_id"],
            chunk_id=item["chunk_id"],
            line_start=item["line_start"],
            line_end=item["line_end"],
            page_start=item["page_start"],
            page_end=item["page_end"],
            excerpt=item["excerpt"],
            source_status=item["source_status"],
            can_open_source=item["can_open_source"],
        )
        for item in (
            citation_payload(session, record)
            for record in list_feedback_citations(session, feedback.feedback_id)
        )
    ]
    return LearningFeedbackResponse(
        feedback_id=feedback.feedback_id,
        attempt_id=attempt_id,
        selected_option=selected_option,
        result=feedback.result,
        explanation=feedback.explanation,
        provider=feedback.provider,
        model=feedback.model,
        live_model_called=False,
        citations=citations,
    )


def _question_payload(session: Session, question: Any) -> dict[str, Any]:
    attempt = load_attempt(session, question.question_id)
    feedback = None
    if attempt is not None:
        feedback = _feedback_payload(session, attempt.attempt_id, attempt.selected_option)
    return LearningQuestionResponse(
        question_id=question.question_id,
        learning_session_id=question.learning_session_id,
        question_type=question.question_type,
        prompt_text=question.prompt_text,
        options=[
            LearningOptionResponse(option_id=item["option_id"], label=item["label"])
            for item in question.options_json
        ],
        sequence_number=question.sequence_number,
        status=question.status,
        difficulty=question.difficulty,
        row_version=question.row_version,
        feedback=feedback,
    ).model_dump(mode="json")


def _session_payload(session: Session, record: Any) -> dict[str, Any]:
    scope = load_scope(session, record.learning_session_id)
    plan = load_plan(session, record.learning_session_id)
    question_payload = None
    if record.current_question_id is not None:
        from mindmate.infrastructure.models import LearningQuestion

        question = session.get(LearningQuestion, record.current_question_id)
        if question is not None:
            question_payload = LearningQuestionResponse.model_validate(
                _question_payload(session, question)
            )
    scope_payload = None
    if scope is not None:
        scope_payload = LearningScopeResponse(
            knowledge_base_id=scope.knowledge_base_id,
            index_version_id=scope.index_version_id,
            source_set_hash=scope.source_set_hash,
            file_ids=scope_file_ids(session, scope.learning_scope_id),
        )
    plan_payload = None
    if plan is not None:
        plan_payload = LearningPlanResponse(
            learning_plan_id=plan.learning_plan_id,
            status=plan.status,
            target_question_count=plan.target_question_count,
            knowledge_point_title=knowledge_point_title(
                session, record.current_knowledge_point_id
            ),
            prompt_template_version=plan.prompt_template_version,
        )
    return LearningSessionResponse(
        learning_session_id=record.learning_session_id,
        topic=record.topic,
        goal_type=record.goal_type,
        goal_text=record.goal_text,
        knowledge_base_id=record.knowledge_base_id,
        target_question_count=record.target_question_count,
        status=record.status,
        failure_code=record.failure_code,
        failure_detail=record.failure_detail,
        completed_question_count=record.completed_question_count,
        current_question_id=record.current_question_id,
        provider=record.provider or MOCK_PROVIDER,
        model=MOCK_MODEL,
        live_model_called=False,
        row_version=record.row_version,
        created_at=record.created_at,
        started_at=record.started_at,
        scope=scope_payload,
        plan=plan_payload,
        question=question_payload,
    ).model_dump(mode="json")


@router.post(
    "/learning-sessions",
    response_model=LearningSessionResponse,
    tags=["learning"],
)
def create_session(
    payload: LearningSessionCreateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    idempotency_key = request.headers.get("idempotency-key", "").strip()
    client_request_id = payload.client_request_id or idempotency_key
    body = payload.model_dump(mode="json")
    try:
        record = create_learning_session(
            session,
            session_factory=request.app.state.session_factory,
            topic=payload.topic.strip(),
            goal_text=payload.goal_text.strip(),
            goal_type=payload.goal_type.strip(),
            knowledge_base_id=payload.knowledge_base_id,
            target_question_count=payload.target_question_count,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_hash=request_hash(body),
            request_id=getattr(request.state, "request_id", None),
            encoder=_encoder(request),
            query=_query(request),
        )
    except LearningCommandError as exc:
        raise _command_error(exc) from exc
    return _session_payload(session, record)


@router.get(
    "/learning-sessions/{learning_session_id}",
    response_model=LearningSessionResponse,
    tags=["learning"],
)
def read_session(
    learning_session_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        record = get_learning_session(session, learning_session_id)
    except LearningCommandError as exc:
        raise _command_error(exc) from exc
    return _session_payload(session, record)


@router.get(
    "/learning-sessions/{learning_session_id}/current-question",
    response_model=LearningQuestionResponse,
    tags=["learning"],
)
def read_current_question(
    learning_session_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        question = current_question(session, learning_session_id)
    except LearningCommandError as exc:
        raise _command_error(exc) from exc
    return _question_payload(session, question)


@router.post(
    "/learning-questions/{question_id}/attempts",
    response_model=LearningFeedbackResponse,
    tags=["learning"],
)
def create_attempt(
    question_id: str,
    payload: LearningAttemptRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    idempotency_key = request.headers.get("idempotency-key", "").strip()
    client_request_id = payload.client_request_id or idempotency_key
    try:
        attempt = submit_learning_attempt(
            session,
            question_id=question_id,
            selected_option=payload.selected_option,
            expected_question_version=payload.expected_question_version,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
        )
    except LearningCommandError as exc:
        raise _command_error(exc) from exc
    feedback = _feedback_payload(session, attempt.attempt_id, attempt.selected_option)
    if feedback is None:
        raise LearningApiError("LEARNING_FEEDBACK_MISSING", "作答反馈没有保存。", 500)
    return feedback.model_dump(mode="json")
