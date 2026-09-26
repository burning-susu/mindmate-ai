"""Deterministic single-choice drafts taken only from approved excerpts.

Excerpts are untrusted data. This module never sends them to a model and never
treats sentences inside them as instructions.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

_FACT = re.compile(
    r"(?P<label>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9]{1,40})"
    r"(?:为|是)\s*(?P<value>\d{1,6})\s*(?P<unit>秒|分钟|天|小时)"
)
_UNIT_VALUE = re.compile(r"(?P<value>\d{1,6})\s*(?P<unit>秒|分钟|天|小时)")
_OFFSETS = (17, 5, 11, 23, 3, 29, 8, 41)
PROMPT_TEMPLATE_VERSION = "learning-demo-fixture-v1"
MOCK_PROVIDER = "mock"
MOCK_MODEL = "learning-demo-fixture-v1"
MOCK_NOTE = "此反馈来自本地 Mock 确定性演示，不是在线模型生成。"


@dataclass(frozen=True, slots=True)
class QuestionDraft:
    prompt_text: str
    knowledge_point_title: str
    options: tuple[tuple[str, str], ...]
    correct_option_id: str
    correct_label: str
    value: int
    unit: str


def draft_single_choice(
    excerpts: list[str], *, source_hash: str
) -> QuestionDraft | None:
    """Return one mutually exclusive question, or None when no unique fact exists."""

    text = _normalize("\n".join(excerpt[:1200] for excerpt in excerpts if excerpt.strip()))
    if not text:
        return None
    values_by_unit: dict[str, set[int]] = {}
    for match in _UNIT_VALUE.finditer(text):
        values_by_unit.setdefault(match.group("unit"), set()).add(int(match.group("value")))
    chosen: tuple[str, int, str] | None = None
    for match in _FACT.finditer(text):
        label = match.group("label")
        value = int(match.group("value"))
        unit = match.group("unit")
        if str(value) in label:
            continue
        if values_by_unit.get(unit) != {value}:
            continue
        chosen = (label, value, unit)
        break
    if chosen is None:
        return None
    label, value, unit = chosen
    distractors: list[int] = []
    occupied = values_by_unit.get(unit, set())
    for offset in _OFFSETS:
        for candidate in (value + offset, value - offset):
            if candidate <= 0 or candidate > 999_999 or candidate in occupied:
                continue
            if candidate in distractors:
                continue
            distractors.append(candidate)
            if len(distractors) == 3:
                break
        if len(distractors) == 3:
            break
    if len(distractors) != 3:
        return None
    labels = [f"{value} {unit}", *[f"{item} {unit}" for item in distractors]]
    if len(set(labels)) != 4:
        return None
    prompt = f"根据当前资料，「{label}」对应的数值是多少{unit}？"
    if str(value) in prompt:
        return None
    ordered = sorted(
        labels,
        key=lambda item: hashlib.sha256(f"{source_hash}:{item}".encode()).hexdigest(),
    )
    options = tuple(
        (f"opt-{hashlib.sha256(item.encode()).hexdigest()[:12]}", item) for item in ordered
    )
    correct_label = f"{value} {unit}"
    correct_option_id = next(
        option_id for option_id, item in options if item == correct_label
    )
    return QuestionDraft(
        prompt_text=prompt,
        knowledge_point_title=label[:80],
        options=options,
        correct_option_id=correct_option_id,
        correct_label=correct_label,
        value=value,
        unit=unit,
    )


def feedback_copy(*, selected_label: str, correct_label: str, correct: bool) -> tuple[str, str, str]:
    """Build distinct correct and incorrect explanations without a canned score line."""

    if correct:
        explanation = (
            f"所选「{selected_label}」与资料记载一致。依据见引用 [1]。{MOCK_NOTE}"
        )
        return explanation, "所选数值与资料记载一致", ""
    explanation = (
        f"所选「{selected_label}」与资料记载不一致。"
        f"资料记载的数值是「{correct_label}」。依据见引用 [1]。{MOCK_NOTE}"
    )
    return explanation, "", "所选数值与资料记载不一致"


def _normalize(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value))
    return collapsed.strip()
