from __future__ import annotations

# FastAPI evaluates dependency declarations when routes are registered.
# ruff: noqa: B008
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.ai.embeddings.model_manager import ModelManager, ModelState
from mindmate.api.files import FileApiError, get_session
from mindmate.application.embedding_model_install import (
    ACTIVE_INSTALL_STATES,
    EMBEDDING_MODEL_INSTALL_TASK,
    active_install_task,
    enqueue_embedding_model_install,
)
from mindmate.infrastructure.models import BackgroundTask

router = APIRouter(prefix="/api/v1")


class EmbeddingModelStatusResponse(BaseModel):
    state: str
    phase: str | None = None
    base_model_id: str
    base_model_url: str
    artifact_repository_id: str
    artifact_url: str
    license: str
    base_revision: str
    artifact_revision: str
    artifact_fingerprint: str
    total_size_bytes: int
    downloaded_bytes: int
    current_file: str | None = None
    file_downloaded_bytes: int | None = None
    file_size_bytes: int | None = None
    task_id: str | None = None
    diagnostic_id: str | None = None
    error_code: str | None = None
    can_install: bool
    can_cancel: bool


def _manager(request: Request) -> ModelManager:
    manager = getattr(request.app.state, "embedding_model_manager", None)
    if manager is None:
        raise FileApiError("LOCAL_RUNTIME_UNAVAILABLE", "本地模型管理器不可用。", 503)
    return manager


def _latest_install_task(session: Session) -> BackgroundTask | None:
    return session.scalar(
        select(BackgroundTask)
        .where(BackgroundTask.task_type == EMBEDDING_MODEL_INSTALL_TASK)
        .order_by(BackgroundTask.created_at.desc())
        .limit(1)
    )


def _task_checkpoint(task: BackgroundTask | None) -> dict[str, Any]:
    if task is None or not isinstance(task.checkpoint_json, dict):
        return {}
    return task.checkpoint_json


def _status_payload(
    session: Session,
    manager: ModelManager,
    preferred_task: BackgroundTask | None = None,
) -> dict[str, Any]:
    active = active_install_task(session)
    task = active or preferred_task or _latest_install_task(session)
    checkpoint = _task_checkpoint(task)
    model_status = manager.status()
    manifest = manager.manifest
    total_size = manifest.total_size_bytes
    downloaded_value = checkpoint.get("downloaded_bytes", 0)
    downloaded = (
        min(total_size, max(0, downloaded_value))
        if isinstance(downloaded_value, int)
        else 0
    )
    if model_status.state == ModelState.READY:
        downloaded = total_size
    current_file = checkpoint.get("current_file")
    file_downloaded = checkpoint.get("file_downloaded_bytes")
    file_size = checkpoint.get("file_size_bytes")
    error_code = checkpoint.get("error_code")
    if not isinstance(error_code, str):
        error_code = model_status.error_code

    if model_status.state == ModelState.READY:
        state = "READY"
        phase = "READY"
        error_code = None
    elif active is not None:
        if active.status == "QUEUED":
            state, phase = "QUEUED", "QUEUED"
        elif active.status == "INTERRUPTED":
            state, phase = "RECOVERING", "RECOVERING"
        else:
            stored_phase = checkpoint.get("phase")
            phase = stored_phase if isinstance(stored_phase, str) else active.phase
            state = phase if phase in {"DOWNLOADING", "VERIFYING"} else "PREPARING"
    elif model_status.state == ModelState.CORRUPT:
        state, phase = "CORRUPT", "FAILED"
    elif task is not None and task.status == "CANCELLED":
        state, phase = "CANCELLED", "CANCELLED"
    elif task is not None and task.status == "FAILED":
        state = "MISSING_OFFLINE" if error_code == "MODEL_DOWNLOAD_OFFLINE" else "FAILED"
        phase = "FAILED"
    elif model_status.state == ModelState.MISSING_OFFLINE or (
        error_code == "MODEL_DOWNLOAD_OFFLINE"
    ):
        state, phase = "MISSING_OFFLINE", "FAILED"
    elif model_status.state == ModelState.INSTALLING:
        state, phase = "VERIFYING", "VERIFYING"
    else:
        state, phase = "MISSING", None

    is_active = active is not None and active.status in ACTIVE_INSTALL_STATES
    return {
        "state": state,
        "phase": phase,
        "base_model_id": manifest.base_model_id,
        "base_model_url": (
            f"https://huggingface.co/{manifest.base_model_id}/tree/{manifest.base_revision}"
        ),
        "artifact_repository_id": manifest.artifact_repository_id,
        "artifact_url": (
            "https://huggingface.co/"
            f"{manifest.artifact_repository_id}/tree/{manifest.artifact_revision}"
        ),
        "license": manifest.license,
        "base_revision": manifest.base_revision,
        "artifact_revision": manifest.artifact_revision,
        "artifact_fingerprint": manifest.fingerprint,
        "total_size_bytes": total_size,
        "downloaded_bytes": downloaded,
        "current_file": current_file if isinstance(current_file, str) else None,
        "file_downloaded_bytes": file_downloaded if isinstance(file_downloaded, int) else None,
        "file_size_bytes": file_size if isinstance(file_size, int) else None,
        "task_id": task.task_id if task is not None else None,
        "diagnostic_id": (
            task.task_id
            if task is not None and task.status in {"FAILED", "CANCELLED"}
            else None
        ),
        "error_code": error_code if state in {"FAILED", "MISSING_OFFLINE", "CORRUPT"} else None,
        "can_install": not is_active
        and state in {"MISSING", "MISSING_OFFLINE", "CANCELLED", "FAILED", "CORRUPT"},
        "can_cancel": is_active and state != "READY",
    }


@router.get(
    "/embedding-model",
    response_model=EmbeddingModelStatusResponse,
    tags=["embedding-models"],
)
def get_embedding_model_status(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    return _status_payload(session, _manager(request))


@router.post(
    "/embedding-model/install",
    response_model=EmbeddingModelStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["embedding-models"],
)
def install_embedding_model(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    manager = _manager(request)
    key = request.headers.get("idempotency-key")
    if key is None:
        raise FileApiError("IDEMPOTENCY_KEY_REQUIRED", "安装请求缺少幂等键。", 400)
    existing = session.scalar(
        select(BackgroundTask).where(
            BackgroundTask.idempotency_key
            == f"embedding-model-install:{manager.manifest.fingerprint}:{key}"
        )
    )
    model_status = manager.status()
    if model_status.state == ModelState.READY:
        return _status_payload(session, manager, existing)
    task = existing or enqueue_embedding_model_install(session, key, manager)
    worker = getattr(request.app.state, "embedding_model_install_worker", None)
    if worker is not None:
        worker.wake()
    return _status_payload(session, manager, task)


__all__ = ["router"]
