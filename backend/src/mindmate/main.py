from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mindmate import __version__


class ServiceStatus(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


def create_app() -> FastAPI:
    app = FastAPI(
        title="MindMate AI Local API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def local_host_guard(request: Request, call_next: Any) -> JSONResponse:
        host = request.headers.get("host", "").split(":", 1)[0]
        if host not in {"127.0.0.1", "localhost", "[::1]", "::1"}:
            return JSONResponse(status_code=400, content={"detail": "local host required"})
        return await call_next(request)

    @app.get("/api/v1/health", response_model=ServiceStatus, tags=["system"])
    async def health() -> ServiceStatus:
        return ServiceStatus(
            status="ok",
            service="mindmate-backend",
            version=__version__,
            timestamp=datetime.now(UTC),
        )

    @app.get("/api/v1/ready", response_model=ServiceStatus, tags=["system"])
    async def ready() -> ServiceStatus:
        return ServiceStatus(
            status="ready",
            service="mindmate-backend",
            version=__version__,
            timestamp=datetime.now(UTC),
        )

    @app.get("/api/v1/version", response_model=ServiceStatus, tags=["system"])
    async def version() -> ServiceStatus:
        return ServiceStatus(
            status="ok",
            service="mindmate-backend",
            version=__version__,
            timestamp=datetime.now(UTC),
        )

    return app


app = create_app()
