from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MAX_PAGES = 2_000
MAX_TEXT_CHARACTERS = 10_000_000


class ParseFailure(Exception):
    pass


def _append(parts: list[str], locations: list[dict[str, Any]], text: str, **location: Any) -> None:
    value = text.strip()
    if not value:
        return
    current_size = sum(len(part) for part in parts) + max(0, len(parts) - 1)
    if current_size + len(value) > MAX_TEXT_CHARACTERS:
        raise ParseFailure("解析文本超过安全输出上限。")
    start = current_size
    parts.append(value)
    locations.append({"start": start, "length": len(value), **location})


def _parse_pdf(path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise ParseFailure("加密 PDF 不受支持。")
    if len(reader.pages) > MAX_PAGES:
        raise ParseFailure("PDF 页数超过安全上限。")
    parts: list[str] = []
    locations: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        _append(parts, locations, page.extract_text() or "", page=page_number)
    if not parts:
        raise ParseFailure("未检测到可解析文本；V1 不支持扫描 PDF OCR。")
    return {
        "text": "\n".join(parts),
        "metadata": {"page_count": len(reader.pages), "character_count": sum(len(p) for p in parts)},
        "locations": locations,
    }


def _parse_docx(path: Path) -> dict[str, Any]:
    from docx import Document

    document = Document(str(path))
    parts: list[str] = []
    locations: list[dict[str, Any]] = []
    heading_path: list[str] = []
    paragraph_number = 0
    for paragraph in document.paragraphs:
        paragraph_number += 1
        text = paragraph.text.strip()
        style_name = (paragraph.style.name or "") if paragraph.style is not None else ""
        if style_name.startswith("Heading") and text:
            level_text = style_name.removeprefix("Heading").strip()
            level = int(level_text) if level_text.isdigit() else 1
            heading_path = heading_path[: max(0, level - 1)]
            heading_path.append(text)
        _append(
            parts,
            locations,
            text,
            paragraph=paragraph_number,
            heading_path=list(heading_path),
        )
    for table_number, table in enumerate(document.tables, start=1):
        for row_number, row in enumerate(table.rows, start=1):
            _append(
                parts,
                locations,
                "\t".join(cell.text.strip() for cell in row.cells),
                table=table_number,
                row=row_number,
            )
    return {
        "text": "\n".join(parts),
        "metadata": {
            "paragraph_count": paragraph_number,
            "table_count": len(document.tables),
            "character_count": sum(len(p) for p in parts),
        },
        "locations": locations,
    }


def _shape_text(shape: Any) -> list[str]:
    values: list[str] = []
    if getattr(shape, "has_text_frame", False):
        value = str(shape.text).strip()
        if value:
            values.append(value)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            value = "\t".join(cell.text.strip() for cell in row.cells)
            if value.strip():
                values.append(value)
    return values


def _parse_pptx(path: Path) -> dict[str, Any]:
    from pptx import Presentation

    presentation = Presentation(str(path))
    if len(presentation.slides) > MAX_PAGES:
        raise ParseFailure("PPTX 幻灯片数量超过安全上限。")
    parts: list[str] = []
    locations: list[dict[str, Any]] = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        order = 0
        for shape in slide.shapes:
            for value in _shape_text(shape):
                order += 1
                _append(parts, locations, value, slide=slide_number, shape_order=order)
        notes_slide = getattr(slide, "notes_slide", None)
        if notes_slide is not None:
            for shape in notes_slide.notes_text_frame.paragraphs:
                note = shape.text.strip()
                if note:
                    order += 1
                    _append(parts, locations, note, slide=slide_number, note=True, shape_order=order)
    return {
        "text": "\n".join(parts),
        "metadata": {
            "slide_count": len(presentation.slides),
            "character_count": sum(len(p) for p in parts),
        },
        "locations": locations,
    }


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    document_type, source_value, output_value = sys.argv[1:]
    source = Path(source_value).resolve(strict=True)
    output = Path(output_value).resolve()
    parsers = {"PDF": _parse_pdf, "DOCX": _parse_docx, "PPTX": _parse_pptx}
    parser = parsers.get(document_type)
    if parser is None:
        raise ParseFailure("解析类型不受支持。")
    payload = parser(source)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc)[:500], file=sys.stderr)
        raise SystemExit(1) from None
