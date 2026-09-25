from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from mindmate.ai.embeddings.manifest import ModelFile, ModelManifest
from mindmate.ai.embeddings.model_manager import ModelManager, ModelState
from mindmate.application.embedding_model_install import EMBEDDING_MODEL_INSTALL_TASK
from mindmate.config import Settings
from mindmate.infrastructure.models import BackgroundTask
from mindmate.main import create_app


def fixture_model():
    model = b"onnx fixture " * 12_000
    tokenizer = b"tokenizer fixture"
    config = json.dumps(
        {
            "model_type": "bert",
            "hidden_size": 512,
            "max_position_embeddings": 512,
            "num_hidden_layers": 4,
            "vocab_size": 21_128,
        },
        separators=(",", ":"),
    ).encode()
    payloads = {
        "onnx/model.onnx": model,
        "tokenizer.json": tokenizer,
        "config.json": config,
    }
    manifest = ModelManifest(
        base_model_id="BAAI/bge-small-zh-v1.5",
        base_revision="a" * 40,
        artifact_repository_id="Xenova/bge-small-zh-v1.5",
        artifact_revision="b" * 40,
        license="MIT",
        files=tuple(
            ModelFile(path, len(value), hashlib.sha256(value).hexdigest())
            for path, value in payloads.items()
        ),
    )
    return manifest, payloads


class PausedModelStream(httpx.SyncByteStream):
    def __init__(self, content: bytes, entered: threading.Event, release: threading.Event) -> None:
        self.content = content
        self.entered = entered
        self.release = release

    def __iter__(self):
        midpoint = 64 * 1024
        yield self.content[:midpoint]
        self.entered.set()
        self.release.wait(timeout=0.4)
        yield self.content[midpoint:]

    def close(self) -> None:
        return


def test_install_api_persists_progress_deduplicates_cancels_and_retries(tmp_path: Path) -> None:
    manifest, payloads = fixture_model()
    first_chunk_entered = threading.Event()
    release_first_response = threading.Event()
    model_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal model_requests
        path = request.url.path
        relative = next(item for item in payloads if path.endswith(f"/{item}"))
        content = payloads[relative]
        if relative == "onnx/model.onnx":
            model_requests += 1
            if model_requests == 1:
                return httpx.Response(
                    200,
                    headers={"Content-Length": str(len(content))},
                    stream=PausedModelStream(content, first_chunk_entered, release_first_response),
                    request=request,
                )
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(content))},
            content=content,
            request=request,
        )

    settings = Settings(data_dir=tmp_path, env="test")
    app = create_app(settings)
    app.state.embedding_model_manager = ModelManager(
        settings.model_dir, manifest=manifest, transport=httpx.MockTransport(handler)
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"Origin": "http://127.0.0.1:5173"}
        session = client.post("/api/v1/system/session", headers=headers)
        assert session.status_code == 200

        missing = client.get("/api/v1/embedding-model").json()
        assert missing["state"] == "MISSING"
        assert missing["base_revision"] == "a" * 40
        assert missing["artifact_revision"] == "b" * 40
        assert missing["total_size_bytes"] == manifest.total_size_bytes
        assert missing["can_install"] is True

        started = client.post(
            "/api/v1/embedding-model/install",
            headers={**headers, "Idempotency-Key": "install-model-first"},
        )
        assert started.status_code == 202
        task_id = started.json()["task_id"]
        assert task_id
        assert first_chunk_entered.wait(timeout=5)

        downloading = client.get("/api/v1/embedding-model").json()
        assert downloading["state"] == "DOWNLOADING"
        assert downloading["downloaded_bytes"] > 0
        assert downloading["total_size_bytes"] == manifest.total_size_bytes
        assert downloading["can_cancel"] is True

        duplicate = client.post(
            "/api/v1/embedding-model/install",
            headers={**headers, "Idempotency-Key": "install-model-duplicate"},
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["task_id"] == task_id
        with app.state.session_factory() as session_factory:
            tasks = list(
                session_factory.scalars(
                    select(BackgroundTask).where(
                        BackgroundTask.task_type == EMBEDDING_MODEL_INSTALL_TASK
                    )
                )
            )
        assert len(tasks) == 1

        cancelled = client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            headers={**headers, "Idempotency-Key": "cancel-model-install"},
        )
        assert cancelled.status_code == 200
        release_first_response.set()
        cancelled_status = wait_for_model_state(client, "CANCELLED")
        assert cancelled_status["diagnostic_id"] == task_id
        assert not app.state.embedding_model_manager.install_directory.exists()
        assert app.state.embedding_model_manager.partial_directory.exists()

        retry = client.post(
            "/api/v1/embedding-model/install",
            headers={**headers, "Idempotency-Key": "install-model-retry"},
        )
        assert retry.status_code == 202
        assert retry.json()["task_id"] != task_id
        ready = wait_for_model_state(client, "READY")
        assert ready["downloaded_bytes"] == manifest.total_size_bytes
        assert ready["can_cancel"] is False
        assert app.state.embedding_model_manager.install_directory.is_dir()
        assert not app.state.embedding_model_manager.partial_directory.exists()


