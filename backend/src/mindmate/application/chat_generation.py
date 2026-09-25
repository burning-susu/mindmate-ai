from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from uuid6 import uuid7

from mindmate.ai.providers.base import (
    ChatProviderPort,
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    ProviderRequestError,
)
from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL
from mindmate.application.provider_configuration import read_consent
from mindmate.application.tasks import add_event, claim_task, finish_attempt
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    AiOperation,
    AnswerVersion,
    BackgroundTask,
    Conversation,
    ConversationScope,
    Message,
    new_id,
)
from mindmate.security.credentials import CredentialStoreError, CredentialStorePort

CHAT_GENERATION_TASK = "AI_GENERATION"
GENERAL_CHAT_MODE = "GENERAL_CHAT"
GENERAL_SCOPE_TYPE = "NONE"
CHAT_PROMPT_TEMPLATE_VERSION = "general-chat-v1"
MAX_USER_MESSAGE_CHARS = 10_000
MAX_CONTEXT_CHARS = 64_000
MAX_OUTPUT_TOKENS = 2_048
MAX_OUTPUT_CHARS = 64_000
ACTIVE_OPERATION_STATES = {"QUEUED", "RUNNING", "STOPPING"}
TERMINAL_OPERATION_STATES = {"COMPLETED", "FAILED", "STOPPED", "INTERRUPTED"}
_SUBMISSION_LOCK = threading.RLock()


def utc_now() -> datetime:
    return datetime.now(UTC)


class ChatCommandError(Exception):
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


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise ChatCommandError("MESSAGE_EMPTY", "消息不能为空。", 422)
    if len(normalized) > MAX_USER_MESSAGE_CHARS:
        raise ChatCommandError(
            "MESSAGE_TOO_LARGE",
            f"单条普通聊天消息不能超过 {MAX_USER_MESSAGE_CHARS} 个字符。",
            413,
        )
    return normalized


def _provider_name(provider: ChatProviderPort) -> str:
    return str(getattr(provider, "provider_name", provider.__class__.__name__))[:50]


def _provider_model(provider: ChatProviderPort, settings: Settings) -> str:
    value = getattr(provider, "model", None) or getattr(settings, "provider_model", DEEPSEEK_MODEL)
    return str(value)[:100]


def _task_idempotency_key(idempotency_key: str) -> str:
    return "ai-op:" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def _validate_existing_operation(
    operation: AiOperation, expected_hash: str
) -> AiOperation:
    if operation.request_hash != expected_hash:
        raise ChatCommandError(
            "IDEMPOTENCY_KEY_REUSED",
            "幂等键已用于不同的普通聊天请求。请为新请求生成新的幂等键。",
            409,
        )
    return operation


def _existing_by_client_request(
    session: Session, client_request_id: str, idempotency_key: str
) -> AiOperation | None:
    operation = session.scalar(
        select(AiOperation).where(AiOperation.client_request_id == client_request_id)
    )
    if operation is not None and operation.idempotency_key != idempotency_key:
        raise ChatCommandError(
            "CLIENT_REQUEST_ID_REUSED",
            "client_request_id 已用于其他请求。请生成新的业务请求 ID。",
            409,
        )
    return operation


def _active_operation(session: Session, conversation_id: str) -> AiOperation | None:
    return session.scalar(
        select(AiOperation)
        .where(
            AiOperation.conversation_id == conversation_id,
            AiOperation.status.in_(ACTIVE_OPERATION_STATES),
        )
        .order_by(AiOperation.created_at)
        .limit(1)
    )


def _latest_scope(session: Session, conversation_id: str) -> ConversationScope | None:
    return session.scalar(
        select(ConversationScope)
        .where(
            ConversationScope.conversation_id == conversation_id,
            ConversationScope.ended_at.is_(None),
        )
        .order_by(ConversationScope.scope_version.desc())
        .limit(1)
    )


