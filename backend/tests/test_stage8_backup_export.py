from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.application.backups import create_backup, verify_backup
from mindmate.application.local_backup import BackupBuildError, verify_backup_archive
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    ContentObject,
    Conversation,
    LearningSession,
    Message,
    new_id,
)
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore

ORIGIN = "http://127.0.0.1:5173"
SECRET = "fixture-backup-secret-do-not-pack"


def _stream_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(
            b'data: {"id":"probe","model":"deepseek-flash",'
            b'"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
            b'data: {"id":"probe","model":"deepseek-flash",'
            b'"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":8,"completion_tokens":3,"total_tokens":11}}\n\n'
            b"data: [DONE]\n\n"
        ),
        request=request,
    )


def _make_app(tmp_path: Path) -> tuple[TestClient, InMemoryCredentialStore, Settings]:
    settings = Settings(data_dir=tmp_path, env="test", provider_base_url="https://fixture.invalid")
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model=DEEPSEEK_MODEL,
        transport=httpx.MockTransport(_stream_response),
    )
    return TestClient(app, base_url="http://127.0.0.1"), store, settings


def _session_headers(client: TestClient, *, idempotency: str | None = None) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {
        "Origin": ORIGIN,
        "Idempotency-Key": idempotency or str(uuid4()),
    }


def _seed_content_object(session: Session, settings: Settings, payload: bytes) -> ContentObject:
    now = datetime.now(UTC)
    content_id = new_id()
    relative = f"objects/{content_id[:2]}/{content_id}.txt"
    absolute = settings.resolved_data_dir / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(payload)
    row = ContentObject(
        content_object_id=content_id,
        sha256=__import__("hashlib").sha256(payload).hexdigest(),
        byte_size=len(payload),
        detected_mime_type="text/plain",
        storage_relative_path=relative,
        storage_state="READY",
        reference_count=1,
        created_at=now,
        verified_at=now,
    )
    session.add(row)
    session.commit()
    return row


def test_empty_database_backup_create_verify_download(tmp_path: Path) -> None:
    client, _, _ = _make_app(tmp_path)
    with client:
        headers = _session_headers(client)
        created = client.post("/api/v1/backups", headers=headers, json={})
        assert created.status_code == 200
        body = created.json()
        assert body["status"] == "COMPLETED"
        assert body["includes_secrets"] is False
        assert body["encrypted"] is False
        assert body["unencrypted_warning"] is True
        assert body["contains_user_files_and_history"] is True
        assert body["restore_available"] is False
        assert body["download_available"] is True
        assert body["file_count"] >= 1  # database snapshot at minimum
        assert "api_key" not in created.text.lower() or "api_key" not in json.dumps(body).lower()

        listed = client.get("/api/v1/backups", headers={"Origin": ORIGIN})
        assert listed.status_code == 200
        assert listed.json()["items"][0]["backup_id"] == body["backup_id"]

        verified = client.post(
            f"/api/v1/backups/{body['backup_id']}/verify",
            headers=_session_headers(client),
            json={},
        )
        assert verified.status_code == 200
        assert verified.json()["verified"] is True

        download = client.get(
            f"/api/v1/backups/{body['backup_id']}/download",
            headers={"Origin": ORIGIN},
        )
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/zip")
        assert "attachment" in download.headers.get("content-disposition", "")
        # Never JSON-wrap archive bytes.
        assert not download.headers.get("content-type", "").startswith("application/json")
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert "manifest.json" in archive.namelist()
            assert "database/mindmate.db" in archive.namelist()


