from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()


async def events():
    for index, text in enumerate(("Mind", "Mate", " ready"), start=1):
        yield f'event: TEXT_DELTA\ndata: {{"sequence": {index}, "text": "{text}"}}\n\n'
        await asyncio.sleep(0)
    yield 'event: COMPLETED\ndata: {"sequence": 4}\n\n'


@app.get("/mock/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(events(), media_type="text/event-stream")


async def run() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://mock"
    ) as client:
        response = await client.get("/mock/stream")
    assert response.status_code == 200
    assert "TEXT_DELTA" in response.text
    assert "COMPLETED" in response.text
    assert all(fragment in response.text for fragment in ('"Mind"', '"Mate"', '" ready"'))
    print("mock-sse PASS: TEXT_DELTA and COMPLETED received")


if __name__ == "__main__":
    asyncio.run(run())