def _new_operation_graph(
    session: Session,
    *,
    conversation: Conversation,
    scope: ConversationScope,
    content: str,
    sequence_start: int,
    idempotency_key: str,
    client_request_id: str,
    request_id: str,
    body_hash: str,
    provider: ChatProviderPort,
    settings: Settings,
) -> AiOperation:
    now = utc_now()
    user_message = Message(
        message_id=new_id(),
        conversation_id=conversation.conversation_id,
        role="USER",
        content=content,
        status="SENT",
        sequence_number=sequence_start,
        request_id=client_request_id,
        mode_snapshot=GENERAL_CHAT_MODE,
        conversation_scope_id=scope.conversation_scope_id,
        revision_number=1,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    assistant_message = Message(
        message_id=new_id(),
        conversation_id=conversation.conversation_id,
        role="ASSISTANT",
        content="",
        status="PENDING",
        sequence_number=sequence_start + 1,
        request_id=None,
        mode_snapshot=GENERAL_CHAT_MODE,
        conversation_scope_id=scope.conversation_scope_id,
        parent_user_message_id=user_message.message_id,
        revision_number=1,
        created_at=now,
        updated_at=now,
    )
    session.add_all([user_message, assistant_message])
    session.flush()

    operation_id = new_id()
    task = BackgroundTask(
        task_id=new_id(),
        task_type=CHAT_GENERATION_TASK,
        status="QUEUED",
        phase="QUEUED",
        priority=100,
        idempotency_key=_task_idempotency_key(idempotency_key),
        checkpoint_json={
            "operation_id": operation_id,
            "conversation_id": conversation.conversation_id,
            "user_message_id": user_message.message_id,
            "assistant_message_id": assistant_message.message_id,
            "content": "",
            "stream_sequence": 0,
            "event_sequence": 0,
            "stop_requested": False,
        },
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    add_event(session, task, "QUEUED", {"operation_id": operation_id})

    operation = AiOperation(
        operation_id=operation_id,
        conversation_id=conversation.conversation_id,
        user_message_id=user_message.message_id,
        assistant_message_id=assistant_message.message_id,
        task_id=task.task_id,
        idempotency_key=idempotency_key,
        client_request_id=client_request_id,
        request_hash=body_hash,
        request_id=request_id,
        status="QUEUED",
        provider=_provider_name(provider),
        requested_model=_provider_model(provider, settings),
        prompt_template_version=CHAT_PROMPT_TEMPLATE_VERSION,
        created_at=now,
        updated_at=now,
        row_version=1,
    )
    answer = AnswerVersion(
        answer_version_id=new_id(),
        assistant_message_id=assistant_message.message_id,
        version_number=1,
        content="",
        status="PENDING",
        provider=_provider_name(provider),
        model=_provider_model(provider, settings),
        prompt_template_version=CHAT_PROMPT_TEMPLATE_VERSION,
        created_at=now,
    )
    session.add_all([operation, answer])
    return operation


def _commit_or_recover(
    session: Session, operation: AiOperation, body_hash: str
) -> AiOperation:
    try:
        session.commit()
        return operation
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(AiOperation).where(AiOperation.idempotency_key == operation.idempotency_key)
        )
        if existing is not None:
            return _validate_existing_operation(existing, body_hash)
        existing = session.scalar(
            select(AiOperation).where(AiOperation.client_request_id == operation.client_request_id)
        )
        if existing is not None:
            raise ChatCommandError(
                "CLIENT_REQUEST_ID_REUSED",
                "client_request_id 已用于其他请求。请生成新的业务请求 ID。",
                409,
            ) from None
        raise


def create_first_chat(
    session: Session,
    *,
    content: str,
    idempotency_key: str,
    client_request_id: str,
    request_id: str,
    body: dict[str, Any],
    provider: ChatProviderPort,
    settings: Settings,
) -> AiOperation:
    normalized = _validate_content(content)
    if body.get("mode", GENERAL_CHAT_MODE) != GENERAL_CHAT_MODE:
        raise ChatCommandError("CHAT_MODE_UNSUPPORTED", "本批只支持 GENERAL_CHAT 普通聊天。", 400)
    source_scope = body.get("source_scope")
    if source_scope not in (None, {}, {"scope_type": GENERAL_SCOPE_TYPE}, {"type": GENERAL_SCOPE_TYPE}):
        raise ChatCommandError(
            "CHAT_SCOPE_UNSUPPORTED",
            "本批普通聊天不接受知识库或文件资料范围。",
            400,
        )
    body_hash = request_hash({**body, "first_message": normalized})
    with _SUBMISSION_LOCK:
        existing = session.scalar(
            select(AiOperation).where(AiOperation.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return _validate_existing_operation(existing, body_hash)
        existing = _existing_by_client_request(session, client_request_id, idempotency_key)
        if existing is not None:
            return _validate_existing_operation(existing, body_hash)
        now = utc_now()
        conversation = Conversation(
            conversation_id=new_id(),
            title=normalized[:30],
            title_source="AUTO",
            current_mode=GENERAL_CHAT_MODE,
            current_scope_type=GENERAL_SCOPE_TYPE,
            current_scope_id_list=[],
            status="ACTIVE",
            created_at=now,
            updated_at=now,
            last_active_at=now,
            row_version=1,
        )
        session.add(conversation)
        session.flush()
        scope = ConversationScope(
            conversation_scope_id=new_id(),
            conversation_id=conversation.conversation_id,
            scope_version=1,
            mode=GENERAL_CHAT_MODE,
            scope_type=GENERAL_SCOPE_TYPE,
            created_at=now,
        )
        session.add(scope)
        session.flush()
        operation = _new_operation_graph(
            session,
            conversation=conversation,
            scope=scope,
            content=normalized,
            sequence_start=1,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_id=request_id,
            body_hash=body_hash,
            provider=provider,
            settings=settings,
        )
        return _commit_or_recover(session, operation, body_hash)


def create_chat_message(
    session: Session,
    *,
    conversation_id: str,
    content: str,
    idempotency_key: str,
    client_request_id: str,
    request_id: str,
    expected_version: int | None,
    body: dict[str, Any],
    provider: ChatProviderPort,
    settings: Settings,
) -> AiOperation:
    normalized = _validate_content(content)
    body_hash = request_hash({**body, "content": normalized})
    with _SUBMISSION_LOCK:
        existing = session.scalar(
            select(AiOperation).where(AiOperation.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return _validate_existing_operation(existing, body_hash)
        existing = _existing_by_client_request(session, client_request_id, idempotency_key)
        if existing is not None:
            return _validate_existing_operation(existing, body_hash)
        conversation = session.get(Conversation, conversation_id)
        if conversation is None or conversation.deleted_at is not None:
            raise ChatCommandError("CONVERSATION_NOT_FOUND", "会话不存在。", 404)
        if expected_version is not None and conversation.row_version != expected_version:
            raise ChatCommandError(
                "RESOURCE_VERSION_CONFLICT",
                f"会话已被更新，当前版本为 {conversation.row_version}，请刷新后重试。",
                412,
                current_row_version=conversation.row_version,
            )
        active = _active_operation(session, conversation_id)
        if active is not None:
            raise ChatCommandError(
                "CONVERSATION_GENERATION_IN_PROGRESS",
                "当前会话已有一条消息正在生成，请等待结果后再发送。",
                409,
            )
        scope = _latest_scope(session, conversation_id)
        if scope is None or scope.mode != GENERAL_CHAT_MODE:
            raise ChatCommandError("CHAT_SCOPE_UNAVAILABLE", "当前会话的普通聊天范围不可用。", 409)
        last_sequence = session.scalar(
            select(func.max(Message.sequence_number)).where(
                Message.conversation_id == conversation_id
            )
        ) or 0
        conversation.updated_at = utc_now()
        conversation.last_active_at = conversation.updated_at
        conversation.row_version += 1
        operation = _new_operation_graph(
            session,
            conversation=conversation,
            scope=scope,
            content=normalized,
            sequence_start=int(last_sequence) + 1,
            idempotency_key=idempotency_key,
            client_request_id=client_request_id,
            request_id=request_id,
            body_hash=body_hash,
            provider=provider,
            settings=settings,
        )
        return _commit_or_recover(session, operation, body_hash)


def recover_interrupted_chat_operations(session: Session) -> int:
    """Converge in-flight provider calls to an observable state without retrying them."""
    operations = list(
        session.scalars(
            select(AiOperation).where(AiOperation.status.in_({"RUNNING", "STOPPING"}))
        )
    )
    recovered = 0
    for operation in operations:
        checkpoint = {}
        task = session.get(BackgroundTask, operation.task_id) if operation.task_id else None
        if task is not None and task.checkpoint_json:
            checkpoint = copy.deepcopy(task.checkpoint_json)
        was_stopping = operation.status == "STOPPING" or bool(checkpoint.get("stop_requested"))
        operation.status = "STOPPED" if was_stopping else "INTERRUPTED"
        operation.error_code = "GENERATION_STOPPED" if was_stopping else "GENERATION_INTERRUPTED"
        operation.error_detail = (
            "用户已停止生成。"
            if was_stopping
            else "应用在生成过程中退出，未自动重发不确定的 Provider 请求。"
        )
        operation.updated_at = utc_now()
        operation.completed_at = operation.updated_at
        operation.row_version += 1
        assistant = session.get(Message, operation.assistant_message_id)
        if assistant is not None and assistant.status in {"PENDING", "STREAMING"}:
            assistant.status = "STOPPED" if was_stopping else "INTERRUPTED"
            assistant.updated_at = operation.updated_at
            assistant.completed_at = operation.updated_at
        answer = session.scalar(
            select(AnswerVersion)
            .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
            .order_by(AnswerVersion.version_number.desc())
            .limit(1)
        )
        if answer is not None and answer.status in {"PENDING", "STREAMING"}:
            answer.status = "STOPPED" if was_stopping else "INTERRUPTED"
        if task is not None and task.status in {"RUNNING", "QUEUED"}:
            task.status = "CANCELLED" if was_stopping else "INTERRUPTED"
            task.phase = "STOPPED" if was_stopping else "INTERRUPTED"
            task.error_summary = operation.error_detail
            task.lease_owner = None
            task.lease_until = None
            task.updated_at = operation.updated_at
            task.completed_at = operation.updated_at
            task.row_version += 1
            finish_attempt(
                session,
                task.task_id,
                "CANCELLED" if was_stopping else "INTERRUPTED",
                task.error_summary,
            )
            checkpoint["content"] = assistant.content if assistant is not None else checkpoint.get("content", "")
            checkpoint["final_status"] = operation.status
            task.checkpoint_json = checkpoint
            event = add_event(
                session,
                task,
                "STOPPED" if was_stopping else "INTERRUPTED",
                {
                    "operation_id": operation.operation_id,
                    "content": checkpoint.get("content", ""),
                    "sequence": int(checkpoint.get("stream_sequence", 0)),
                    "terminal": True,
                    "reason": "APPLICATION_RESTART",
                },
            )
            checkpoint["event_sequence"] = event.sequence
            task.checkpoint_json = checkpoint
        recovered += 1
    session.commit()
    return recovered


def request_chat_stop(session: Session, operation_id: str) -> AiOperation:
    """Record an idempotent stop request; the owner worker performs finalization."""
    operation = session.get(AiOperation, operation_id)
    if operation is None:
        raise ChatCommandError("AI_OPERATION_NOT_FOUND", "AI Operation 不存在。", 404)
    if operation.status in TERMINAL_OPERATION_STATES:
        return operation
    task = session.get(BackgroundTask, operation.task_id) if operation.task_id else None
    if task is None:
        raise ChatCommandError("CHAT_STATE_INVALID", "聊天生成任务不存在。", 409)
    checkpoint = copy.deepcopy(task.checkpoint_json or {})
    checkpoint["stop_requested"] = True
    task.checkpoint_json = checkpoint
    task.checkpoint_version += 1
    task.updated_at = utc_now()
    if operation.status in {"QUEUED", "RUNNING"}:
        operation.status = "STOPPING"
        operation.updated_at = task.updated_at
        operation.row_version += 1
        event = add_event(
            session,
            task,
            "STOP_REQUESTED",
            {
                "operation_id": operation.operation_id,
                "content": checkpoint.get("content", ""),
                "sequence": int(checkpoint.get("stream_sequence", 0)),
                "status": "STOPPING",
                "terminal": False,
            },
        )
        checkpoint["event_sequence"] = event.sequence
        task.checkpoint_json = checkpoint
    session.commit()
    return operation


def _message_context(session: Session, operation: AiOperation) -> tuple[dict[str, str], ...]:
    current_user = session.get(Message, operation.user_message_id)
    if current_user is None:
        return ()
    rows = list(
        session.scalars(
            select(Message)
            .where(
                Message.conversation_id == operation.conversation_id,
                Message.archived_at.is_(None),
                Message.status.in_({"SENT", "COMPLETED"}),
                Message.sequence_number <= current_user.sequence_number,
            )
            .order_by(Message.sequence_number.desc())
            .limit(20)
        )
    )
    rows.reverse()
    messages: list[dict[str, str]] = []
    total = 0
    for row in rows:
        if row.role not in {"USER", "ASSISTANT"} or not row.content:
            continue
        content = row.content[:MAX_USER_MESSAGE_CHARS]
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 0:
            break
        content = content[:remaining]
        messages.append({"role": row.role.lower(), "content": content})
        total += len(content)
    return tuple(messages)


def _chat_request(session: Session, operation: AiOperation) -> ChatRequest:
    return ChatRequest(
        request_id=operation.request_id or operation.client_request_id,
        task_type="GENERAL_CHAT",
        model_profile=operation.requested_model,
        system_instructions=(
            "你是 MindMate AI 的普通聊天助手。当前请求是 GENERAL_CHAT，"
            "不要声称答案来自本地文件或知识库，不生成本地引用；只回答用户明确提出的问题。"
        ),
        messages=_message_context(session, operation),
        temperature=0.6,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        reasoning_profile="LOW",
        timeout_profile="chat",
        stream=False,
        metadata={"conversation_id": operation.conversation_id},
    )


class ChatGenerationWorker:
    """Durable single-process worker for bounded general-chat generation."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings,
        provider_getter: Callable[[], ChatProviderPort],
        credential_store_getter: Callable[[], CredentialStorePort],
        *,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._provider_getter = provider_getter
        self._credential_store_getter = credential_store_getter
        self.worker_id = worker_id or f"chat-{uuid7()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._start_lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-chat-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.1, timeout))

    def _run(self) -> None:
        try:
            with self._session_factory() as session:
                recover_interrupted_chat_operations(session)
            while not self._stop_event.is_set():
                task_id = self._claim_one()
                if task_id is None:
                    self._stop_event.wait(max(0.02, self._settings.chat_worker_poll_seconds))
                    continue
                try:
                    self._process_task(task_id)
                except Exception:
                    self._fail_worker_task(task_id)
        finally:
            with self._session_factory() as session:
                for task in session.scalars(
                    select(BackgroundTask).where(
                        BackgroundTask.task_type == CHAT_GENERATION_TASK,
                        BackgroundTask.status == "RUNNING",
                        BackgroundTask.lease_owner == self.worker_id,
                    )
                ):
                    operation = session.scalar(
                        select(AiOperation).where(AiOperation.task_id == task.task_id)
                    )
                    if operation is not None:
                        self._mark_interrupted(session, operation, task)
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            candidates = session.scalars(
                select(BackgroundTask.task_id)
                .where(
                    BackgroundTask.task_type == CHAT_GENERATION_TASK,
                    BackgroundTask.status == "QUEUED",
                )
                .order_by(BackgroundTask.priority.desc(), BackgroundTask.created_at)
                .limit(32)
            )
            for task_id in candidates:
                task = claim_task(
                    session,
                    task_id,
                    self.worker_id,
                    self._settings.chat_worker_lease_seconds,
                )
                if task is not None:
                    session.commit()
                    return task.task_id
            session.rollback()
            return None

    @staticmethod
    def _checkpoint(task: BackgroundTask) -> dict[str, Any]:
        return copy.deepcopy(task.checkpoint_json or {})

    def _process_task(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            operation = session.scalar(select(AiOperation).where(AiOperation.task_id == task_id))
            if (
                task is None
                or operation is None
                or task.status != "RUNNING"
                or task.lease_owner != self.worker_id
            ):
                return
            checkpoint = self._checkpoint(task)
            if operation.status == "STOPPING" or checkpoint.get("stop_requested"):
                self._stop_operation(session, task, operation)
                session.commit()
                return
            if operation.status != "QUEUED":
                return
            assistant = session.get(Message, operation.assistant_message_id)
            answer = session.scalar(
                select(AnswerVersion)
                .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
                .order_by(AnswerVersion.version_number.desc())
                .limit(1)
            )
            if assistant is None or answer is None:
                self._fail_operation(session, task, operation, "CHAT_STATE_INVALID", "聊天生成状态不完整。")
                session.commit()
                return
            operation.status = "RUNNING"
            operation.started_at = operation.started_at or utc_now()
            operation.updated_at = utc_now()
            operation.row_version += 1
            assistant.status = "STREAMING"
            assistant.updated_at = operation.updated_at
            answer.status = "STREAMING"
            task.phase = "GENERATING"
            checkpoint["phase"] = "GENERATING"
            task.checkpoint_json = checkpoint
            task.checkpoint_version += 1
            task.updated_at = operation.updated_at
            request = _chat_request(session, operation)
            session.commit()

        provider = self._provider_getter()
        api_key: str | None = None
        stream: Any = None
        content = ""
        final_chunk: ChatStreamChunk | None = None
        try:
            if getattr(provider, "requires_external_transfer", True):
                with self._session_factory() as gate_session:
                    consent = read_consent(gate_session)
                if not consent.get("accepted"):
                    raise ProviderRequestError(
                        "EXTERNAL_AI_CONSENT_REQUIRED",
                        "普通聊天发送前必须先确认当前版本的数据外发说明。",
                        409,
                    )
                try:
                    api_key = self._credential_store_getter().get_secret("provider/deepseek/api-key")
                except CredentialStoreError as exc:
                    raise ProviderRequestError(
                        exc.code,
                        "本地凭据存储当前不可用，未发起 Provider 请求。",
                        503,
                        True,
                    ) from exc
                if not api_key:
                    raise ProviderRequestError(
                        "PROVIDER_NOT_CONFIGURED",
                        "尚未配置可用的 DeepSeek API Key。",
                        409,
                    )
            # Test/runtime injection keeps the established non-streaming fixture
            # path when the application itself is still in Mock mode.  The real
            # DeepSeek runtime uses its SSE adapter below.
            stream_factory = getattr(provider, "generate_stream", None)
            if (
                getattr(provider, "provider_name", "") == "DEEPSEEK"
                and self._settings.provider_mode == "mock"
            ):
                stream_factory = None
            if callable(stream_factory):
                stream = stream_factory(request, api_key)
                for raw_chunk in stream:
                    if isinstance(raw_chunk, ChatResponse):
                        chunk = ChatStreamChunk(
                            request_id=raw_chunk.request_id,
                            delta=raw_chunk.content,
                            finish_reason=raw_chunk.finish_reason,
                            provider=raw_chunk.provider,
                            requested_model=raw_chunk.requested_model,
                            resolved_model=raw_chunk.resolved_model,
                            usage=raw_chunk.usage,
                            provider_request_id=raw_chunk.provider_request_id,
                            done=True,
                        )
                    elif isinstance(raw_chunk, ChatStreamChunk):
                        chunk = raw_chunk
                    else:
                        raise ProviderRequestError(
                            "PROVIDER_INVALID_RESPONSE", "Provider 返回了无法识别的流式分片。", 502
                        )
                    if chunk.delta:
                        content += chunk.delta
                        if len(content) > MAX_OUTPUT_CHARS:
                            raise ProviderRequestError(
                                "OUTPUT_LIMIT_EXCEEDED",
                                "Provider 返回的普通聊天回答超过本地安全上限。",
                                502,
                            )
                        if not self._persist_snapshot(task_id, content):
                            return
                    if chunk.done:
                        final_chunk = chunk
            else:
                response = provider.generate(request, api_key)
                content = response.content
                final_chunk = ChatStreamChunk(
                    request_id=response.request_id,
                    delta="",
                    finish_reason=response.finish_reason,
                    provider=response.provider,
                    requested_model=response.requested_model,
                    resolved_model=response.resolved_model,
                    usage=response.usage,
                    provider_request_id=response.provider_request_id,
                    done=True,
                )
            if self._stop_event.is_set():
                return
        except ProviderRequestError as exc:
            self._fail_after_provider_error(task_id, exc, content)
            return
        except Exception:
            self._fail_after_provider_error(
                task_id,
                ProviderRequestError(
                    "AI_GENERATION_FAILED",
                    "普通聊天生成失败，请稍后重试。",
                    503,
                    True,
                ),
                content,
            )
            return
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()
            api_key = None
        if final_chunk is None:
            final_chunk = ChatStreamChunk(
                request_id=request.request_id,
                provider=_provider_name(provider),
                requested_model=request.model_profile,
                resolved_model=getattr(provider, "model", None),
                done=True,
            )
        self._complete_operation(task_id, content, final_chunk)

    def _persist_snapshot(self, task_id: str, content: str) -> bool:
        if self._stop_event.is_set():
            return False
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            operation = session.scalar(select(AiOperation).where(AiOperation.task_id == task_id))
            if task is None or operation is None or task.status != "RUNNING":
                return False
            checkpoint = self._checkpoint(task)
            if operation.status == "STOPPING" or checkpoint.get("stop_requested"):
                self._stop_operation(session, task, operation)
                session.commit()
                return False
            assistant = session.get(Message, operation.assistant_message_id)
            answer = session.scalar(
                select(AnswerVersion)
                .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
                .order_by(AnswerVersion.version_number.desc())
                .limit(1)
            )
            if assistant is None or answer is None:
                self._fail_operation(session, task, operation, "CHAT_STATE_INVALID", "聊天生成状态不完整。")
                session.commit()
                return False
            now = utc_now()
            sequence = int(checkpoint.get("stream_sequence", 0)) + 1
            assistant.content = content
            assistant.status = "STREAMING"
            assistant.updated_at = now
            answer.content = content
            answer.status = "STREAMING"
            checkpoint["content"] = content
            checkpoint["stream_sequence"] = sequence
            checkpoint["phase"] = "GENERATING"
            event = add_event(
                session,
                task,
                "SNAPSHOT",
                {
                    "operation_id": operation.operation_id,
                    "content": content,
                    "sequence": sequence,
                    "status": "RUNNING",
                    "terminal": False,
                },
            )
            checkpoint["event_sequence"] = event.sequence
            task.checkpoint_json = checkpoint
            task.checkpoint_version += 1
            task.updated_at = now
            operation.updated_at = now
            session.commit()
            return True

    def _complete_operation(self, task_id: str, content: str, chunk: ChatStreamChunk) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            operation = session.scalar(select(AiOperation).where(AiOperation.task_id == task_id))
            if task is None or operation is None or task.status != "RUNNING":
                return
            checkpoint = self._checkpoint(task)
            if operation.status == "STOPPING" or checkpoint.get("stop_requested"):
                self._stop_operation(session, task, operation)
                session.commit()
                return
            normalized = content.strip()
            if not normalized or len(normalized) > MAX_OUTPUT_CHARS:
                self._fail_operation(
                    session,
                    task,
                    operation,
                    "OUTPUT_LIMIT_EXCEEDED",
                    "Provider 返回的普通聊天回答超过本地安全上限。",
                )
                session.commit()
                return
            assistant = session.get(Message, operation.assistant_message_id)
            answer = session.scalar(
                select(AnswerVersion)
                .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
                .order_by(AnswerVersion.version_number.desc())
                .limit(1)
            )
            if assistant is None or answer is None:
                self._fail_operation(session, task, operation, "CHAT_STATE_INVALID", "聊天生成状态不完整。")
                session.commit()
                return
            now = utc_now()
            usage = chunk.usage or {}
            assistant.content = normalized
            assistant.status = "COMPLETED"
            assistant.updated_at = now
            assistant.completed_at = now
            answer.content = normalized
            answer.status = "COMPLETED"
            answer.usage_input_tokens = usage.get("prompt_tokens")
            answer.usage_output_tokens = usage.get("completion_tokens")
            answer.usage_total_tokens = usage.get("total_tokens")
            operation.status = "COMPLETED"
            operation.resolved_model = chunk.resolved_model
            operation.provider_request_id = chunk.provider_request_id
            operation.usage_input_tokens = usage.get("prompt_tokens")
            operation.usage_output_tokens = usage.get("completion_tokens")
            operation.usage_total_tokens = usage.get("total_tokens")
            operation.updated_at = now
            operation.completed_at = now
            operation.row_version += 1
            checkpoint["content"] = normalized
            checkpoint["final_status"] = "COMPLETED"
            checkpoint["stream_sequence"] = int(checkpoint.get("stream_sequence", 0)) + 1
            checkpoint["event_sequence"] = int(checkpoint.get("event_sequence", 0))
            task.checkpoint_json = checkpoint
            task.status = "COMPLETED"
            task.phase = "COMPLETED"
            task.progress = 100
            task.completed_at = now
            task.updated_at = now
            task.lease_owner = None
            task.lease_until = None
            task.row_version += 1
            finish_attempt(session, task.task_id, "SUCCEEDED")
            event = add_event(
                session,
                task,
                "COMPLETED",
                {
                    "operation_id": operation.operation_id,
                    "content": normalized,
                    "sequence": checkpoint["stream_sequence"],
                    "status": "COMPLETED",
                    "terminal": True,
                },
            )
            checkpoint["event_sequence"] = event.sequence
            task.checkpoint_json = checkpoint
            session.commit()

    def _fail_after_provider_error(
        self, task_id: str, error: ProviderRequestError, content: str = ""
    ) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            operation = session.scalar(select(AiOperation).where(AiOperation.task_id == task_id))
            if task is None or operation is None or task.status != "RUNNING":
                return
            if content:
                checkpoint = self._checkpoint(task)
                checkpoint["content"] = content
                task.checkpoint_json = checkpoint
            self._fail_operation(session, task, operation, error.code, error.detail)
            session.commit()

    def _fail_operation(
        self,
        session: Session,
        task: BackgroundTask,
        operation: AiOperation,
        code: str,
        detail: str,
    ) -> None:
        now = utc_now()
        assistant = session.get(Message, operation.assistant_message_id)
        answer = session.scalar(
            select(AnswerVersion)
            .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
            .order_by(AnswerVersion.version_number.desc())
            .limit(1)
        )
        if assistant is not None:
            assistant.status = "FAILED"
            assistant.updated_at = now
            assistant.completed_at = now
        if answer is not None:
            answer.status = "FAILED"
        operation.status = "FAILED"
        operation.error_code = code[:100]
        operation.error_detail = detail[:500]
        operation.updated_at = now
        operation.completed_at = now
        operation.row_version += 1
        checkpoint = self._checkpoint(task)
        checkpoint["content"] = assistant.content if assistant is not None else checkpoint.get("content", "")
        checkpoint["final_status"] = "FAILED"
        task.checkpoint_json = checkpoint
        task.status = "FAILED"
        task.phase = "FAILED"
        task.error_summary = detail[:500]
        task.completed_at = now
        task.updated_at = now
        task.lease_owner = None
        task.lease_until = None
        task.row_version += 1
        finish_attempt(session, task.task_id, "FAILED", task.error_summary)
        event = add_event(
            session,
            task,
            "FAILED",
            {
                "operation_id": operation.operation_id,
                "content": checkpoint.get("content", ""),
                "sequence": int(checkpoint.get("stream_sequence", 0)),
                "status": "FAILED",
                "error_code": code[:100],
                "terminal": True,
            },
        )
        checkpoint["event_sequence"] = event.sequence
        task.checkpoint_json = checkpoint

    def _stop_operation(self, session: Session, task: BackgroundTask, operation: AiOperation) -> None:
        if operation.status in TERMINAL_OPERATION_STATES:
            return
        now = utc_now()
        assistant = session.get(Message, operation.assistant_message_id)
        answer = session.scalar(
            select(AnswerVersion)
            .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
            .order_by(AnswerVersion.version_number.desc())
            .limit(1)
        )
        content = assistant.content if assistant is not None else ""
        if assistant is not None and assistant.status in {"PENDING", "STREAMING"}:
            assistant.status = "STOPPED"
            assistant.updated_at = now
            assistant.completed_at = now
        if answer is not None and answer.status in {"PENDING", "STREAMING"}:
            answer.status = "STOPPED"
            answer.content = content
        operation.status = "STOPPED"
        operation.error_code = "GENERATION_STOPPED"
        operation.error_detail = "用户已停止生成。"
        operation.updated_at = now
        operation.completed_at = now
        operation.row_version += 1
        checkpoint = self._checkpoint(task)
        checkpoint["content"] = content
        checkpoint["stop_requested"] = True
        checkpoint["final_status"] = "STOPPED"
        checkpoint["stream_sequence"] = int(checkpoint.get("stream_sequence", 0)) + 1
        task.checkpoint_json = checkpoint
        task.status = "CANCELLED"
        task.phase = "STOPPED"
        task.error_summary = operation.error_detail
        task.completed_at = now
        task.updated_at = now
        task.lease_owner = None
        task.lease_until = None
        task.row_version += 1
        finish_attempt(session, task.task_id, "CANCELLED", task.error_summary)
        event = add_event(
            session,
            task,
            "STOPPED",
            {
                "operation_id": operation.operation_id,
                "content": content,
                "sequence": checkpoint["stream_sequence"],
                "status": "STOPPED",
                "error_code": "GENERATION_STOPPED",
                "terminal": True,
            },
        )
        checkpoint["event_sequence"] = event.sequence
        task.checkpoint_json = checkpoint

    def _mark_interrupted(
        self, session: Session, operation: AiOperation, task: BackgroundTask
    ) -> None:
        if operation.status in TERMINAL_OPERATION_STATES:
            return
        checkpoint = self._checkpoint(task)
        if operation.status == "STOPPING" or checkpoint.get("stop_requested"):
            self._stop_operation(session, task, operation)
            return
        now = utc_now()
        operation.status = "INTERRUPTED"
        operation.error_code = "GENERATION_INTERRUPTED"
        operation.error_detail = "应用在生成过程中退出，未自动重发不确定的 Provider 请求。"
        operation.updated_at = now
        operation.completed_at = now
        operation.row_version += 1
        assistant = session.get(Message, operation.assistant_message_id)
        if assistant is not None and assistant.status in {"PENDING", "STREAMING"}:
            assistant.status = "INTERRUPTED"
            assistant.updated_at = now
            assistant.completed_at = now
        answer = session.scalar(
            select(AnswerVersion)
            .where(AnswerVersion.assistant_message_id == operation.assistant_message_id)
            .order_by(AnswerVersion.version_number.desc())
            .limit(1)
        )
        if answer is not None and answer.status in {"PENDING", "STREAMING"}:
            answer.status = "INTERRUPTED"
        checkpoint["content"] = assistant.content if assistant is not None else checkpoint.get("content", "")
        checkpoint["final_status"] = "INTERRUPTED"
        task.checkpoint_json = checkpoint
        task.status = "INTERRUPTED"
        task.phase = "INTERRUPTED"
        task.error_summary = operation.error_detail
        task.completed_at = now
        task.updated_at = now
        task.lease_owner = None
        task.lease_until = None
        task.row_version += 1
        finish_attempt(session, task.task_id, "INTERRUPTED", task.error_summary)
        event = add_event(
            session,
            task,
            "INTERRUPTED",
            {
                "operation_id": operation.operation_id,
                "content": checkpoint.get("content", ""),
                "sequence": int(checkpoint.get("stream_sequence", 0)),
                "status": "INTERRUPTED",
                "terminal": True,
            },
        )
        checkpoint["event_sequence"] = event.sequence
        task.checkpoint_json = checkpoint

    def _fail_worker_task(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            operation = session.scalar(select(AiOperation).where(AiOperation.task_id == task_id))
            if task is None or operation is None or task.status != "RUNNING":
                return
            self._fail_operation(
                session,
                task,
                operation,
                "AI_GENERATION_WORKER_FAILED",
                "普通聊天 Worker 执行失败，可以稍后重新发送。",
            )
            session.commit()


__all__ = [
    "ACTIVE_OPERATION_STATES",
    "CHAT_GENERATION_TASK",
    "CHAT_PROMPT_TEMPLATE_VERSION",
    "ChatCommandError",
    "ChatGenerationWorker",
    "GENERAL_CHAT_MODE",
    "GENERAL_SCOPE_TYPE",
    "MAX_CONTEXT_CHARS",
    "MAX_OUTPUT_TOKENS",
    "MAX_USER_MESSAGE_CHARS",
    "create_chat_message",
    "create_first_chat",
    "recover_interrupted_chat_operations",
    "request_chat_stop",
    "request_hash",
]
