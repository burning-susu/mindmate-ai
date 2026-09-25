from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
import json
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mindmate.ai.providers.base import ChatProviderPort
from mindmate.api.files import get_session
from mindmate.application.chat_generation import (
    GENERAL_CHAT_MODE,
    ChatCommandError,
    create_chat_message,
    create_first_chat,
    request_chat_stop,
)
from mindmate.infrastructure.models import (
    AiOperation,
    AnswerVersion,
    BackgroundTask,
    Conversation,
    Message,
    TaskEvent,
)

router = APIRouter(prefix="/api/v1")


class ChatApiError(Exception):
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


class FirstConversationRequest(BaseModel):
    mode: str = Field(default=GENERAL_CHAT_MODE, min_length=1, max_length=30)
    source_scope: dict[str, Any] | None = None
    first_message: str = Field(min_length=1, max_length=10_000)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_conversation_version: int | None = Field(default=None, ge=1)


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    status: str
    sequence_number: int
    request_id: str | None
    mode_snapshot: str
    conversation_scope_id: str | None
    parent_user_message_id: str | None
    revision_number: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ConversationResponse(BaseModel):
    conversation_id: str
    title: str
    title_source: str
    current_mode: str
    current_scope_type: str
    current_scope_id_list: list[str]
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    row_version: int
    active_operation_id: str | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    next_cursor: str | None = None


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: str | None = None


class AnswerVersionResponse(BaseModel):
    answer_version_id: str
    assistant_message_id: str
    version_number: int
    content: str
    status: str
    provider: str
    model: str
    prompt_template_version: str
    usage_input_tokens: int | None
    usage_output_tokens: int | None
    usage_total_tokens: int | None
    created_at: datetime


class AiOperationResponse(BaseModel):
    operation_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    status: str
    provider: str
    requested_model: str
    resolved_model: str | None
    prompt_template_version: str
    usage_input_tokens: int | None
    usage_output_tokens: int | None
    usage_total_tokens: int | None
    provider_request_id: str | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    stream_sequence: int = 0
    event_sequence: int = 0
    snapshot_content: str = ""
    stop_requested: bool = False
    user_message: MessageResponse | None = None
    assistant_message: MessageResponse | None = None
    answer_version: AnswerVersionResponse | None = None


class ConversationSubmissionResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    operation_id: str
    status: str
    status_url: str
    events_url: str | None
    conversation: ConversationResponse
    user_message: MessageResponse
    assistant_message: MessageResponse
    operation: AiOperationResponse


def _provider(request: Request) -> ChatProviderPort:
    provider = getattr(request.app.state, "chat_provider", None)
    if provider is None:
        raise ChatApiError("CHAT_PROVIDER_UNAVAILABLE", "普通聊天 Provider 当前不可用。", 503)
    return provider


def _command_error(exc: ChatCommandError) -> ChatApiError:
    return ChatApiError(
        exc.code,
        exc.detail,
        exc.status,
        current_row_version=exc.current_row_version,
    )


def _message_payload(message: Message | None) -> dict[str, Any] | None:
    if message is None:
        return None
    return {
        "message_id": message.message_id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "sequence_number": message.sequence_number,
        "request_id": message.request_id,
        "mode_snapshot": message.mode_snapshot,
        "conversation_scope_id": message.conversation_scope_id,
        "parent_user_message_id": message.parent_user_message_id,
        "revision_number": message.revision_number,
        "archived_at": message.archived_at,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "completed_at": message.completed_at,
    }


def _conversation_payload(session: Session, conversation: Conversation) -> dict[str, Any]:
    count = session.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation.conversation_id, Message.archived_at.is_(None))
    ) or 0
    active_operation = session.scalar(
        select(AiOperation)
        .where(
            AiOperation.conversation_id == conversation.conversation_id,
            AiOperation.status.in_({"QUEUED", "RUNNING", "STOPPING"}),
        )
        .order_by(AiOperation.created_at.desc())
        .limit(1)
    )
    return {
        "conversation_id": conversation.conversation_id,
        "title": conversation.title,
        "title_source": conversation.title_source,
        "current_mode": conversation.current_mode,
        "current_scope_type": conversation.current_scope_type,
        "current_scope_id_list": list(conversation.current_scope_id_list or []),
        "status": conversation.status,
        "message_count": int(count),
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "last_active_at": conversation.last_active_at,
        "row_version": conversation.row_version,
        "active_operation_id": active_operation.operation_id if active_operation else None,
    }


