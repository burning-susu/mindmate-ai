from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from uuid6 import uuid7

from mindmate import __version__
from mindmate.api.files import FileApiError
from mindmate.api.files import router as files_router
from mindmate.api.knowledge_bases import router as knowledge_bases_router
from mindmate.api.problem import ProblemDetail
from mindmate.application.index_preprocessing_worker import IndexPreprocessingWorker
from mindmate.application.knowledge_membership_worker import KnowledgeMembershipWorker
from mindmate.application.parse_worker_service import ParsingWorker
from mindmate.config import Settings, get_settings
from mindmate.infrastructure.db import create_session_factory, create_sqlite_engine, quick_check
from mindmate.security.instance import SingleInstanceLock
from mindmate.security.session import SESSION_COOKIE, LocalSession


class ServiceStatus(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime
    request_id: str


def problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str,
    retryable: bool = False,
    current_row_version: int | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid7()))
    payload = ProblemDetail(
        type=f"https://mindmate.local/problems/{code.lower()}",
        title=title,
        status=status,
        code=code,
        detail=detail,
        instance=request.url.path,
        request_id=request_id,
        retryable=retryable,
        current_row_version=current_row_version,
    )
    return JSONResponse(
        status_code=status,
        content=payload.model_dump(mode="json"),
        media_type="application/problem+json",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.ensure_data_dirs()
    lock = SingleInstanceLock(settings.runtime_dir / "instance.lock")
    lock.acquire()
    try:
        alembic_config = Config(str(settings.alembic_ini))
        alembic_config.attributes["settings"] = settings
        command.upgrade(alembic_config, "head")
        app.state.instance_lock = lock
        app.state.engine = create_sqlite_engine(settings.database_path)
        app.state.database_status = quick_check(app.state.engine)
        app.state.session_factory = create_session_factory(app.state.engine)
        app.state.session = LocalSession()
        app.state.parse_worker = ParsingWorker(app.state.session_factory, settings)
        app.state.parse_worker.start()
        app.state.knowledge_membership_worker = KnowledgeMembershipWorker(
            app.state.session_factory, settings
        )
        app.state.knowledge_membership_worker.start()
        app.state.index_preprocessing_worker = IndexPreprocessingWorker(
            app.state.session_factory, settings
        )
        app.state.index_preprocessing_worker.start()
        yield
    finally:
        index_worker = getattr(app.state, "index_preprocessing_worker", None)
        if index_worker is not None:
            index_worker.stop()
        knowledge_worker = getattr(app.state, "knowledge_membership_worker", None)
        if knowledge_worker is not None:
            knowledge_worker.stop()
        worker = getattr(app.state, "parse_worker", None)
        if worker is not None:
            worker.stop()
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            engine.dispose()
        lock.release()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(
        title="MindMate AI Local API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "Idempotency-Key", "X-MindMate-Session"],
    )

    @app.middleware("http")
    async def local_security(request: Request, call_next: Any) -> Response:
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", supplied_request_id)
            else str(uuid7())
        )
        request.state.request_id = request_id
        host = (request.url.hostname or "").lower()
        if host not in {"127.0.0.1", "localhost", "[::1]", "::1"}:
            return problem(
                request, 400, "LOCAL_HOST_REQUIRED", "需要本地 Host", "请求必须来自本机回环地址。"
            )
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site", "none").lower()
        if request.url.path == "/api/v1/system/session" and fetch_site not in {
            "none",
            "same-origin",
            "same-site",
        }:
            return problem(
                request,
                403,
                "SESSION_ORIGIN_NOT_ALLOWED",
                "来源不允许",
                "本地会话只能由本地应用来源建立。",
            )
        if origin is not None and origin not in app_settings.allowed_origins:
            return problem(
                request, 403, "ORIGIN_NOT_ALLOWED", "来源不允许", "请求来源不在本地来源白名单中。"
            )
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin not in app_settings.allowed_origins
        ):
            return problem(
                request,
                403,
                "ORIGIN_NOT_ALLOWED",
                "来源不允许",
                "请求来源不在本地开发来源白名单中。",
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in {
            "/api/v1/system/session"
        }:
            if not getattr(request.app.state, "session", LocalSession()).matches(
                request.cookies.get(SESSION_COOKIE)
            ):
                return problem(
                    request,
                    401,
                    "LOCAL_SESSION_REQUIRED",
                    "本地会话无效",
                    "请从当前 MindMate 应用页面重新建立本地会话。",
                )
        idempotency_key = request.headers.get("idempotency-key")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/api/v1/system/session"
            and idempotency_key is None
        ):
            return problem(
                request,
                400,
                "IDEMPOTENCY_KEY_REQUIRED",
                "缺少幂等键",
                "写请求必须携带 Idempotency-Key。",
            )
        if idempotency_key is not None and not re.fullmatch(
            r"[A-Za-z0-9._:-]{8,128}", idempotency_key
        ):
            return problem(
                request,
                400,
                "IDEMPOTENCY_KEY_INVALID",
                "幂等键无效",
                "幂等键格式或长度不符合要求。",
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if idempotency_key is not None:
            response.headers["Idempotency-Key"] = idempotency_key
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {
            401: ("LOCAL_SESSION_REQUIRED", "本地会话无效"),
            403: ("REQUEST_FORBIDDEN", "请求被拒绝"),
            404: ("RESOURCE_NOT_FOUND", "资源不存在"),
        }
        code, title = messages.get(exc.status_code, ("REQUEST_FAILED", "请求失败"))
        return problem(request, exc.status_code, code, title, "请求无法完成。")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError) -> JSONResponse:
        return problem(request, 422, "REQUEST_INVALID", "请求无效", "请求字段未通过校验。")

    @app.exception_handler(RuntimeError)
    async def runtime_error(request: Request, _exc: RuntimeError) -> JSONResponse:
        return problem(
            request,
            503,
            "LOCAL_RUNTIME_UNAVAILABLE",
            "本地服务不可用",
            "本地运行组件不可用，请重启应用或检查本地数据目录。",
            retryable=True,
        )

    @app.exception_handler(FileApiError)
    async def file_api_error(request: Request, exc: FileApiError) -> JSONResponse:
        return problem(
            request,
            exc.status,
            exc.code,
            "文件操作失败",
            exc.detail,
            current_row_version=exc.current_row_version,
        )

    @app.post("/api/v1/system/session", tags=["system"])
    async def session(request: Request, response: Response) -> dict[str, Any]:
        local_session = getattr(request.app.state, "session", None)
        if local_session is None:
            return {"status": "starting", "expires_on_restart": True}
        response.set_cookie(
            SESSION_COOKIE,
            local_session.token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return {"status": "ready", "expires_on_restart": True}

    @app.get("/api/v1/health", response_model=ServiceStatus, tags=["system"])
    @app.get("/api/v1/system/health", response_model=ServiceStatus, tags=["system"])
    async def health(request: Request) -> ServiceStatus:
        return ServiceStatus(
            status="ok",
            service="mindmate-backend",
            version=__version__,
            timestamp=datetime.now(UTC),
            request_id=request.state.request_id,
        )

    @app.get("/api/v1/ready", response_model=ServiceStatus, tags=["system"])
    @app.get("/api/v1/system/readiness", response_model=ServiceStatus, tags=["system"])
    async def ready(request: Request) -> ServiceStatus:
        status = (
            "ready" if getattr(request.app.state, "database_status", "ok") == "ok" else "degraded"
        )
        return ServiceStatus(
            status=status,
            service="mindmate-backend",
            version=__version__,
            timestamp=datetime.now(UTC),
            request_id=request.state.request_id,
        )

    @app.get("/api/v1/version", response_model=ServiceStatus, tags=["system"])
    async def version(request: Request) -> ServiceStatus:
        return ServiceStatus(
            status="ok",
            service="mindmate-backend",
            version=__version__,
            timestamp=datetime.now(UTC),
            request_id=request.state.request_id,
        )

    @app.get("/api/v1/system/capabilities", tags=["system"])
    async def capabilities() -> dict[str, Any]:
        return {
            "provider_runtime": "mock",
            "real_provider_enabled": False,
            "embedding": "stage-1-validated",
            "vector_store": "sqlite-vec-stage-1-validated",
        }

    @app.get("/api/v1/system/storage", tags=["system"])
    async def storage() -> dict[str, Any]:
        settings: Settings = app.state.settings
        return {
            "data_dir_configured": bool(settings.data_dir),
            "database": "sqlite",
            "writable": True,
        }

    @app.get("/api/v1/system/openapi.json", include_in_schema=False)
    async def openapi_json() -> dict[str, Any]:
        return app.openapi()

    app.include_router(knowledge_bases_router)
    app.include_router(files_router)

    return app


app = create_app()
