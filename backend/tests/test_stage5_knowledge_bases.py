from __future__ import annotations

import threading
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from mindmate.application.knowledge_membership_worker import KnowledgeMembershipWorker
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


def wait_for_task(client: TestClient, task_id: str) -> dict:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        task = client.get(f"/api/v1/tasks/{task_id}").json()
        if task["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return task
        sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


def import_text(client: TestClient, name: str, content: bytes, key: str) -> str:
    response = client.post(
        "/api/v1/file-imports",
        headers=write_headers(key),
        files={"files": (name, content, "text/plain")},
    )
    assert response.status_code == 202
    body = response.json()
    wait_for_task(client, body["task_id"])
    return body["items"][0]["file_id"]


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


def test_membership_task_supports_partial_results_shared_files_and_readd(knowledge_client) -> None:
    client, _ = knowledge_client
    first = create_kb(client, "第一知识库")
    second = create_kb(client, "第二知识库")
    file_id = import_text(client, "shared.txt", b"shared knowledge", "shared-source")

    submitted = client.post(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/files",
        headers=write_headers("membership-mixed"),
        json={"file_ids": [file_id, "missing-file", file_id]},
    )
    assert submitted.status_code == 202
    completed = wait_for_task(client, submitted.json()["task_id"])
    assert completed["status"] == "COMPLETED"
    assert completed["summary"] == {"added": 1, "failed": 1}
    assert {item["reason"] for item in completed["results"] if item["status"] == "FAILED"} == {
        "FILE_NOT_FOUND"
    }

    members = client.get(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/files"
    ).json()["items"]
    assert len(members) == 1
    assert members[0]["file_id"] == file_id
    assert members[0]["file_status"] == "PARSED"
    assert members[0]["index_state"] == "PENDING"
    assert members[0]["available_for_retrieval"] is False
    assert members[0]["unavailable_reason"] == "索引待建立"
    assert client.get(f"/api/v1/knowledge-bases/{first['knowledge_base_id']}").json()[
        "status"
    ] == "PREPARING"

    other_task = client.post(
        f"/api/v1/knowledge-bases/{second['knowledge_base_id']}/files",
        headers=write_headers("membership-other-kb"),
        json={"file_ids": [file_id]},
    ).json()
    assert wait_for_task(client, other_task["task_id"])["status"] == "COMPLETED"
    assert len(client.get(f"/api/v1/files/{file_id}/knowledge-bases").json()["items"]) == 2

    removed = client.delete(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/files/{file_id}",
        headers=write_headers("membership-remove"),
    )
    assert removed.status_code == 200
    assert client.get(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/files"
    ).json()["items"] == []
    assert client.get(f"/api/v1/files/{file_id}").status_code == 200

    readded = client.post(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/files",
        headers=write_headers("membership-readd"),
        json={"file_ids": [file_id]},
    ).json()
    result = wait_for_task(client, readded["task_id"])["results"][0]
    assert result["action"] == "RESTORED"
    assert len(client.get(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/files"
    ).json()["items"]) == 1


def test_membership_request_is_idempotent_and_rejects_trashed_file(knowledge_client) -> None:
    client, _ = knowledge_client
    knowledge_base = create_kb(client, "幂等验证")
    file_id = import_text(client, "trash.txt", b"trash", "trash-source")
    file = client.get(f"/api/v1/files/{file_id}").json()
    trashed = client.delete(
        f"/api/v1/files/{file_id}?expected_version={file['row_version']}",
        headers=write_headers("trash-member-source"),
    )
    assert trashed.status_code == 200

    headers = write_headers("same-membership-request")
    first = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
        headers=headers,
        json={"file_ids": [file_id]},
    )
    second = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
        headers=headers,
        json={"file_ids": [file_id]},
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["task_id"] == second.json()["task_id"]
    completed = wait_for_task(client, first.json()["task_id"])
    assert completed["results"][0]["reason"] == "FILE_IN_TRASH"
    assert client.get(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files"
    ).json()["items"] == []


def test_running_membership_task_cancellation_is_not_overwritten(
    knowledge_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = knowledge_client
    knowledge_base = create_kb(client, "取消验证")
    file_id = import_text(client, "cancel.txt", b"cancel", "cancel-source")
    entered = threading.Event()
    release = threading.Event()
    original = KnowledgeMembershipWorker._process_item

    def blocked_process(self, session, target, item):
        entered.set()
        assert release.wait(3)
        return original(self, session, target, item)

    monkeypatch.setattr(KnowledgeMembershipWorker, "_process_item", blocked_process)
    submitted = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
        headers=write_headers("cancel-membership-task"),
        json={"file_ids": [file_id]},
    )
    assert submitted.status_code == 202
    task_id = submitted.json()["task_id"]
    assert entered.wait(3)
    cancelled = client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers=write_headers("cancel-membership-now"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    release.set()
    assert wait_for_task(client, task_id)["status"] == "CANCELLED"
