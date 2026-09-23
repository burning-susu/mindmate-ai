from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindmate.application.tasks import create_task
from mindmate.infrastructure.models import ChunkingConfig, IndexVersion

CHUNK_GENERATION_TASK = "INDEX_CHUNK"
# Descriptive aliases keep the task contract readable to callers without
# introducing a second persisted task type.
INDEX_CHUNKING_TASK = CHUNK_GENERATION_TASK
CHUNKING_TASK = CHUNK_GENERATION_TASK


class ChunkingCancelled(Exception):
    pass


def enqueue_index_chunking(
    session: Session,
    index_version_id: str,
    idempotency_key: str,
    *,
    retry_failed: bool = False,
):
    """Queue chunk generation for one already-frozen index version."""
    version = session.get(IndexVersion, index_version_id)
    if version is None:
        raise ValueError("索引版本不存在。")
    config = session.scalar(
        select(ChunkingConfig).where(
            ChunkingConfig.chunking_config_id == version.chunking_config_id
        )
    )
    if config is None:
        raise ValueError("切片配置不存在。")
    return create_task(
        session,
        CHUNK_GENERATION_TASK,
        idempotency_key,
        {
            "schema_version": 1,
            "index_version_id": index_version_id,
            "knowledge_base_id": version.scope_id,
            "chunking_config_id": version.chunking_config_id,
            "chunking_config_fingerprint": config.config_fingerprint,
            "retry_failed": retry_failed,
            "next_ordinal": 0,
            "results": [],
        },
    )


@dataclass(frozen=True)
class SourceUnit:
    text: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    slide: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    source_kind: str | None = None


@dataclass(frozen=True)
class ChunkDraft:
    sequence_number: int
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    slide_number: int | None
    line_start: int | None
    line_end: int | None
    source_kind: str | None
    content: str
    content_hash: str
    length_unit: str
    length_value: int
    token_count: int | None = None


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_SENTENCE_END = set("。！？!?；;\n")