def test_backup_includes_files_excludes_secrets_logs_models(tmp_path: Path) -> None:
    client, store, settings = _make_app(tmp_path)
    with client:
        factory = client.app.state.session_factory
        with factory() as session:
            _seed_content_object(session, settings, b"knowledge-bytes")
            now = datetime.now(UTC)
            conversation = Conversation(
                title="fixture-chat",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
                last_active_at=now,
            )
            session.add(conversation)
            session.flush()
            session.add(
                Message(
                    conversation_id=conversation.conversation_id,
                    role="user",
                    content="hello",
                    status="COMPLETED",
                    sequence_number=1,
                    mode_snapshot="GENERAL_CHAT",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                LearningSession(
                    topic="fixture",
                    goal_type="CUSTOM",
                    goal_text="learn",
                    knowledge_base_id=new_id(),
                    target_question_count=3,
                    initial_difficulty="BASIC",
                    status="ACTIVE",
                    idempotency_key=str(uuid4()),
                    client_request_id=str(uuid4()),
                    request_hash="b" * 64,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

        (settings.resolved_data_dir / "logs").mkdir(parents=True, exist_ok=True)
        (settings.resolved_data_dir / "logs" / "app.log").write_text(SECRET, encoding="utf-8")
        (settings.resolved_data_dir / "models").mkdir(parents=True, exist_ok=True)
        (settings.resolved_data_dir / "models" / "weights.bin").write_bytes(b"model-cache")
        (settings.resolved_data_dir / "config").mkdir(parents=True, exist_ok=True)
        (settings.resolved_data_dir / "config" / "ui.json").write_text('{"theme":"light"}', encoding="utf-8")
        (settings.resolved_data_dir / "config" / ".env").write_text(f"KEY={SECRET}", encoding="utf-8")
        store.set_secret("provider/deepseek/api-key", SECRET)

        headers = _session_headers(client)
        created = client.post("/api/v1/backups", headers=headers, json={})
        assert created.status_code == 200
        body = created.json()
        assert body["status"] == "COMPLETED"
        assert body["file_count"] >= 2

        download = client.get(
            f"/api/v1/backups/{body['backup_id']}/download",
            headers={"Origin": ORIGIN},
        )
        assert download.status_code == 200
        raw = download.content
        assert SECRET.encode() not in raw
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert "database/mindmate.db" in names
            assert any(name.startswith("objects/") for name in names)
            assert "config/ui.json" in names
            assert "logs/app.log" not in names
            assert "models/weights.bin" not in names
            assert "config/.env" not in names
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["includes_secrets"] is False
            assert manifest["includes_vectors"] is False
            assert "vectors" in manifest["rebuild_after_restore"]


def test_backup_rejects_missing_content_object(tmp_path: Path) -> None:
    client, _, settings = _make_app(tmp_path)
    with client:
        factory = client.app.state.session_factory
        with factory() as session:
            now = datetime.now(UTC)
            session.add(
                ContentObject(
                    content_object_id=new_id(),
                    sha256="a" * 64,
                    byte_size=12,
                    detected_mime_type="text/plain",
                    storage_relative_path="objects/ab/missing.txt",
                    storage_state="READY",
                    reference_count=1,
                    created_at=now,
                    verified_at=now,
                )
            )
            session.commit()
        headers = _session_headers(client)
        created = client.post("/api/v1/backups", headers=headers, json={})
        assert created.status_code == 200
        body = created.json()
        assert body["status"] == "FAILED"
        assert body["download_available"] is False
        assert not list((settings.resolved_data_dir / "backups").glob("*.mindmate-backup"))


def test_backup_idempotent_retry(tmp_path: Path) -> None:
    client, _, _ = _make_app(tmp_path)
    with client:
        key = str(uuid4())
        first = client.post(
            "/api/v1/backups",
            headers=_session_headers(client, idempotency=key),
            json={},
        )
        second = client.post(
            "/api/v1/backups",
            headers=_session_headers(client, idempotency=key),
            json={},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["backup_id"] == second.json()["backup_id"]
        assert first.json()["status"] == "COMPLETED"


def test_verify_rejects_path_traversal_zip(tmp_path: Path) -> None:
    archive = tmp_path / "evil.mindmate-backup"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", b"nope")
        handle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "backup_format_version": "1",
                    "schema_version": "test",
                    "file_count": 1,
                    "total_size": 4,
                    "entries": [{"path": "../escape.txt", "sha256": "0" * 64, "byte_size": 4}],
                    "includes_secrets": False,
                    "includes_vectors": False,
                }
            ).encode(),
        )
    try:
        verify_backup_archive(archive)
        raised = False
    except BackupBuildError:
        raised = True
    assert raised


def test_create_backup_library_excludes_logs_and_keeps_callable(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "database").mkdir()
    db = data / "database" / "mindmate.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('test_rev')")
        conn.execute(
            "CREATE TABLE content_objects ("
            "content_object_id TEXT PRIMARY KEY, sha256 TEXT, byte_size INT, "
            "detected_mime_type TEXT, storage_relative_path TEXT, storage_state TEXT, "
            "reference_count INT, created_at TEXT, verified_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE files (file_id TEXT PRIMARY KEY, deleted_at TEXT)"
        )
        conn.commit()
    (data / "logs").mkdir()
    (data / "logs" / "x.log").write_text(SECRET, encoding="utf-8")
    (data / "config").mkdir()
    (data / "config" / "ok.json").write_text("{}", encoding="utf-8")
    archive = tmp_path / "out.mindmate-backup"
    manifest = create_backup(data, archive, "test_rev")
    assert manifest["includes_secrets"] is False
    assert SECRET.encode() not in archive.read_bytes()
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
        assert "logs/x.log" not in names
        assert "config/ok.json" in names
        assert "database/mindmate.db" in names
    assert verify_backup(archive)["file_count"] == manifest["file_count"]


def test_restore_endpoint_disabled(tmp_path: Path) -> None:
    client, _, _ = _make_app(tmp_path)
    with client:
        headers = _session_headers(client)
        created = client.post("/api/v1/backups", headers=headers, json={})
        backup_id = created.json()["backup_id"]
        restore = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=_session_headers(client),
            json={},
        )
        assert restore.status_code == 501
        assert restore.json()["code"] == "BACKUP_RESTORE_DISABLED"
