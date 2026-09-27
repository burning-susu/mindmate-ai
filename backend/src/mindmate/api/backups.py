"""Backup create / list / download API, plus restart-gated full restore."""

from __future__ import annotations

# ruff: noqa: B008
from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mindmate.api.files import get_session, get_settings
from mindmate.application.backups import (
    UNENCRYPTED_WARNING,
    backup_public_view,
    get_backup,
    list_backups,
    resolve_archive_path,
    start_or_get_backup,
    verify_managed_backup,
)
from mindmate.application.local_backup import BackupBuildError
from mindmate.application.local_restore import (
    RESTORE_FLOW_AVAILABLE,
    acknowledge_provider_reconfirm,
    cancel_restore,
    confirm_restore,
    list_recovery_points,
    precheck_upload,
    public_restore_status,
    save_uploaded_archive,
    session_fingerprint,
)
from mindmate.config import Settings
from mindmate.security.session import SESSION_COOKIE

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


class BackupApiError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400, retryable: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status_code
        self.retryable = retryable


class BackupScopeResponse(BaseModel):
    database_snapshot: bool
    content_objects: bool
    parsed_artifacts: bool
    non_secret_config: bool
    vectors: bool
    fts: bool
    models: bool
    logs: bool
    secrets: bool


class BackupResponse(BaseModel):
    backup_id: str
    status: str
    backup_format_version: str
    schema_version: str
    file_count: int
    total_size: int
    created_at: datetime
    completed_at: datetime | None = None
    error_summary: str | None = None
    includes_vectors: bool = False
    includes_parsed: bool = False
    includes_secrets: bool = False
    encrypted: bool = False
    contains_user_files_and_history: bool = True
    unencrypted_warning: bool = True
    warning_message: str = UNENCRYPTED_WARNING
    download_available: bool = False
    restore_available: bool = False
    scope: BackupScopeResponse


class BackupListResponse(BaseModel):
    items: list[BackupResponse]
    restore_available: bool = False
    warning_message: str = UNENCRYPTED_WARNING


class BackupVerifyResponse(BaseModel):
    backup_id: str
    verified: bool
    file_count: int | None = None
    total_size: int | None = None
    schema_version: str | None = None
    includes_secrets: bool = False
    includes_vectors: bool = False


def _require_local_session(request: Request) -> None:
    local = getattr(request.app.state, "session", None)
    if local is None or not local.matches(request.cookies.get(SESSION_COOKIE)):
        raise BackupApiError(
            "LOCAL_SESSION_REQUIRED",
            "请从当前 MindMate 应用页面重新建立本地会话。",
            401,
        )


def _map_build_error(exc: BackupBuildError) -> BackupApiError:
    status = {
        "BACKUP_NOT_FOUND": 404,
        "BACKUP_NOT_READY": 409,
        "BACKUP_CONTENT_MISSING": 409,
        "BACKUP_DATABASE_MISSING": 409,
        "BACKUP_ARCHIVE_MISSING": 404,
        "RESTORE_IN_PROGRESS": 409,
        "RESTORE_ALREADY_CONFIRMED": 409,
        "RESTORE_PRECHECK_EXPIRED": 409,
        "RESTORE_PRECHECK_INVALID": 409,
        "RESTORE_ARCHIVE_CHANGED": 409,
        "RESTORE_DATA_CHANGED": 409,
        "RESTORE_SESSION_MISMATCH": 409,
        "RESTORE_DATABASE_LOCKED": 409,
        "RESTORE_DISK_SPACE": 409,
        "RESTORE_CONFIRMATION_REQUIRED": 400,
        "BACKUP_UPLOAD_TOO_LARGE": 413,
    }.get(exc.code, 400)
    # Never leak private paths or file bodies in API errors.
    detail = exc.detail
    if len(detail) > 200:
        detail = detail[:200]
    return BackupApiError(exc.code, detail, status)