def _operation_payload(session: Session, operation: AiOperation) -> dict[str, Any]:
    user = session.get(Message, operation.user_message_id)
    assistant = session.get(Message, operation.assistant_message_id)
    answer = session.scalar(
        select(AnswerVersion)
        .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
        .order_by(AnswerVersion.version_number.desc())
        .limit(1)
    )
    answer_payload = None
    if answer is not None:
        answer_payload = {
            "answer_version_id": answer.answer_version_id,
            "assistant_message_id": answer.assistant_message_id,
            "version_number": answer.version_number,
            "content": answer.content,
            "status": answer.status,
            "provider": answer.provider,
            "model": answer.model,
            "prompt_template_version": answer.prompt_template_version,
            "usage_input_tokens": answer.usage_input_tokens,
            "usage_output_tokens": answer.usage_output_tokens,
            "usage_total_tokens": answer.usage_total_tokens,
            "created_at": answer.created_at,
        }
    task = session.get(BackgroundTask, operation.task_id) if operation.task_id else None
    checkpoint = (task.checkpoint_json or {}) if task is not None else {}
    snapshot_content = str(checkpoint.get("content") or (assistant.content if assistant else ""))
    return {
        "operation_id": operation.operation_id,
        "conversation_id": operation.conversation_id,
        "user_message_id": operation.user_message_id,
        "assistant_message_id": operation.assistant_message_id,
        "status": operation.status,
        "provider": operation.provider,
        "requested_model": operation.requested_model,
        "resolved_model": operation.resolved_model,
        "prompt_template_version": operation.prompt_template_version,
        "usage_input_tokens": operation.usage_input_tokens,
        "usage_output_tokens": operation.usage_output_tokens,
        "usage_total_tokens": operation.usage_total_tokens,
        "provider_request_id": operation.provider_request_id,
        "error_code": operation.error_code,
        "error_detail": operation.error_detail,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
        "started_at": operation.started_at,
        "completed_at": operation.completed_at,
        "stream_sequence": int(checkpoint.get("stream_sequence", 0) or 0),
        "event_sequence": int(checkpoint.get("event_sequence", 0) or 0),
        "snapshot_content": snapshot_content,
        "stop_requested": bool(checkpoint.get("stop_requested", False)),
        "user_message": _message_payload(user),
        "assistant_message": _message_payload(assistant),
        "answer_version": answer_payload,
    }


