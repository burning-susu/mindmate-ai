from __future__ import annotations

import secrets
import socket

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient


def run() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        assert port > 0

    token = secrets.token_urlsafe(24)
    app = FastAPI()

    @app.get("/private")
    def private(x_mindmate_session: str | None = Header(default=None)) -> dict[str, str]:
        if x_mindmate_session != token:
            raise HTTPException(status_code=401, detail="local session required")
        return {"status": "ok"}

    client = TestClient(app)
    assert client.get("/private").status_code == 401
    assert client.get("/private", headers={"X-MindMate-Session": token}).status_code == 200
    print(f"local-runtime PASS: loopback_port={port} session_guard=ok")


if __name__ == "__main__":
    run()
