from __future__ import annotations

import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mindmate.api import files as files_api
from mindmate.application import pptx_preview
from mindmate.application.files import (
    FileValidationError,
    document_spec,
    parse_document_in_subprocess,
    validate_file_format,
    validate_upload_mime,
)
from mindmate.application.parser_worker import ParseFailure, _parse_xlsx
from mindmate.application.pptx_preview import get_or_create_xlsx_sheet_preview
from mindmate.config import Settings
from mindmate.main import create_app


def make_xlsx(path: Path) -> None:
    entries = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets><sheet name="成绩表" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>姓名</t></si><si><t>林同学</t></si></sst>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>98</v></c></row></sheetData></worksheet>',
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def make_pptx_package(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
        )


def test_xlsx_parser_extracts_cells_and_sheet_locations(tmp_path: Path) -> None:
    source = tmp_path / "grades.xlsx"
    make_xlsx(source)
    spec = document_spec(source.name)
    validate_file_format(source, spec, source.read_bytes()[:8192])
    validate_upload_mime(spec, spec.mime_type)

    result = _parse_xlsx(source)

    assert result["text"] == "姓名\n林同学\n98"
    assert result["metadata"]["sheet_count"] == 1
    assert result["metadata"]["cell_count"] == 3
    assert result["locations"][1] == {
        "start": 2,
        "length": 3,
        "sheet": 1,
        "sheet_name": "成绩表",
        "cell": "A2",
    }


def test_xlsx_parser_rejects_duplicate_zip_entries(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.xlsx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")

    with pytest.raises(ParseFailure, match="重复"):
        _parse_xlsx(source)


@pytest.mark.parametrize(
    ("name", "payload", "mime"),
    [
        (
            "deck.ppt",
            bytes.fromhex("D0CF11E0A1B11AE1") + b"fixture",
            "application/vnd.ms-powerpoint",
        ),
    ],
)
def test_new_office_formats_validate_extension_and_mime(
    tmp_path: Path, name: str, payload: bytes, mime: str
) -> None:
    source = tmp_path / name
    source.write_bytes(payload)
    spec = document_spec(name)

    validate_file_format(source, spec, payload[:8192])
    validate_upload_mime(spec, mime)


def test_ppt_rejects_zip_disguised_as_binary_presentation(tmp_path: Path) -> None:
    source = tmp_path / "fake.ppt"
    source.write_bytes(b"PK\x03\x04fake")

    with pytest.raises(FileValidationError, match="旧版 PowerPoint"):
        validate_file_format(source, document_spec(source.name), source.read_bytes())


def test_ppt_extension_accepts_a_valid_ooxml_presentation_package(tmp_path: Path) -> None:
    source = tmp_path / "renamed.ppt"
    make_pptx_package(source)

    validate_file_format(source, document_spec(source.name), source.read_bytes()[:8192])
    validate_upload_mime(document_spec(source.name), "application/zip")


def test_xlsx_isolated_parser_reads_workbook(tmp_path: Path) -> None:
    xlsx_source = tmp_path / "sheet.xlsx"
    make_xlsx(xlsx_source)
    parsed = parse_document_in_subprocess(xlsx_source, "XLSX", timeout_seconds=30)
    text = parsed["text"]
    assert isinstance(text, str)
    assert "林同学" in text
    metadata = parsed["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["sheet_count"] == 1


def test_xlsx_html_preview_selects_sheet_and_reuses_cache(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "grades.xlsx"
    make_xlsx(source)
    executable = tmp_path / "soffice.exe"
    executable.write_bytes(b"fake executable")
    settings = Settings(data_dir=tmp_path / "data", libreoffice_path=executable)
    calls = 0

    class FakeJob:
        @classmethod
        def create(cls, _memory_limit: int):
            return cls()

        def assign(self, _process: object) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeProcess:
        returncode = 0

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            nonlocal calls
            calls += 1
            assert command[command.index("--convert-to") + 1] == "html"
            workdir = Path(command[command.index("--outdir") + 1])
            converted = workdir / "source.xlsx"
            with zipfile.ZipFile(converted) as archive:
                workbook = archive.read("xl/workbook.xml").decode("utf-8")
                assert 'activeTab="0"' in workbook
            (workdir / "source.html").write_text(
                '<html><head><style>table{border-collapse:collapse}</style></head>'
                "<body><table><tr><td>林同学</td></tr></table></body></html>",
                encoding="utf-8",
            )

        def wait(self, timeout: int) -> int:
            assert timeout == settings.pptx_preview_timeout_seconds
            return 0

    monkeypatch.setattr(pptx_preview, "ManagedJobObject", FakeJob)
    monkeypatch.setattr(pptx_preview.subprocess, "Popen", FakeProcess)
    first = get_or_create_xlsx_sheet_preview(source, "d" * 64, 0, settings)
    second = get_or_create_xlsx_sheet_preview(source, "d" * 64, 0, settings)

    assert first == second
    rendered_html = first.read_text(encoding="utf-8")
    assert "林同学" in rendered_html
    assert 'id="mindmate-xlsx-table-style"' in rendered_html
    assert "border:1px solid #8797a0!important" in rendered_html
    assert calls == 1


def test_xlsx_html_preview_rejects_active_markup(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "grades.xlsx"
    make_xlsx(source)
    executable = tmp_path / "soffice.exe"
    executable.write_bytes(b"fake executable")
    settings = Settings(data_dir=tmp_path / "data", libreoffice_path=executable)

    class FakeJob:
        @classmethod
        def create(cls, _memory_limit: int):
            return cls()

        def assign(self, _process: object) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeProcess:
        returncode = 0

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            workdir = Path(command[command.index("--outdir") + 1])
            (workdir / "source.html").write_text(
                "<html><body><script>alert(1)</script></body></html>", encoding="utf-8"
            )

        def wait(self, timeout: int) -> int:
            return 0

    monkeypatch.setattr(pptx_preview, "ManagedJobObject", FakeJob)
    monkeypatch.setattr(pptx_preview.subprocess, "Popen", FakeProcess)

    with pytest.raises(pptx_preview.OfficePreviewError, match="安全"):
        get_or_create_xlsx_sheet_preview(source, "e" * 64, 0, settings)


def test_xlsx_preview_route_returns_sandboxed_html_for_parsed_sheet(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(data_dir=tmp_path / "app", env="test")
    html_path = tmp_path / "sheet-preview.html"
    html_path.write_text("<html><body><table><tr><td>fixture</td></tr></table></body></html>", encoding="utf-8")
    monkeypatch.setattr(
        files_api,
        "get_or_create_xlsx_sheet_preview",
        lambda _source, _content_hash, _index, _settings: html_path,
    )

    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        headers = {"Origin": "http://127.0.0.1:5173"}
        assert client.post("/api/v1/system/session", headers=headers).status_code == 200
        source = tmp_path / "sheet.xlsx"
        make_xlsx(source)
        imported = client.post(
            "/api/v1/file-imports",
            headers={**headers, "Idempotency-Key": "xlsx-html-route"},
            files={
                "files": (
                    source.name,
                    source.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        import_id = imported.json()["import_id"]
        task: dict[str, Any] = {}
        for _ in range(200):
            task = client.get(f"/api/v1/file-imports/{import_id}").json()
            if task["status"] in {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED"}:
                break
            time.sleep(0.02)
        file_id = task["items"][0]["file_id"]
        response = client.get(f"/api/v1/files/{file_id}/xlsx-preview/0")

    assert task["items"][0]["parse_status"] == "PARSED"
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "sandbox" in response.headers["content-security-policy"]
    assert b"<table>" in response.content
