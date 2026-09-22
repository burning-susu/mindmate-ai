from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mindmate.api import files as files_api
from mindmate.application import files as file_service
from mindmate.application.files import (
    FileValidationError,
    resolve_storage_path,
    validate_managed_content_path,
)
from mindmate.config import Settings
from mindmate.infrastructure.models import Folder
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


def create_folder(client: TestClient, name: str, key: str, parent_id: str | None = None):
    return client.post(
        "/api/v1/folders",
        headers=write_headers(key),
        json={"name": name, "parent_folder_id": parent_id},
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


def test_office_documents_use_isolated_parsers_and_blank_pdf_is_not_marked_parsed(
    file_client,
) -> None:
    from docx import Document
    from pptx import Presentation
    from pptx.util import Inches
    from pypdf import PdfWriter

    client, _ = file_client
    docx_buffer = io.BytesIO()
    document = Document()
    document.add_heading("学习主题", level=1)
    document.add_paragraph("这是 Word 正文。")
    document.save(docx_buffer)
    docx_response = client.post(
        "/api/v1/file-imports",
        headers=write_headers("import-docx-1"),
        files={
            "files": (
                "lesson.docx",
                docx_buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    docx_item = docx_response.json()["items"][0]
    assert docx_item["parse_status"] == "PARSED"
    docx_preview = client.get(f"/api/v1/files/{docx_item['file_id']}/preview").json()
    assert "这是 Word 正文" in docx_preview["text"]
    assert docx_preview["metadata"]["paragraph_count"] >= 2

    pptx_buffer = io.BytesIO()
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    text_box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    text_box.text = "第一张幻灯片"
    presentation.save(pptx_buffer)
    pptx_response = client.post(
        "/api/v1/file-imports",
        headers=write_headers("import-pptx-1"),
        files={
            "files": (
                "slides.pptx",
                pptx_buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        },
    )
    pptx_item = pptx_response.json()["items"][0]
    assert pptx_item["parse_status"] == "PARSED"
    pptx_preview = client.get(f"/api/v1/files/{pptx_item['file_id']}/preview").json()
    assert "第一张幻灯片" in pptx_preview["text"]
    assert pptx_preview["metadata"]["slide_count"] == 1

    pdf_buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(pdf_buffer)
    pdf_response = client.post(
        "/api/v1/file-imports",
        headers=write_headers("import-pdf-blank-1"),
        files={"files": ("scan.pdf", pdf_buffer.getvalue(), "application/pdf")},
    )
    pdf_item = pdf_response.json()["items"][0]
    assert pdf_item["status"] == "IMPORTED"
    assert pdf_item["parse_status"] == "PARSE_FAILED"
    assert "OCR" in pdf_item["parse_error"]


def test_mime_size_and_batch_limits_are_enforced(file_client, monkeypatch) -> None:
    client, _ = file_client
    mismatch = client.post(
        "/api/v1/file-imports",
        headers=write_headers("mime-mismatch-1"),
        files={"files": ("fake.txt", b"plain", "application/pdf")},
    )
    assert mismatch.json()["items"][0]["error_code"] == "FILE_MIME_INVALID"

    monkeypatch.setattr(file_service, "MAX_FILE_SIZE", 4)
    size_response = import_one(client, "large.txt", b"12345", "size-limit-1")
    assert size_response.json()["items"][0]["error_code"] == "FILE_TOO_LARGE"

    monkeypatch.setattr(file_service, "MAX_FILE_SIZE", 50 * 1024 * 1024)
    monkeypatch.setattr(files_api, "MAX_BATCH_SIZE", 8)
    batch_response = client.post(
        "/api/v1/file-imports",
        headers=write_headers("batch-limit-1"),
        files=[
            ("files", ("one.txt", b"12345", "text/plain")),
            ("files", ("two.txt", b"67890", "text/plain")),
        ],
    )
    assert batch_response.json()["items"][1]["error_code"] == "BATCH_TOO_LARGE"


def test_storage_paths_reject_traversal_absolute_and_symlink_escape(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", env="test")
    settings.ensure_data_dirs()
    with pytest.raises(FileValidationError, match="受控文件路径无效"):
        resolve_storage_path(settings, "../../outside.txt")
    with pytest.raises(FileValidationError, match="受控文件路径无效"):
        resolve_storage_path(settings, str((tmp_path / "outside.txt").resolve()))

    outside = tmp_path / "outside"
    outside.mkdir()
    link = settings.resolved_data_dir / "objects" / "escape"
    symlink_created = True
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        symlink_created = False
    if symlink_created:
        with pytest.raises(FileValidationError, match="受控文件路径"):
            validate_managed_content_path(settings, "objects/escape/secret.txt")

    outside_file = outside / "outside.txt"
    outside_file.write_text("secret", encoding="utf-8")
    hardlink = settings.resolved_data_dir / "objects" / "hardlink.txt"
    os.link(outside_file, hardlink)
    with pytest.raises(FileValidationError, match="硬链接"):
        validate_managed_content_path(settings, "objects/hardlink.txt")


def test_folder_guards_null_semantics_and_multi_level_trash(file_client) -> None:
    client, _ = file_client
    missing_parent = create_folder(client, "orphan", "folder-missing-parent", "missing")
    assert missing_parent.status_code == 404

    root = create_folder(client, "root", "folder-root-guard").json()
    child = create_folder(client, "child", "folder-child-guard", root["folder_id"]).json()
    grandchild = create_folder(
        client, "grandchild", "folder-grandchild-guard", child["folder_id"]
    ).json()
    self_move = client.post(
        f"/api/v1/folders/{root['folder_id']}/move",
        headers=write_headers("folder-self-move"),
        json={"parent_folder_id": root["folder_id"], "row_version": 1},
    )
    assert self_move.status_code == 400
    cycle_move = client.post(
        f"/api/v1/folders/{root['folder_id']}/move",
        headers=write_headers("folder-cycle-move"),
        json={"parent_folder_id": grandchild["folder_id"], "row_version": 1},
    )
    assert cycle_move.status_code == 400

    tag = client.post(
        "/api/v1/tags",
        headers=write_headers("tag-create-color"),
        json={"name": "重点", "color": "#ff0000"},
    ).json()
    cleared = client.patch(
        f"/api/v1/tags/{tag['tag_id']}",
        headers=write_headers("tag-clear-color"),
        json={"color": None},
    )
    assert cleared.json()["color"] is None

    imported = client.post(
        "/api/v1/file-imports",
        headers=write_headers("nested-file-import"),
        data={"folder_id": grandchild["folder_id"]},
        files={"files": ("nested.txt", b"nested", "text/plain")},
    ).json()
    file_id = imported["items"][0]["file_id"]
    client.delete(
        f"/api/v1/folders/{root['folder_id']}?deletion_strategy=TRASH_RECURSIVE",
        headers=write_headers("folder-trash-deep"),
    )
    restored = client.post(
        f"/api/v1/trash/folder/{root['folder_id']}/restore",
        headers=write_headers("folder-restore-deep"),
    )
    assert restored.status_code == 200
    assert client.get(f"/api/v1/files/{file_id}").json()["status"] == "PARSED"

    client.delete(
        f"/api/v1/folders/{root['folder_id']}?deletion_strategy=TRASH_RECURSIVE",
        headers=write_headers("folder-trash-deep-2"),
    )
    purged = client.delete(
        f"/api/v1/trash/folder/{root['folder_id']}?confirmed=true",
        headers=write_headers("folder-purge-deep"),
    )
    assert purged.status_code == 200
    assert client.get(f"/api/v1/files/{file_id}").status_code == 404


def test_corrupt_folder_cycle_is_rejected_without_hanging(file_client) -> None:
    client, _ = file_client
    first = create_folder(client, "first", "cycle-first").json()
    second = create_folder(client, "second", "cycle-second", first["folder_id"]).json()
    factory = client.app.state.session_factory
    with factory() as session:
        session.execute(
            update(Folder)
            .where(Folder.folder_id == first["folder_id"])
            .values(parent_folder_id=second["folder_id"])
        )
        session.commit()
    response = client.post(
        f"/api/v1/folders/{first['folder_id']}/move",
        headers=write_headers("cycle-detected"),
        json={"parent_folder_id": None, "row_version": 1},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FOLDER_TREE_INVALID"
