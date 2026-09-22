from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mindmate.config import Settings
from mindmate.main import create_app


@pytest.fixture
def file_client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, env="test")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
        )
        assert response.status_code == 200
        yield client, tmp_path


def write_headers(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def import_one(client: TestClient, name: str, content: bytes, key: str):
    return client.post(
        "/api/v1/file-imports",
        headers=write_headers(key),
        files={"files": (name, content, "text/plain")},
    )


def test_text_import_is_streamed_into_controlled_storage(file_client) -> None:
    client, data_dir = file_client
    response = import_one(client, "notes.txt", "第一行\n第二行".encode(), "import-text-1")

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    item = payload["items"][0]
    assert item["status"] == "IMPORTED"
    file_id = item["file_id"]

    detail = client.get(f"/api/v1/files/{file_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "PARSED"
    assert detail.json()["content_available"] is True

    text = client.get(f"/api/v1/files/{file_id}/text")
    assert text.status_code == 200
    assert "第二行" in text.json()["text"]

    content = client.get(f"/api/v1/files/{file_id}/content")
    assert content.status_code == 200
    assert content.headers["x-content-type-options"] == "nosniff"
    assert content.content == "第一行\n第二行".encode()
    assert list((data_dir / "objects").rglob("*.txt"))
    assert not list((data_dir / "tasks").rglob("*.staging"))


def test_duplicate_requires_decision_and_separate_record_reuses_content(file_client) -> None:
    client, data_dir = file_client
    first = import_one(client, "same.txt", b"same-content", "import-duplicate-1")
    first_file_id = first.json()["items"][0]["file_id"]
    duplicate = import_one(client, "copy.txt", b"same-content", "import-duplicate-2")

    assert duplicate.status_code == 202
    duplicate_payload = duplicate.json()
    assert duplicate_payload["status"] == "BLOCKED"
    assert duplicate_payload["items"][0]["duplicate_status"] == "PENDING_DECISION"
    import_id = duplicate_payload["import_id"]
    decision = client.post(
        f"/api/v1/file-imports/{import_id}/duplicate-decisions",
        headers=write_headers("duplicate-decision-1"),
        json={"decisions": [{"item_index": 0, "decision": "CREATE_SEPARATE_RECORD"}]},
    )
    assert decision.status_code == 200
    second_file_id = decision.json()["items"][0]["file_id"]
    assert second_file_id != first_file_id
    assert len([path for path in (data_dir / "objects").rglob("*") if path.is_file()]) == 1

    listed = client.get("/api/v1/files").json()["items"]
    assert {item["file_id"] for item in listed} == {first_file_id, second_file_id}


def test_invalid_signature_and_batch_limits_are_rejected_per_item(file_client) -> None:
    client, _ = file_client
    disguised = client.post(
        "/api/v1/file-imports",
        headers=write_headers("import-invalid-signature"),
        files={"files": ("fake.pdf", b"plain text", "application/pdf")},
    )
    assert disguised.status_code == 202
    assert disguised.json()["items"][0]["error_code"] == "FILE_SIGNATURE_INVALID"

    too_many = client.post(
        "/api/v1/file-imports",
        headers=write_headers("import-too-many"),
        files=[("files", (f"{index}.txt", b"x", "text/plain")) for index in range(21)],
    )
    assert too_many.status_code == 202
    assert too_many.json()["items"][-1]["error_code"] == "TOO_MANY_FILES"


def test_folder_tag_trash_restore_and_purge(file_client) -> None:
    client, data_dir = file_client
    folder = client.post(
        "/api/v1/folders",
        headers=write_headers("folder-create-1"),
        json={"name": "资料"},
    )
    assert folder.status_code == 201
    folder_id = folder.json()["folder_id"]
    tag = client.post(
        "/api/v1/tags",
        headers=write_headers("tag-create-1"),
        json={"name": "重要", "color": "#176b87"},
    )
    assert tag.status_code == 201
    tag_id = tag.json()["tag_id"]
    imported = client.post(
        "/api/v1/file-imports",
        headers=write_headers("import-folder-tag-1"),
        data={"folder_id": folder_id, "tag_ids": f'["{tag_id}"]'},
        files={"files": ("organized.md", b"# title", "text/markdown")},
    )
    file_id = imported.json()["items"][0]["file_id"]
    assert imported.status_code == 202
    assert client.get(f"/api/v1/files/{file_id}").json()["folder_id"] == folder_id
    assert client.get("/api/v1/files?q=重要").json()["items"][0]["file_id"] == file_id

    trashed = client.delete(
        f"/api/v1/files/{file_id}",
        params={"expected_version": 1},
        headers=write_headers("trash-file-1"),
    )
    assert trashed.status_code == 200
    assert client.get("/api/v1/files").json()["items"] == []
    assert client.get("/api/v1/trash").json()["files"][0]["file_id"] == file_id

    restored = client.post(
        f"/api/v1/trash/file/{file_id}/restore", headers=write_headers("restore-file-1")
    )
    assert restored.status_code == 200
    assert client.get("/api/v1/files").json()["items"][0]["file_id"] == file_id

    deleted = client.delete(
        f"/api/v1/files/{file_id}",
        params={"expected_version": restored.json()["row_version"]},
        headers=write_headers("trash-file-2"),
    )
    assert deleted.status_code == 200
    purged = client.delete(
        f"/api/v1/trash/file/{file_id}",
        params={"confirmed": "true", "expected_version": deleted.json()["row_version"]},
        headers=write_headers("purge-file-1"),
    )
    assert purged.status_code == 200
    assert client.get(f"/api/v1/files/{file_id}").status_code == 404
    assert not [path for path in (data_dir / "objects").rglob("*") if path.is_file()]


def test_folder_tree_restore_and_permanent_purge(file_client) -> None:
    client, data_dir = file_client
    root = client.post(
        "/api/v1/folders", headers=write_headers("tree-root-1"), json={"name": "根"}
    ).json()
    child = client.post(
        "/api/v1/folders",
        headers=write_headers("tree-child-1"),
        json={"name": "子", "parent_folder_id": root["folder_id"]},
    ).json()
    imported = client.post(
        "/api/v1/file-imports",
        headers=write_headers("tree-import-1"),
        data={"folder_id": child["folder_id"]},
        files={"files": ("tree.txt", b"tree", "text/plain")},
    ).json()
    file_id = imported["items"][0]["file_id"]

    deleted = client.delete(
        f"/api/v1/folders/{root['folder_id']}",
        params={"deletion_strategy": "TRASH_RECURSIVE"},
        headers=write_headers("tree-trash-1"),
    )
    assert deleted.status_code == 200
    assert client.get("/api/v1/files").json()["items"] == []
    restored = client.post(
        f"/api/v1/trash/folder/{root['folder_id']}/restore",
        headers=write_headers("tree-restore-1"),
    )
    assert restored.status_code == 200
    assert client.get("/api/v1/files").json()["items"][0]["file_id"] == file_id

    client.delete(
        f"/api/v1/folders/{root['folder_id']}",
        params={"deletion_strategy": "TRASH_RECURSIVE"},
        headers=write_headers("tree-trash-2"),
    )
    purged = client.delete(
        f"/api/v1/trash/folder/{root['folder_id']}",
        params={"confirmed": "true"},
        headers=write_headers("tree-purge-1"),
    )
    assert purged.status_code == 200
    assert client.get(f"/api/v1/files/{file_id}").status_code == 404
    assert not [path for path in (data_dir / "objects").rglob("*") if path.is_file()]