def _as_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _heading_path(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _source_kind(value: object, text: str) -> str:
    if isinstance(value, str) and value.strip():
        normalized = value.strip().upper()
        if normalized in {"TITLE", "HEADING", "PARAGRAPH", "LIST", "TABLE", "CODE"}:
            return normalized
    if _FENCE.match(text):
        return "CODE"
    if "\t" in text or ("|" in text and "\n" in text):
        return "TABLE"
    if _HEADING.match(text.strip()):
        return "HEADING"
    return "PARAGRAPH"


def _location_units(
    text: str,
    locations: object,
    cancel_check: Callable[[], bool] | None = None,
) -> list[SourceUnit]:
    if not isinstance(locations, list):
        return []
    units: list[SourceUnit] = []
    for location in locations:
        if cancel_check is not None and cancel_check():
            raise ChunkingCancelled
        if not isinstance(location, Mapping):
            continue
        start = location.get("start")
        length = location.get("length")
        if not isinstance(start, int) or not isinstance(length, int) or length <= 0:
            continue
        value = text[max(0, start) : max(0, start) + length].strip()
        if not value:
            continue
        line_start = _as_positive_int(location.get("line_start"))
        line_end = _as_positive_int(location.get("line_end"))
        if line_start is None:
            line_start = _as_positive_int(location.get("line"))
        if line_end is None and line_start is not None:
            line_end = line_start
        units.append(
            SourceUnit(
                text=value,
                heading_path=_heading_path(location.get("heading_path")),
                page=_as_positive_int(location.get("page"))
                or _as_positive_int(location.get("page_number")),
                slide=_as_positive_int(location.get("slide"))
                or _as_positive_int(location.get("slide_number")),
                line_start=line_start,
                line_end=line_end,
                source_kind=_source_kind(
                    location.get("block_type") or location.get("type"), value
                ),
            )
        )
    return units


def _flush_fallback(
    units: list[SourceUnit], lines: list[str], start_line: int, end_line: int, kind: str, heading: tuple[str, ...]
) -> None:
    value = "\n".join(lines).strip()
    if value:
        units.append(
            SourceUnit(
                text=value,
                heading_path=heading,
                line_start=start_line,
                line_end=end_line,
                source_kind=kind,
            )
        )


def _fallback_units(
    text: str, cancel_check: Callable[[], bool] | None = None
) -> list[SourceUnit]:
    """Recover paragraph, heading, table, code and line locations for plain parsers."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    units: list[SourceUnit] = []
    heading_stack: list[str] = []
    group: list[str] = []
    start_line = 1
    kind = "PARAGRAPH"
    in_code = False

    def flush(end_line: int) -> None:
        nonlocal group, start_line, kind
        _flush_fallback(units, group, start_line, end_line, kind, tuple(heading_stack))
        group = []
        kind = "PARAGRAPH"

    for number, line in enumerate(lines, start=1):
        if cancel_check is not None and cancel_check():
            raise ChunkingCancelled
        stripped = line.strip()
        fence = _FENCE.match(line)
        if fence:
            if not in_code and group:
                flush(number - 1)
            if not group:
                start_line = number
            group.append(line)
            kind = "CODE"
            in_code = not in_code
            if not in_code:
                flush(number)
            continue
        if in_code:
            group.append(line)
            continue
        heading = _HEADING.match(stripped) if stripped else None
        if heading:
            if group:
                flush(number - 1)
            level = len(heading.group(1))
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading.group(2).strip())
            group = [line]
            start_line = number
            kind = "HEADING"
            continue
        if not stripped:
            if group and kind != "HEADING":
                flush(number - 1)
            continue
        if not group:
            start_line = number
            kind = "TABLE" if "|" in line and "|" in line.rstrip("|") else "PARAGRAPH"
        elif kind == "PARAGRAPH" and "|" in line and "|" in line.rstrip("|"):
            kind = "TABLE"
        elif kind == "HEADING":
            kind = "PARAGRAPH"
        group.append(line)
    if group:
        flush(len(lines))
    return units


def source_units(
    parsed: Mapping[str, Any], cancel_check: Callable[[], bool] | None = None
) -> list[SourceUnit]:
    text = parsed.get("text")
    if not isinstance(text, str) or not text.strip():
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    units = _location_units(normalized, parsed.get("locations"), cancel_check)
    return units or _fallback_units(normalized, cancel_check)


def _natural_cut(value: str, maximum: int) -> int:
    if len(value) <= maximum:
        return len(value)
    lower = max(1, maximum // 2)
    candidates = [index + 1 for index, char in enumerate(value[: maximum + 1]) if char in _SENTENCE_END]
    valid = [candidate for candidate in candidates if candidate >= lower]
    return min(maximum, max(valid)) if valid else maximum


def _split_unit(
    unit: SourceUnit, maximum: int, cancel_check: Callable[[], bool] | None = None
) -> list[SourceUnit]:
    remaining = unit.text.strip()
    pieces: list[SourceUnit] = []
    while remaining:
        if cancel_check is not None and cancel_check():
            raise ChunkingCancelled
        cut = _natural_cut(remaining, maximum)
        value = remaining[:cut].strip()
        if value:
            pieces.append(replace(unit, text=value))
        next_value = remaining[cut:].lstrip()
        if next_value == remaining:
            break
        remaining = next_value
    return pieces


def _joined(units: list[SourceUnit]) -> str:
    return "\n".join(unit.text for unit in units).strip()


def _suffix_unit(units: list[SourceUnit], overlap: int) -> SourceUnit | None:
    value = _joined(units)
    if not value or overlap <= 0:
        return None
    suffix = value[-overlap:]
    last = units[-1]
    return replace(last, text=suffix)


def _draft(units: list[SourceUnit], sequence: int) -> ChunkDraft | None:
    content = _joined(units)
    if not content:
        return None
    pages = [unit.page for unit in units if unit.page is not None]
    lines_start = [unit.line_start for unit in units if unit.line_start is not None]
    lines_end = [unit.line_end for unit in units if unit.line_end is not None]
    slides = [unit.slide for unit in units if unit.slide is not None]
    kinds = {unit.source_kind for unit in units if unit.source_kind}
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return ChunkDraft(
        sequence_number=sequence,
        heading_path=list(units[0].heading_path),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        slide_number=slides[0] if slides and len(set(slides)) == 1 else None,
        line_start=min(lines_start) if lines_start else None,
        line_end=max(lines_end) if lines_end else None,
        source_kind=next(iter(kinds)) if len(kinds) == 1 else ("MIXED" if kinds else None),
        content=content,
        content_hash=digest,
        length_unit="UNICODE_CHARACTER",
        length_value=len(content),
    )


def _can_merge(current: list[SourceUnit], next_unit: SourceUnit) -> bool:
    previous = current[-1]
    if previous.heading_path != next_unit.heading_path:
        return False
    if previous.page != next_unit.page or previous.slide != next_unit.slide:
        return False
    structural = {"CODE", "TABLE"}
    if previous.source_kind in structural or next_unit.source_kind in structural:
        return previous.source_kind == next_unit.source_kind
    return True


def chunk_parsed_document(
    parsed: Mapping[str, Any],
    *,
    target_size: int = 500,
    min_size: int = 250,
    max_size: int = 800,
    overlap_size: int = 80,
    cancel_check: Callable[[], bool] | None = None,
) -> list[ChunkDraft]:
    """Create deterministic, character-counted chunks from one parsed payload."""
    maximum = max(1, max_size)
    target = max(1, min(target_size, maximum))
    minimum = max(1, min(min_size, target))
    overlap = max(0, min(overlap_size, target - 1))
    # Split long structural units near the target so the configured target remains
    # meaningful while max_size still bounds all emitted content.
    atoms: list[SourceUnit] = []
    for unit in source_units(parsed, cancel_check):
        if cancel_check is not None and cancel_check():
            raise ChunkingCancelled
        atoms.extend(_split_unit(unit, target, cancel_check))

    chunks: list[ChunkDraft] = []
    current: list[SourceUnit] = []
    for atom in atoms:
        if cancel_check is not None and cancel_check():
            raise ChunkingCancelled
        if not current:
            current = [atom]
            continue
        if not _can_merge(current, atom):
            draft = _draft(current, len(chunks))
            if draft is not None:
                chunks.append(draft)
            current = [atom]
            continue
        candidate = _joined([*current, atom])
        current_size = len(_joined(current))
        if len(candidate) <= target or (
            current_size < minimum and len(candidate) <= maximum
        ):
            current.append(atom)
            continue
        draft = _draft(current, len(chunks))
        if draft is not None:
            chunks.append(draft)
        # Do not carry prose overlap into a code/table block. This keeps the
        # structural type and its source location truthful at hard boundaries.
        suffix = (
            _suffix_unit(current, overlap)
            if current[-1].source_kind == atom.source_kind
            and _can_merge(current, atom)
            else None
        )
        current = [suffix, atom] if suffix is not None else [atom]
        if len(_joined(current)) > maximum:
            current = [atom]
    draft = _draft(current, len(chunks))
    if draft is not None:
        chunks.append(draft)

    # A short final chunk is intentionally kept with its source context. Repeated
    # text at distinct source locations remains distinct; equal content is not proof
    # that two source spans are the same chunk.
    return [
        replace(draft, sequence_number=index)
        for index, draft in enumerate(chunks)
        if draft.content
    ]


def config_values(config: Any) -> dict[str, int]:
    return {
        "target_size": int(getattr(config, "target_size", 500)),
        "min_size": int(getattr(config, "min_size", 250)),
        "max_size": int(getattr(config, "max_size", 800)),
        "overlap_size": int(getattr(config, "overlap_size", 80)),
    }