def test_model_install_task_recovers_after_application_restart(tmp_path: Path) -> None:
    manifest, payloads = fixture_model()
    entered = threading.Event()
    release = threading.Event()

    def interrupted_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        relative = next(item for item in payloads if path.endswith(f"/{item}"))
        content = payloads[relative]
        if relative == "onnx/model.onnx":
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(content))},
                stream=PausedModelStream(content, entered, release),
                request=request,
            )
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(content))},
            content=content,
            request=request,
        )

    settings = Settings(data_dir=tmp_path, env="test")
    first_app = create_app(settings)
    first_app.state.embedding_model_manager = ModelManager(
        settings.model_dir, manifest=manifest, transport=httpx.MockTransport(interrupted_handler)
    )
    with TestClient(first_app, base_url="http://127.0.0.1") as client:
        headers = {"Origin": "http://127.0.0.1:5173"}
        client.post("/api/v1/system/session", headers=headers)
        started = client.post(
            "/api/v1/embedding-model/install",
            headers={**headers, "Idempotency-Key": "restart-model-install"},
        )
        assert started.status_code == 202
        assert entered.wait(timeout=5)
        task_id = started.json()["task_id"]

    with first_app.state.session_factory() as session_factory:
        task = session_factory.get(BackgroundTask, task_id)
        assert task is not None
        assert task.status == "INTERRUPTED"
        assert task.checkpoint_json["downloaded_bytes"] > 0

    def resumed_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        relative = next(item for item in payloads if path.endswith(f"/{item}"))
        content = payloads[relative]
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(content))},
            content=content,
            request=request,
        )

    second_app = create_app(settings)
    second_app.state.embedding_model_manager = ModelManager(
        settings.model_dir, manifest=manifest, transport=httpx.MockTransport(resumed_handler)
    )
    with TestClient(second_app, base_url="http://127.0.0.1") as client:
        headers = {"Origin": "http://127.0.0.1:5173"}
        client.post("/api/v1/system/session", headers=headers)
        ready = wait_for_model_state(client, "READY")
        assert ready["task_id"] == task_id
        assert ready["downloaded_bytes"] == manifest.total_size_bytes


def test_busy_model_verification_does_not_offer_a_new_install(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    app = create_app(settings)
    manager = ModelManager(settings.model_dir)
    app.state.embedding_model_manager = manager
    monkeypatch.setattr(manager, "status", lambda: manager._status(ModelState.INSTALLING))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"Origin": "http://127.0.0.1:5173"}
        client.post("/api/v1/system/session", headers=headers)
        status_response = client.get("/api/v1/embedding-model")
        assert status_response.json()["state"] == "VERIFYING"
        assert status_response.json()["can_install"] is False


def wait_for_model_state(client: TestClient, expected: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get("/api/v1/embedding-model")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] == expected:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Embedding model state did not become {expected}.")
