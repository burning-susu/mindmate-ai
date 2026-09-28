from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/testing", tags=["testing"])


class ProviderFixtureFailureRequest(BaseModel):
    provider: Literal["DEEPSEEK", "OPENAI"]


@router.get("/provider-fixture/calls")
def read_provider_fixture_calls(request: Request) -> dict[str, Any]:
    fixture = getattr(request.app.state, "provider_fixture", None)
    if fixture is None:
        return {"calls": []}
    return {"calls": fixture.calls()}


@router.post("/provider-fixture/fail-next-question")
def fail_next_provider_fixture_question(
    payload: ProviderFixtureFailureRequest, request: Request
) -> dict[str, Any]:
    fixture = getattr(request.app.state, "provider_fixture", None)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Provider fixture is unavailable.")
    fixture.fail_next_question(payload.provider)
    return {"provider": payload.provider, "scheduled": True}
