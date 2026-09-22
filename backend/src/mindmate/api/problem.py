from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    instance: str
    request_id: str
    retryable: bool = False
    current_row_version: int | None = None
    field_errors: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
