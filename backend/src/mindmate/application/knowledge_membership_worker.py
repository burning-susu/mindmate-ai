from __future__ import annotations

import threading
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from uuid6 import uuid7

from mindmate.application.tasks import (
    add_event,
    claim_next_task,
    finish_attempt,
    interrupt_owned_tasks,
    renew_task_lease,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    ContentObject,
    FileRecord,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)

KNOWLEDGE_MEMBERSHIP_TASK = "KNOWLEDGE_MEMBERSHIP_ADD"


def _items(task: BackgroundTask) -> list[dict[str, object]]:
    checkpoint = task.checkpoint_json if isinstance(task.checkpoint_json, dict) else {}
    items = checkpoint.get("items", [])
    return [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []


class KnowledgeMembershipWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        worker_id: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self.worker_id = worker_id or f"knowledge-membership-{uuid7()}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run,
                name="mindmate-knowledge-membership-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout))

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                task_id = self._claim_one()
                if task_id is None:
                    self._stop_event.wait(max(0.02, self._settings.knowledge_worker_poll_seconds))
                    continue
                try:
                    self._process(task_id)
                except Exception:
                    self._fail(task_id)
        finally:
            with self._session_factory() as session:
                interrupt_owned_tasks(session, self.worker_id)
                session.commit()

    def _claim_one(self) -> str | None:
        with self._session_factory() as session:
            task = claim_next_task(
                session,
                self.worker_id,
                self._settings.knowledge_worker_lease_seconds,
                {KNOWLEDGE_MEMBERSHIP_TASK},
            )
            if task is None:
                return None
            task.phase = "VALIDATING_MEMBERS"
            session.commit()
            return task.task_id

    def _process(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING" or task.lease_owner != self.worker_id:
                return
            checkpoint = deepcopy(task.checkpoint_json or {})
            knowledge_base_id = checkpoint.get("knowledge_base_id")
            if not isinstance(knowledge_base_id, str):
                self._finish(session, task, "FAILED", "知识库成员任务缺少目标知识库。")
                return
            knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
            if knowledge_base is None or knowledge_base.deleted_at is not None:
                self._finish(session, task, "FAILED", "目标知识库已不存在或位于回收站。")
                return

            results: list[dict[str, object]] = []
            requested = _items(task)
            for index, item in enumerate(requested):
                if task.status == "CANCELLED" or self._stop_event.is_set():
                    session.rollback()
                    return
                results.append(self._process_item(session, knowledge_base, item))
                task.checkpoint_json = {
                    **checkpoint,
                    "items": requested,
                    "results": deepcopy(results),
                }
                task.phase = "ADDING_MEMBERS"
                task.progress = round((index + 1) * 100 / max(1, len(requested)))
                task.checkpoint_version += 1
                task.updated_at = datetime.now(UTC)
                task.row_version += 1
                session.commit()
                session.refresh(task)
                session.refresh(knowledge_base)
                if not renew_task_lease(
                    session,
                    task.task_id,
                    self.worker_id,
                    self._settings.knowledge_worker_lease_seconds,
                ):
                    session.rollback()
                    return
                session.commit()

            session.refresh(task)
            if task.status == "CANCELLED":
                return
            active_count = session.scalar(
                select(KnowledgeBaseFile)
                .where(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.membership_status == "ACTIVE",
                )
                .limit(1)
            )
            knowledge_base.status = "PREPARING" if active_count is not None else "EMPTY"
            knowledge_base.updated_at = datetime.now(UTC)
            knowledge_base.row_version += 1
            failed = sum(1 for result in results if result["status"] == "FAILED")
            task.checkpoint_json = {
                **checkpoint,
                "items": requested,
                "results": results,
                "summary": {"added": len(results) - failed, "failed": failed},
            }
            self._finish(session, task, "COMPLETED", None)

    def _process_item(
        self, session: Session, knowledge_base: KnowledgeBase, item: dict[str, object]
    ) -> dict[str, object]:
        file_id = item.get("file_id")
        result: dict[str, object] = {"file_id": file_id or "", "status": "FAILED"}
        if not isinstance(file_id, str):
            return {**result, "reason": "FILE_ID_INVALID", "message": "文件 ID 无效。"}
        if knowledge_base.deleted_at is not None:
            return {
                **result,
                "reason": "KNOWLEDGE_BASE_IN_TRASH",
                "message": "知识库已移入回收站。",
            }
        record = session.get(FileRecord, file_id)
        if record is None:
            return {**result, "reason": "FILE_NOT_FOUND", "message": "文件不存在。"}
        result["display_name"] = record.display_name
        if record.deleted_at is not None:
            return {**result, "reason": "FILE_IN_TRASH", "message": "文件位于回收站。"}
        content = session.get(ContentObject, record.content_object_id)
        if content is None or content.storage_state != "READY":
            return {**result, "reason": "FILE_UNAVAILABLE", "message": "文件内容不可用。"}

        membership = session.scalar(
            select(KnowledgeBaseFile).where(
                KnowledgeBaseFile.knowledge_base_id == knowledge_base.knowledge_base_id,
                KnowledgeBaseFile.file_id == file_id,
            )
        )
        action = "ADDED"
        now = datetime.now(UTC)
        if membership is None:
            membership = KnowledgeBaseFile(
                knowledge_base_file_id=new_id(),
                knowledge_base_id=knowledge_base.knowledge_base_id,
                file_id=file_id,
                membership_status="ACTIVE",
                index_state="PENDING",
                added_at=now,
            )
            session.add(membership)
        elif membership.membership_status == "ACTIVE":
            action = "ALREADY_MEMBER"
        else:
            requested_at = item.get("requested_at")
            if membership.removed_at is not None and isinstance(requested_at, str):
                request_time = datetime.fromisoformat(requested_at)
                removed_time = membership.removed_at
                if removed_time.tzinfo is None:
                    removed_time = removed_time.replace(tzinfo=UTC)
                if removed_time >= request_time:
                    return {
                        **result,
                        "reason": "MEMBERSHIP_REMOVED",
                        "message": "成员已在本次任务之后移出，未重新加入。",
                    }
            action = "RESTORED"
            membership.membership_status = "ACTIVE"
            membership.index_state = "PENDING"
            membership.added_at = now
            membership.removed_at = None

        parse_state = record.status
        messages = {
            "PARSED": "成员已加入，索引仍待建立。",
            "PARSE_FAILED": "成员已加入，但文件解析失败，当前不可检索。",
            "QUEUED": "成员已加入，文件仍在等待解析。",
            "PARSING": "成员已加入，文件正在解析。",
        }
        return {
            **result,
            "status": "ADDED",
            "action": action,
            "parse_state": parse_state,
            "index_state": "PENDING",
            "message": messages.get(parse_state, "成员已加入，文件当前不可检索。"),
        }

    def _finish(
        self, session: Session, task: BackgroundTask, status: str, error: str | None
    ) -> None:
        task.status = status
        task.phase = "COMPLETED" if status == "COMPLETED" else "FAILED"
        task.progress = 100
        task.error_summary = error
        completed_at = datetime.now(UTC)
        task.completed_at = completed_at
        task.updated_at = completed_at
        task.lease_owner = None
        task.lease_until = None
        task.row_version += 1
        finish_attempt(session, task.task_id, "SUCCEEDED" if status == "COMPLETED" else "FAILED", error)
        add_event(session, task, status, (task.checkpoint_json or {}).get("summary"))
        session.commit()

    def _fail(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.get(BackgroundTask, task_id)
            if task is None or task.status != "RUNNING":
                return
            self._finish(session, task, "FAILED", "知识库成员任务执行失败，可以重新提交。")
