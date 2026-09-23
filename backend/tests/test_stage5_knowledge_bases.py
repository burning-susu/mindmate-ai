from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mindmate.config import Settings
from mindmate.main import create_app


@pytest.fixture
def knowledge_client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, env="test")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"}
        )
        assert response.status_code == 200
        yield client, settings


def write_headers(key: str) -> dict[str, str]:
    return {"Origin": "http://127.0.0.1:5173", "Idempotency-Key": key}


def create_kb(client: TestClient, name: str = "机器学习") -> dict:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=write_headers(f"create-kb-{len(name)}-{sum(ord(char) for char in name)}"),
        json={
            "name": name,
            "description": "课程资料",
            "icon": "book-open",
            "color": "#176b87",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_empty_knowledge_base_crud_and_duplicate_hint(knowledge_client) -> None:
    client, _ = knowledge_client
    first = create_kb(client)
    assert first["status"] == "EMPTY"
    assert first["file_count"] == 0
    assert first["available_file_count"] == 0
    assert first["row_version"] == 1

    second = create_kb(client, "机器学习")
    assert second["duplicate_name"] is True
    listed = client.get("/api/v1/knowledge-bases").json()["items"]
    assert len(listed) == 2
    assert all(item["duplicate_name"] for item in listed)

    patched = client.patch(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}",
        headers=write_headers("edit-kb-1"),
        json={
            "name": "机器学习进阶",
            "description": "更新后的说明",
            "icon": "graduation-cap",
            "color": "#2f855a",
            "row_version": first["row_version"],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["row_version"] == 2
    assert patched.json()["name"] == "机器学习进阶"

    stale = client.patch(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}",
        headers=write_headers("edit-kb-stale"),
        json={"description": "不应覆盖", "row_version": 1},
    )
    assert stale.status_code == 412
    assert stale.json()["current_row_version"] == 2
    assert client.get(f"/api/v1/knowledge-bases/{first['knowledge_base_id']}").json()[
        "description"
    ] == "更新后的说明"


def test_trash_restore_and_purge_keep_source_files(knowledge_client) -> None:
    client, _ = knowledge_client
    knowledge_base = create_kb(client, "待归档")
    imported = client.post(
        "/api/v1/file-imports",
        headers=write_headers("kb-source-file"),
        data={"knowledge_base_id": knowledge_base["knowledge_base_id"]},
        files={"files": ("source.txt", b"source", "text/plain")},
    )
    assert imported.status_code == 202
    file_id = imported.json()["items"][0]["file_id"]

    current = client.get(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}"
    ).json()
    trashed = client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}",
        params={"expected_version": current["row_version"]},
        headers=write_headers("trash-kb"),
    )
    assert trashed.status_code == 200
    assert trashed.json()["status"] == "IN_TRASH"
    assert trashed.json()["purge_after"] is not None
    assert client.get("/api/v1/knowledge-bases").json()["items"] == []
    assert client.get(f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}").status_code == 404
    trash = client.get("/api/v1/trash/knowledge-bases").json()["items"]
    assert trash[0]["knowledge_base_id"] == knowledge_base["knowledge_base_id"]

    stale_restore = client.post(
        f"/api/v1/trash/knowledge-base/{knowledge_base['knowledge_base_id']}/restore",
        params={"expected_version": current["row_version"]},
        headers=write_headers("restore-kb-stale-1"),
    )
    assert stale_restore.status_code == 412

    restored = client.post(
        f"/api/v1/trash/knowledge-base/{knowledge_base['knowledge_base_id']}/restore",
        params={"expected_version": trashed.json()["row_version"]},
        headers=write_headers("restore-kb"),
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "NEEDS_REBUILD"
    assert restored.json()["row_version"] == 3
    assert client.get(f"/api/v1/files/{file_id}").status_code == 200
    repeated_restore = client.post(
        f"/api/v1/trash/knowledge-base/{knowledge_base['knowledge_base_id']}/restore",
        params={"expected_version": restored.json()["row_version"]},
        headers=write_headers("restore-kb-repeat"),
    )
    assert repeated_restore.status_code == 404

    trashed_again = client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}",
        params={"expected_version": restored.json()["row_version"]},
        headers=write_headers("trash-kb-again"),
    ).json()
    purged = client.delete(
        f"/api/v1/trash/knowledge-base/{knowledge_base['knowledge_base_id']}",
        params={"expected_version": trashed_again["row_version"], "confirmed": "true"},
        headers=write_headers("purge-kb"),
    )
    assert purged.status_code == 200
    assert purged.json()["status"] == "PURGED"
    assert client.get(f"/api/v1/files/{file_id}").status_code == 200
    repeated_purge = client.delete(
        f"/api/v1/trash/knowledge-base/{knowledge_base['knowledge_base_id']}",
        params={"expected_version": trashed_again["row_version"], "confirmed": "true"},
        headers=write_headers("purge-kb-repeat"),
    )
    assert repeated_purge.status_code == 404


def test_knowledge_base_persists_after_restart(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"})
        knowledge_base_id = create_kb(client, "重启验证")["knowledge_base_id"]

    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        detail = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}")
        assert detail.status_code == 200
        assert detail.json()["name"] == "重启验证"


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"name": ""}, 422),
        ({"name": "x" * 101}, 422),
        ({"name": "有效", "description": "x" * 2001}, 422),
        ({"name": "有效", "color": "red"}, 422),
    ],
)
def test_knowledge_base_boundaries(knowledge_client, payload: dict, expected_status: int) -> None:
    client, _ = knowledge_client
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=write_headers(f"boundary-{len(str(payload))}"),
        json=payload,
    )
    assert response.status_code == expected_status


def test_patch_rejects_explicit_null_name(knowledge_client) -> None:
    client, _ = knowledge_client
    knowledge_base = create_kb(client, "名称约束")
    response = client.patch(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}",
        headers=write_headers("patch-null-name"),
        json={"name": None, "row_version": knowledge_base["row_version"]},
    )
    assert response.status_code == 422
