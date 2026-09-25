from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mindmate.application.index_preprocessing import get_or_create_default_configs
from mindmate.application.knowledge_membership_worker import KnowledgeMembershipWorker
from mindmate.config import Settings
from mindmate.infrastructure.models import (
    BackgroundTask,
    FileRecord,
    IndexVersion,
    IndexVersionInput,
    KnowledgeBase,
    KnowledgeBaseFile,
    new_id,
)
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


def test_index_status_reports_empty_and_pending_member_state(knowledge_client) -> None:
    client, _ = knowledge_client
    knowledge_base = create_kb(client, "索引状态")
    empty_status = client.get(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/index-status"
    )
    assert empty_status.status_code == 200
    assert empty_status.json()["status"] == "EMPTY"
    assert empty_status.json()["file_counts"] == {
        "total": 0,
        "available": 0,
        "processing": 0,
        "failed": 0,
    }
    assert empty_status.json()["active_index_version_id"] is None
    assert empty_status.json()["failures"] == []

    file_id = import_text(
        client, "状态讲义.txt", "可观察的索引状态。".encode(), "index-status-file"
    )
    membership_task = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
        headers=write_headers("index-status-member"),
        json={"file_ids": [file_id]},
    ).json()
    assert wait_for_task(client, membership_task["task_id"])["status"] == "COMPLETED"
    status = client.get(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/index-status"
    ).json()
    assert status["status"] == "PREPARING"
    assert status["file_counts"] == {"total": 1, "available": 0, "processing": 1, "failed": 0}
    assert status["target_index_version_id"] is None
    assert status["embedding_model_state"] in {"MISSING_OFFLINE", "READY", "CORRUPT"}


def test_index_retry_is_persisted_and_rejects_files_outside_failed_members(
    knowledge_client,
) -> None:
    client, _ = knowledge_client
    first = create_kb(client, "失败文件所在库")
    second = create_kb(client, "另一个库")
    file_id = import_text(client, "失败讲义.txt", "失败后可重试。".encode(), "retry-failed-file")
    for knowledge_base, key in ((first, "retry-member-first"), (second, "retry-member-second")):
        task = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
            headers=write_headers(key),
            json={"file_ids": [file_id]},
        ).json()
        assert wait_for_task(client, task["task_id"])["status"] == "COMPLETED"

    factory = client.app.state.session_factory
    with factory() as session:
        member = session.scalar(
            select(KnowledgeBaseFile).where(
                KnowledgeBaseFile.knowledge_base_id == first["knowledge_base_id"],
                KnowledgeBaseFile.file_id == file_id,
            )
        )
        assert member is not None
        member.index_state = "FAILED"
        session.commit()

    failed_status = client.get(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/index-status"
    ).json()
    assert failed_status["failures"][0]["file_id"] == file_id
    assert failed_status["failures"][0]["retryable"] is True
    assert failed_status["can_retry_failed"] is True

    outside_scope = client.post(
        f"/api/v1/knowledge-bases/{second['knowledge_base_id']}/index/retry-failed",
        headers=write_headers("retry-cross-kb"),
        json={"file_ids": [file_id]},
    )
    assert outside_scope.status_code == 409
    assert outside_scope.json()["code"] == "INDEX_RETRY_SCOPE_INVALID"

    headers = write_headers("retry-failed-index-operation")
    retry = client.post(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/index/retry-failed",
        headers=headers,
        json={"file_ids": [file_id]},
    )
    assert retry.status_code == 202
    assert retry.json()["task_type"] == "INDEX_PREPROCESS"
    assert retry.json()["task_id"]
    repeated = client.post(
        f"/api/v1/knowledge-bases/{first['knowledge_base_id']}/index/retry-failed",
        headers=headers,
        json={"file_ids": [file_id]},
    )
    assert repeated.status_code == 202
    assert repeated.json()["task_id"] == retry.json()["task_id"]
    with factory() as session:
        persisted = session.get(BackgroundTask, retry.json()["task_id"])
        assert persisted is not None
        assert persisted.checkpoint_json["operation"] == "RETRY_FAILED_FILES"
        assert persisted.checkpoint_json["requested_failed_file_ids"] == [file_id]