@router.post("", response_model=BackupResponse)
def create_backup_endpoint(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    idempotency_key = request.headers.get("idempotency-key", "").strip()
    if not idempotency_key:
        raise BackupApiError("IDEMPOTENCY_KEY_REQUIRED", "写请求必须携带 Idempotency-Key。", 400)
    try:
        row = start_or_get_backup(session, settings, idempotency_key=idempotency_key)
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc
    return backup_public_view(row)


@router.get("", response_model=BackupListResponse)
def list_backups_endpoint(
    request: Request,
    session: Session = Depends(get_session),
    limit: int = 50,
) -> dict[str, Any]:
    _require_local_session(request)
    rows = list_backups(session, limit=limit)
    return {
        "items": [backup_public_view(row) for row in rows],
        "restore_available": RESTORE_FLOW_AVAILABLE,
        "warning_message": UNENCRYPTED_WARNING,
    }


class RestoreUploadResponse(BaseModel):
    upload_id: str
    archive_sha256: str
    byte_size: int


class RestorePrecheckRequest(BaseModel):
    upload_id: str


class RestoreExecuteRequest(BaseModel):
    precheck_id: str
    confirm_full_replace: bool = False
    confirm_phrase: str


class RestoreReconfirmRequest(BaseModel):
    confirm_reconfigure: bool = False


def _session_fingerprint(request: Request) -> str:
    return session_fingerprint(request.cookies.get(SESSION_COOKIE))


@router.post("/restore/uploads", response_model=RestoreUploadResponse)
def upload_restore_archive(
    request: Request,
    archive: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    filename = (archive.filename or "").replace("\\", "/").split("/")[-1]
    if not filename.endswith(".mindmate-backup") and not filename.endswith(".zip"):
        raise BackupApiError("BACKUP_FORMAT_UNSUPPORTED", "请选择 .mindmate-backup 备份包。", 400)
    idempotency_key = request.headers.get("idempotency-key", "").strip()
    if not idempotency_key:
        raise BackupApiError("IDEMPOTENCY_KEY_REQUIRED", "写请求必须携带 Idempotency-Key。", 400)
    try:
        return save_uploaded_archive(settings, archive.file, idempotency_key=idempotency_key)
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc
    finally:
        archive.file.close()


@router.post("/restore/prechecks")
def precheck_restore_archive(
    payload: RestorePrecheckRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    try:
        return precheck_upload(
            settings,
            payload.upload_id,
            session_fingerprint_value=_session_fingerprint(request),
        )
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc


@router.post("/restore/executions")
def execute_restore(
    payload: RestoreExecuteRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    idempotency_key = request.headers.get("idempotency-key", "").strip()
    if not idempotency_key:
        raise BackupApiError("IDEMPOTENCY_KEY_REQUIRED", "写请求必须携带 Idempotency-Key。", 400)
    try:
        return confirm_restore(
            settings,
            request.app,
            precheck_id=payload.precheck_id,
            confirm_full_replace=payload.confirm_full_replace,
            confirm_phrase=payload.confirm_phrase,
            idempotency_key=idempotency_key,
            session_fingerprint_value=_session_fingerprint(request),
        )
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc


@router.post("/restore/cancel")
def cancel_restore_endpoint(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    try:
        return cancel_restore(settings, request.app)
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc


@router.get("/restore/status")
def restore_status_endpoint(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    return public_restore_status(settings)


@router.get("/restore/recovery-points")
def recovery_points_endpoint(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    return list_recovery_points(settings)


@router.post("/restore/provider-reconfirm")
def acknowledge_restore_provider(
    payload: RestoreReconfirmRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    if not payload.confirm_reconfigure:
        raise BackupApiError(
            "RESTORE_PROVIDER_RECONFIRM_REQUIRED",
            "请确认恢复后需要重新配置或核对 Provider，当前不会自动外发。",
            400,
        )
    acknowledge_provider_reconfirm(session, settings)
    status = public_restore_status(settings)
    status["provider_reconfirm_required"] = False
    status["generation_mode"] = "mock"
    return status


@router.get("/{backup_id}", response_model=BackupResponse)
def get_backup_endpoint(
    backup_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_local_session(request)
    row = get_backup(session, backup_id)
    if row is None:
        raise BackupApiError("BACKUP_NOT_FOUND", "备份记录不存在。", 404)
    return backup_public_view(row)


@router.post("/{backup_id}/verify", response_model=BackupVerifyResponse)
def verify_backup_endpoint(
    backup_id: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_local_session(request)
    try:
        return verify_managed_backup(session, settings, backup_id)
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc


@router.get("/{backup_id}/download")
def download_backup_endpoint(
    backup_id: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    _require_local_session(request)
    row = get_backup(session, backup_id)
    if row is None:
        raise BackupApiError("BACKUP_NOT_FOUND", "备份记录不存在。", 404)
    if row.status != "COMPLETED":
        raise BackupApiError("BACKUP_NOT_READY", "仅已完成且通过校验的备份可以下载。", 409)
    try:
        path = resolve_archive_path(settings, row)
        # Re-verify before streaming so incomplete/tampered archives are never returned.
        from mindmate.application.local_backup import verify_backup_archive

        verify_backup_archive(path, expect_schema=row.schema_version)
    except BackupBuildError as exc:
        raise _map_build_error(exc) from exc
    if not path.is_file():
        raise BackupApiError("BACKUP_ARCHIVE_MISSING", "备份包文件不存在。", 404)

    filename = path.name
    response = FileResponse(
        path,
        media_type="application/zip",
        filename=filename,
        content_disposition_type="attachment",
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = (
        f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/{backup_id}/restore")
def restore_backup_disabled(backup_id: str) -> None:
    raise BackupApiError(
        "BACKUP_RESTORE_DISABLED",
        "恢复能力尚未独立验收，当前版本已禁用。请继续使用手动创建的备份包，等待后续版本开通恢复。",
        501,
    )


__all__ = ["BackupApiError", "router"]
