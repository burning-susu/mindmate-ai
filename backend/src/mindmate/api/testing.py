from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/testing", tags=["testing"])


@router.get("/provider-fixture/calls")
def read_provider_fixture_calls(request: Request) -> dict[str, Any]:
    fixture = getattr(request.app.state, "provider_fixture", None)
    if fixture is None:
        return {"calls": []}
    return {"calls": fixture.calls()}