def test_failed_rebuild_status_keeps_the_active_index_available(knowledge_client) -> None:
    client, _ = knowledge_client
    knowledge_base = create_kb(client, "保留活动版本")
    file_id = import_text(client, "活动文件.txt", "活动索引仍可用。".encode(), "active-index-file")
    task = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
        headers=write_headers("active-index-member"),
        json={"file_ids": [file_id]},
    ).json()
    assert wait_for_task(client, task["task_id"])["status"] == "COMPLETED"

    factory = client.app.state.session_factory
    active_version_id = new_id()
    failed_version_id = new_id()
    failed_task_id = new_id()
    now = datetime.now(UTC)
    with factory() as session:
        record = session.get(KnowledgeBase, knowledge_base["knowledge_base_id"])
        member = session.scalar(
            select(KnowledgeBaseFile).where(
                KnowledgeBaseFile.knowledge_base_id == knowledge_base["knowledge_base_id"],
                KnowledgeBaseFile.file_id == file_id,
            )
        )
        file = session.get(FileRecord, file_id)
        assert record is not None and member is not None and file is not None
        chunking, embedding = get_or_create_default_configs(session)
        record.active_index_version_id = active_version_id
        record.status = "READY"
        member.index_state = "READY"
        versions = []
        for version_id, version_status, embedding_status, created_at in (
            (active_version_id, "READY", "COMPLETED", now),
            (failed_version_id, "FAILED", "FAILED", datetime.fromtimestamp(now.timestamp() + 1, UTC)),
        ):
            versions.append(
                IndexVersion(
                    index_version_id=version_id,
                    scope_type="KNOWLEDGE_BASE",
                    scope_id=record.knowledge_base_id,
                    parse_revision_set_hash=file.content_hash,
                    chunking_config_id=chunking.chunking_config_id,
                    embedding_config_id=embedding.embedding_config_id,
                    vector_engine="sqlite-vec",
                    vector_engine_version="test",
                    status=version_status,
                    preprocessing_status="COMPLETED",
                    chunking_status="COMPLETED",
                    embedding_status=embedding_status,
                    fts_status="COMPLETED",
                    input_count=1,
                    prepared_count=1,
                    created_at=created_at,
                    activated_at=now if version_status == "READY" else None,
                )
            )
        session.add_all(versions)
        session.flush()
        session.add_all(
            [
                IndexVersionInput(
                    index_version_input_id=new_id(),
                    index_version_id=active_version_id,
                    knowledge_base_file_id=member.knowledge_base_file_id,
                    file_id=file_id,
                    content_hash=file.content_hash,
                    parse_revision_id=file.parse_revision_id,
                    membership_added_at=member.added_at,
                    ordinal=0,
                    status="PREPARED",
                    chunk_status="CHUNKED",
                    embedding_status="EMBEDDED",
                    fts_status="INDEXED",
                ),
                IndexVersionInput(
                    index_version_input_id=new_id(),
                    index_version_id=failed_version_id,
                    knowledge_base_file_id=member.knowledge_base_file_id,
                    file_id=file_id,
                    content_hash=file.content_hash,
                    parse_revision_id=file.parse_revision_id,
                    membership_added_at=member.added_at,
                    ordinal=0,
                    status="PREPARED",
                    chunk_status="CHUNKED",
                    embedding_status="FAILED",
                    embedding_reason_code="MODEL_MISSING_OFFLINE",
                    fts_status="INDEXED",
                ),
            ]
        )
        session.add(
            BackgroundTask(
                task_id=failed_task_id,
                task_type="INDEX_EMBED",
                status="FAILED",
                phase="EMBEDDING_FAILED",
                idempotency_key=new_id(),
                checkpoint_json={
                    "knowledge_base_id": record.knowledge_base_id,
                    "index_version_id": failed_version_id,
                },
                created_at=now,
                updated_at=now,
                completed_at=now,
            )
        )
        session.commit()

    status = client.get(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/index-status"
    ).json()
    assert status["status"] == "READY"
    assert status["active_index_version_id"] == active_version_id
    assert status["target_index_version_id"] == failed_version_id
    assert status["target_index_version_status"] == "FAILED"
    assert status["operation_in_progress"] is False
    assert status["failures"] == [
        {
            "file_id": file_id,
            "display_name": "活动文件.txt",
            "stage": "EMBEDDING",
            "reason_code": "MODEL_MISSING_OFFLINE",
            "message": "本地 Embedding 模型缺失；当前操作没有触发下载。恢复模型后可重试。",
            "retryable": True,
            "diagnostic_id": failed_task_id,
        }
    ]


def test_rebuild_is_full_and_rejects_empty_or_trashed_inputs(knowledge_client) -> None:
    client, _ = knowledge_client
    empty = create_kb(client, "不可重建空库")
    rejected = client.post(
        f"/api/v1/knowledge-bases/{empty['knowledge_base_id']}/index/rebuild",
        headers=write_headers("rebuild-empty-kb"),
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "INDEX_INPUT_REQUIRED"

    knowledge_base = create_kb(client, "可重建知识库")
    file_id = import_text(client, "重建资料.txt", "完整重建验证。".encode(), "rebuild-input")
    membership_task = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/files",
        headers=write_headers("rebuild-member"),
        json={"file_ids": [file_id]},
    ).json()
    assert wait_for_task(client, membership_task["task_id"])["status"] == "COMPLETED"
    rebuilt = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base['knowledge_base_id']}/index/rebuild",
        headers=write_headers("rebuild-current-kb"),
    )
    assert rebuilt.status_code == 202
    with client.app.state.session_factory() as session:
        task = session.get(BackgroundTask, rebuilt.json()["task_id"])
        assert task is not None
        assert task.checkpoint_json["operation"] == "REBUILD"
        assert task.checkpoint_json["full_rebuild"] is True

    other = create_kb(client, "回收站成员知识库")
    trashed_file_id = import_text(
        client, "已回收资料.txt", "已进入回收站。".encode(), "trash-index-source"
    )
    add = client.post(
        f"/api/v1/knowledge-bases/{other['knowledge_base_id']}/files",
        headers=write_headers("trash-index-member"),
        json={"file_ids": [trashed_file_id]},
    ).json()
    assert wait_for_task(client, add["task_id"])["status"] == "COMPLETED"
    file = client.get(f"/api/v1/files/{trashed_file_id}").json()
    trash = client.delete(
        f"/api/v1/files/{trashed_file_id}?expected_version={file['row_version']}",
        headers=write_headers("trash-index-source-now"),
    )
    assert trash.status_code == 200
    denied = client.post(
        f"/api/v1/knowledge-bases/{other['knowledge_base_id']}/index/rebuild",
        headers=write_headers("rebuild-trashed-member"),
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == "INDEX_INPUT_REQUIRED"

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
