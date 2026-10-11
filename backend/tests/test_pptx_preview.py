from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfWriter

from mindmate.application import pptx_preview
from mindmate.application.pptx_preview import OfficePreviewError
from mindmate.config import Settings


def make_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FakeJob:
    def __init__(self, _memory_limit: int) -> None:
        self.closed = False

    @classmethod
    def create(cls, memory_limit: int) -> FakeJob:
        return cls(memory_limit)

    def assign(self, _process: object) -> None:
        return None

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("document_type", "extension", "export_filter"),
    [
        ("DOCX", ".docx", "writer_pdf_Export"),
        ("PPT", ".ppt", "impress_pdf_Export"),
        ("PPTX", ".pptx", "impress_pdf_Export"),
        ("XLSX", ".xlsx", "calc_pdf_Export"),
    ],
)
def test_office_preview_uses_matching_filter_and_cache(
    tmp_path: Path, monkeypatch, document_type: str, extension: str, export_filter: str
) -> None:
    source = tmp_path / f"slides{extension}"
    source.write_bytes(b"pptx fixture")
    executable = tmp_path / "soffice.exe"
    executable.write_bytes(b"fake executable")
    settings = Settings(data_dir=tmp_path / "data", libreoffice_path=executable)
    calls = 0

    class FakeProcess:
        returncode = 0

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            nonlocal calls
            calls += 1
            assert f"pdf:{export_filter}" in command
            output_dir = Path(command[command.index("--outdir") + 1])
            (output_dir / "source.pdf").write_bytes(make_pdf())

        def wait(self, timeout: int) -> int:
            assert timeout == settings.pptx_preview_timeout_seconds
            return 0

    monkeypatch.setattr(pptx_preview, "ManagedJobObject", FakeJob)
    monkeypatch.setattr(pptx_preview.subprocess, "Popen", FakeProcess)

    first_path, first_pages, first_cache_hit = pptx_preview.get_or_create_office_preview(
        source, "a" * 64, document_type, settings
    )
    second_path, second_pages, second_cache_hit = pptx_preview.get_or_create_office_preview(
        source, "a" * 64, document_type, settings
    )

    assert first_path == second_path
    assert first_path.is_file()
    assert first_pages == second_pages == 1
    assert first_cache_hit is False
    assert second_cache_hit is True
    assert calls == 1


def test_pptx_preview_timeout_is_reported_and_child_is_killed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"pptx fixture")
    executable = tmp_path / "soffice.exe"
    executable.write_bytes(b"fake executable")
    settings = Settings(data_dir=tmp_path / "data", libreoffice_path=executable)
    killed: list[bool] = []

    class FakeProcess:
        def __init__(self, _command: list[str], **_kwargs: object) -> None:
            self.wait_calls = 0

        def wait(self, timeout: int | None = None) -> int:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired("soffice", 0 if timeout is None else timeout)
            return -9

        def kill(self) -> None:
            killed.append(True)

    monkeypatch.setattr(pptx_preview, "ManagedJobObject", FakeJob)
    monkeypatch.setattr(pptx_preview.subprocess, "Popen", FakeProcess)

    with pytest.raises(OfficePreviewError) as error:
        pptx_preview.get_or_create_office_preview(source, "b" * 64, "PPTX", settings)

    assert error.value.code == "OFFICE_RENDER_TIMEOUT"
    assert killed == [True]


def test_pptx_preview_requires_valid_pdf_output(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"pptx fixture")
    executable = tmp_path / "soffice.exe"
    executable.write_bytes(b"fake executable")
    settings = Settings(data_dir=tmp_path / "data", libreoffice_path=executable)

    class FakeProcess:
        returncode = 0

        def __init__(self, command: list[str], **_kwargs: object) -> None:
            output_dir = Path(command[command.index("--outdir") + 1])
            (output_dir / "source.pdf").write_bytes(b"not a PDF")

        def wait(self, timeout: int) -> int:
            return 0

    monkeypatch.setattr(pptx_preview, "ManagedJobObject", FakeJob)
    monkeypatch.setattr(pptx_preview.subprocess, "Popen", FakeProcess)

    with pytest.raises(OfficePreviewError) as error:
        pptx_preview.get_or_create_office_preview(source, "c" * 64, "PPTX", settings)

    assert error.value.code == "OFFICE_RENDER_OUTPUT_INVALID"