def _submission_payload(session: Session, operation: AiOperation, request: Request) -> dict[str, Any]:
    conversation = session.get(Conversation, operation.conversation_id)
    user = session.get(Message, operation.user_message_id)
    assistant = session.get(Message, operation.assistant_message_id)
    if conversation is None or user is None or assistant is None:
        raise ChatApiError("CHAT_STATE_INVALID", "聊天提交结果不完整。", 500)
    return {
        "conversation_id": conversation.conversation_id,
        "user_message_id": user.message_id,
        "assistant_message_id": assistant.message_id,
        "operation_id": operation.operation_id,
        "status": operation.status,
        "status_url": f"/api/v1/ai-operations/{operation.operation_id}",
        "events_url": f"/api/v1/ai-operations/{operation.operation_id}/events",
        "conversation": _conversation_payload(session, conversation),
        "user_message": _message_payload(user),
        "assistant_message": _message_payload(assistant),
        "operation": _operation_payload(session, operation),
    }


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    tags=["chat"],
)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    records = session.scalars(
        select(Conversation)
        .where(Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return {"items": [_conversation_payload(session, record) for record in records], "next_cursor": None}


@router.post(
    "/conversations",
    response_model=ConversationSubmissionResponse,
    status_code=202,
    tags=["chat"],
)
def create_conversation(
    payload: FirstConversationRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    idempotency_key = request.headers.get("idempotency-key", "")
    client_request_id = payload.client_request_id or idempotency_key
    try:
        operation = create_first_chat(
            session,
            content=payload.first_message,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_id=request.state.request_id,
            body=payload.model_dump(mode="json"),
            provider=_provider(request),
            settings=request.app.state.settings,
        )
    except ChatCommandError as exc:
        raise _command_error(exc) from exc
    return _submission_payload(session, operation, request)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    tags=["chat"],
)
def get_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.deleted_at is not None:
        raise ChatApiError("CONVERSATION_NOT_FOUND", "会话不存在。", 404)
    return _conversation_payload(session, conversation)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationSubmissionResponse,
    status_code=202,
    tags=["chat"],
)
def create_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    idempotency_key = request.headers.get("idempotency-key", "")
    client_request_id = payload.client_request_id or idempotency_key
    try:
        operation = create_chat_message(
            session,
            conversation_id=conversation_id,
            content=payload.content,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_id=request.state.request_id,
            expected_version=payload.expected_conversation_version,
            body=payload.model_dump(mode="json"),
            provider=_provider(request),
            settings=request.app.state.settings,
        )
    except ChatCommandError as exc:
        raise _command_error(exc) from exc
    return _submission_payload(session, operation, request)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    tags=["chat"],
)
def list_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    before_sequence: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.deleted_at is not None:
        raise ChatApiError("CONVERSATION_NOT_FOUND", "会话不存在。", 404)
    statement = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.archived_at.is_(None),
    )
    if before_sequence is not None:
        statement = statement.where(Message.sequence_number < before_sequence)
    rows = list(
        session.scalars(statement.order_by(Message.sequence_number.desc()).limit(limit + 1))
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()
    return {
        "items": [_message_payload(row) for row in rows],
        "next_cursor": str(rows[0].sequence_number) if has_more and rows else None,
    }


@router.get(
    "/ai-operations/{operation_id}",
    response_model=AiOperationResponse,
    tags=["chat"],
)
def get_ai_operation(
    operation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    operation = session.get(AiOperation, operation_id)
    if operation is None:
        raise ChatApiError("AI_OPERATION_NOT_FOUND", "AI Operation 不存在。", 404)
    return _operation_payload(session, operation)


def _sse_line(event: TaskEvent, operation_id: str) -> str:
    payload = dict(event.payload_json or {})
    payload.setdefault("operation_id", operation_id)
    payload["event_sequence"] = event.sequence
    payload.setdefault("event_type", event.event_type)
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type.lower()}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _operation_event_stream(
    session_factory: Any,
    operation_id: str,
    after_event: int,
):
    """Yield durable task events until the operation reaches a terminal state."""
    cursor = max(0, after_event)
    deadline = time.monotonic() + 300
    terminal_states = {"COMPLETED", "FAILED", "STOPPED", "INTERRUPTED"}
    while time.monotonic() < deadline:
        events: list[TaskEvent] = []
        terminal = False
        with session_factory() as stream_session:
            operation = stream_session.get(AiOperation, operation_id)
            if operation is None or operation.task_id is None:
                return
            terminal = operation.status in terminal_states
            events = list(
                stream_session.scalars(
                    select(TaskEvent)
                    .where(
                        TaskEvent.task_id == operation.task_id,
                        TaskEvent.sequence > cursor,
                    )
                    .order_by(TaskEvent.sequence)
                )
            )
        if events:
            for event in events:
                cursor = event.sequence
                yield _sse_line(event, operation_id)
            if terminal or any(
                event.event_type in {"COMPLETED", "FAILED", "STOPPED", "INTERRUPTED"}
                for event in events
            ):
                return
            continue
        if terminal:
            return
        time.sleep(0.05)


@router.post(
    "/ai-operations/{operation_id}/stop",
    response_model=AiOperationResponse,
    tags=["chat"],
)
@router.post(
    "/ai-operations/{operation_id}/cancel",
    response_model=AiOperationResponse,
    include_in_schema=False,
    tags=["chat"],
)
def stop_ai_operation(
    operation_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        operation = request_chat_stop(session, operation_id)
    except ChatCommandError as exc:
        raise _command_error(exc) from exc
    return _operation_payload(session, operation)


@router.get(
    "/ai-operations/{operation_id}/events",
    response_class=StreamingResponse,
    tags=["chat"],
)
@router.get(
    "/ai-operations/{operation_id}/stream",
    response_class=StreamingResponse,
    include_in_schema=False,
    tags=["chat"],
)
def stream_ai_operation(
    operation_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    operation = session.get(AiOperation, operation_id)
    if operation is None or operation.task_id is None:
        raise ChatApiError("AI_OPERATION_NOT_FOUND", "AI Operation 不存在。", 404)
    header_cursor = request.headers.get("last-event-id")
    if header_cursor and header_cursor.isdigit():
        after = max(after, int(header_cursor))
    factory = request.app.state.session_factory
    return StreamingResponse(
        _operation_event_stream(factory, operation_id, after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router", "ChatApiError"]
