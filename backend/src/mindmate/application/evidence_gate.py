from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

EVIDENCE_RULES_VERSION = "evidence-gate-v1"
MAX_EVIDENCE_CANDIDATES = 8
INSUFFICIENT_MESSAGE = "当前选择的资料不足以可靠回答这个问题。请调整问题范围或补充相关资料。"
INSUFFICIENT_SUGGESTIONS = (
    "缩小问题范围，聚焦一个问题。",
    "补充包含所需结论或数值的资料。",
    "确认所选知识库和文件范围。",
)


@dataclass(frozen=True, slots=True)
class EvidenceCandidateIdentity:
    chunk_id: str
    file_id: str
    index_version_id: str


class EvidenceCandidate(Protocol):
    @property
    def chunk_id(self) -> str: ...

    @property
    def file_id(self) -> str: ...

    @property
    def index_version_id(self) -> str: ...

    @property
    def fts_rank(self) -> int | None: ...

    @property
    def vector_rank(self) -> int | None: ...

    @property
    def vector_distance(self) -> float | None: ...

    @property
    def vector_score(self) -> float | None: ...

    @property
    def content(self) -> str | None: ...

    @property
    def file_title(self) -> str | None: ...

    @property
    def ranking_rank(self) -> int | None: ...

    @property
    def sources(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class EvidenceSufficiencyConfig:
    """Conservative local gate parameters; thresholds are not a quality claim."""

    rules_version: str = EVIDENCE_RULES_VERSION
    min_vector_similarity: float = 0.82
    max_candidate_rank: int = 3
    max_original_rank: int = 5
    minimum_anchor_count: int = 2
    minimum_anchor_coverage: float = 0.6
    minimum_semantic_anchor_count: int = 2
    minimum_semantic_anchor_coverage: float = 0.5
    minimum_phrase_characters: int = 5
    minimum_distinct_sources: int = 1
    min_fts_similarity: float = 0.50
    min_semantic_similarity: float = 0.60
    numeric_context_characters: int = 48

    def __post_init__(self) -> None:
        if self.rules_version != EVIDENCE_RULES_VERSION:
            raise ValueError("EVIDENCE_RULE_VERSION_UNSUPPORTED")
        if (
            isinstance(self.min_vector_similarity, bool)
            or not isinstance(self.min_vector_similarity, (int, float))
            or not math.isfinite(self.min_vector_similarity)
            or not -1 <= self.min_vector_similarity <= 1
            or isinstance(self.max_candidate_rank, bool)
            or not isinstance(self.max_candidate_rank, int)
            or not 1 <= self.max_candidate_rank <= MAX_EVIDENCE_CANDIDATES
            or isinstance(self.max_original_rank, bool)
            or not isinstance(self.max_original_rank, int)
            or not 1 <= self.max_original_rank <= MAX_EVIDENCE_CANDIDATES
            or isinstance(self.minimum_anchor_count, bool)
            or not isinstance(self.minimum_anchor_count, int)
            or not 1 <= self.minimum_anchor_count <= 20
            or isinstance(self.minimum_anchor_coverage, bool)
            or not isinstance(self.minimum_anchor_coverage, (int, float))
            or not math.isfinite(self.minimum_anchor_coverage)
            or not 0 < self.minimum_anchor_coverage <= 1
            or isinstance(self.minimum_semantic_anchor_count, bool)
            or not isinstance(self.minimum_semantic_anchor_count, int)
            or not 1 <= self.minimum_semantic_anchor_count <= 20
            or isinstance(self.minimum_semantic_anchor_coverage, bool)
            or not isinstance(self.minimum_semantic_anchor_coverage, (int, float))
            or not math.isfinite(self.minimum_semantic_anchor_coverage)
            or not 0 < self.minimum_semantic_anchor_coverage <= 1
            or isinstance(self.minimum_phrase_characters, bool)
            or not isinstance(self.minimum_phrase_characters, int)
            or not 4 <= self.minimum_phrase_characters <= 128
            or isinstance(self.minimum_distinct_sources, bool)
            or not isinstance(self.minimum_distinct_sources, int)
            or not 1 <= self.minimum_distinct_sources <= MAX_EVIDENCE_CANDIDATES
            or isinstance(self.min_fts_similarity, bool)
            or not isinstance(self.min_fts_similarity, (int, float))
            or not math.isfinite(self.min_fts_similarity)
            or not -1 <= self.min_fts_similarity <= 1
            or isinstance(self.min_semantic_similarity, bool)
            or not isinstance(self.min_semantic_similarity, (int, float))
            or not math.isfinite(self.min_semantic_similarity)
            or not -1 <= self.min_semantic_similarity <= 1
            or isinstance(self.numeric_context_characters, bool)
            or not isinstance(self.numeric_context_characters, int)
            or not 0 <= self.numeric_context_characters <= 256
        ):
            raise ValueError("EVIDENCE_CONFIG_INVALID")


DEFAULT_EVIDENCE_CONFIG = EvidenceSufficiencyConfig()


@dataclass(frozen=True, slots=True)
class EvidenceCandidateSignal:
    identity: EvidenceCandidateIdentity
    candidate_rank: int | None
    fts_rank: int | None
    vector_rank: int | None
    vector_similarity: float | None
    matched_anchors: tuple[str, ...]
    anchor_coverage: float
    exact_body_phrase: bool
    identifier_hits: tuple[str, ...]
    distinct_source_count: int
    supporting: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    status: Literal["supported", "insufficient", "unavailable"]
    rules_version: str
    question_type: str
    reason_codes: tuple[str, ...]
    candidate_ids: tuple[EvidenceCandidateIdentity, ...]
    signals: tuple[EvidenceCandidateSignal, ...]
    distinct_source_count: int
    local_message: str | None = None
    suggestions: tuple[str, ...] = ()


_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9]*(?:[-_][A-Z0-9]+)+|V\d+(?:\.\d+)+|"
    r"\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?)\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(
    r"(?<![a-z0-9_])\d+(?:[.,]\d+)?\s*(?:%|％|毫秒|摄氏度|分钟|小时|秒|天|周|月|年|个|项|条|次|元|度|种|mb|gb|kb)?",
    re.IGNORECASE,
)
_ANSWER_UNITS = (
    "摄氏度",
    "毫秒",
    "分钟",
    "小时",
    "秒",
    "天",
    "周",
    "月",
    "年",
    "个",
    "项",
    "条",
    "次",
    "元",
    "度",
    "种",
    "%",
    "％",
    "mb",
    "gb",
    "kb",
)
_QUESTION_SCAFFOLDING = (
    "请问",
    "请介绍一下",
    "介绍一下",
    "解释一下",
    "说明一下",
    "什么叫",
    "什么是",
    "是什么意思",
    "指的是什么",
    "是否",
    "是什么",
    "如何",
    "怎么",
    "怎样",
    "为什么",
    "主要",
    "请介绍",
    "介绍",
    "解释",
    "说明",
    "定义",
    "含义",
    "对应",
    "具体",
    "什么",
    "多少",
    "几种",
    "几个",
    "哪些",
    "有哪些",
    "用途",
    "功能",
    "作用",
)
_IGNORED_ANCHORS = {
    "么是",
    "是什",
    "什叫",
    "叫什",
    "的什",
    "请问",
    "介绍",
    "解释",
    "说明",
    "定义",
    "含义",
    "如何",
    "怎么",
    "怎样",
    "为什么",
    "以及",
    "并且",
    "同时",
    "分别",
    "哪些",
    "有什么",
    "多少",
    "几个",
    "几种",
}
_COMPOSITE_MARKERS = (
    "分别",
    "各自",
    "同时",
    "并且",
    "以及",
    "另外",
    "还要",
    "比较",
    "对比",
    "区别",
    "差异",
    "异同",
    "所有",
    "全部",
    "列出",
    "列举",
    "有哪些",
    "哪些",
)
_NUMERIC_QUESTION_MARKERS = (
    "多少",
    "几个",
    "几种",
    "几天",
    "几周",
    "几个月",
    "几年",
    "几秒",
    "几分钟",
    "几小时",
    "几条",
    "几项",
    "几次",
    "多大",
    "多长",
    "多久",
    "多高",
    "比例",
    "百分比",
    "哪年",
    "何时",
    "什么时候",
    "日期",
    "期限",
    "阈值",
    "上限",
    "下限",
    "数量",
    "版本号",
)
_NEGATIVE_MARKERS = (
    "不允许",
    "禁止",
    "不支持",
    "不能够",
    "不能",
    "不可以",
    "无法",
    "不可",
    "没有",
    "不应",
    "不是",
)
_POSITIVE_MARKERS = ("允许", "支持", "可以", "能够", "应当", "可以", "是")
_CLAIM_PREDICATES = (
    "保留",
    "使用",
    "支持",
    "允许",
    "发送",
    "定义",
    "属于",
    "共用",
    "说明",
    "包含",
    "接收",
)
_SEMANTIC_STOPWORDS = {
    "一般",
    "普通",
    "单次",
    "请求",
    "查询",
    "超时",
    "时间",
    "时限",
    "多少",
    "几个",
    "几种",
    "多久",
    "多长",
    "上限",
    "下限",
    "调用",
    "超过",
    "最多",
    "是否",
    "以及",
    "并且",
    "同时",
    "分别",
    "这个",
    "该值",
    "什么",
    "哪个",
    "哪些",
}


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    separated = "".join(
        " " if unicodedata.category(character)[0] in {"P", "Z", "S"} else character
        for character in normalized
    )
    return " ".join(separated.split())


def _compact(text: str) -> str:
    return "".join(character for character in _normalize(text) if not character.isspace())


def _question_type(query: str) -> str:
    compact = _compact(query)
    if (
        re.search(r"[?？!！;；\n]", query)
        and len([part for part in re.split(r"[?？!！;；\n]+", query) if part.strip()]) > 1
    ):
        return "composite"
    if any(marker in compact for marker in _COMPOSITE_MARKERS):
        return "composite"
    if any(marker in compact for marker in _NUMERIC_QUESTION_MARKERS):
        return "numeric_fact"
    if _IDENTIFIER_PATTERN.search(unicodedata.normalize("NFKC", query).upper()):
        return "exact_identifier"
    if any(marker in compact for marker in ("什么是", "什么叫", "定义", "含义", "指什么")):
        return "definition"
    return "factual"


def _query_anchors(query: str) -> tuple[str, ...]:
    normalized = _normalize(query)
    for scaffold in _QUESTION_SCAFFOLDING:
        normalized = normalized.replace(scaffold, " ")
    anchors: list[str] = []
    for token in re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", normalized):
        if token[0].isascii():
            if len(token) >= 3 or _IDENTIFIER_PATTERN.fullmatch(token.upper()):
                anchors.append(token)
        else:
            anchors.extend(
                token[index : index + 2]
                for index in range(len(token) - 1)
                if token[index : index + 2] not in _IGNORED_ANCHORS
            )
    return tuple(dict.fromkeys(anchors))


def _semantic_anchors(anchors: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(anchor for anchor in anchors if anchor not in _SEMANTIC_STOPWORDS)
    )


def _numeric_tokens(text: str) -> tuple[tuple[str, str | None], ...]:
    """Extract numbers while excluding the numeric fragments inside identifiers."""
    protected = _IDENTIFIER_PATTERN.sub(" ", unicodedata.normalize("NFKC", text))
    tokens: list[tuple[str, str | None]] = []
    for match in _NUMBER_PATTERN.finditer(protected):
        raw = match.group(0).strip()
        value_match = re.match(r"(\d+(?:[.,]\d+)?)(.*)", raw, re.IGNORECASE)
        if value_match is None:
            continue
        value = value_match.group(1).replace(",", "")
        unit = value_match.group(2).replace(" ", "").casefold() or None
        tokens.append((value, unit))
    return tuple(dict.fromkeys(tokens))


def _requested_units(query: str) -> tuple[str, ...]:
    compact = _compact(query)
    units = [unit.casefold() for unit in _ANSWER_UNITS if unit.casefold() in compact]
    if "几个" in compact:
        units.append("个")
    if "几种" in compact:
        units.append("种")
    return tuple(dict.fromkeys(units))


def _nearby_number_match(
    body: str,
    *,
    anchors: Sequence[str],
    context_characters: int,
    targets: Sequence[tuple[str, str | None]] = (),
    required_units: Sequence[str] = (),
) -> set[tuple[str, str | None]]:
    matches: set[tuple[str, str | None]] = set()
    if not anchors:
        return matches
    for anchor in anchors:
        start = 0
        while (position := body.find(anchor, start)) >= 0:
            left = max(0, position - context_characters)
            right = min(len(body), position + len(anchor) + context_characters)
            for number_match in _NUMBER_PATTERN.finditer(body[left:right]):
                raw = number_match.group(0).strip()
                value_match = re.match(r"(\d+(?:[.,]\d+)?)(.*)", raw, re.IGNORECASE)
                if value_match is None:
                    continue
                token = (
                    value_match.group(1).replace(",", ""),
                    value_match.group(2).replace(" ", "").casefold() or None,
                )
                if required_units and token[1] not in required_units:
                    continue
                if not targets or token in targets:
                    matches.add(token)
            start = position + 1
    return matches


def _has_nearby_number(
    body: str,
    anchors: Sequence[str],
    context_characters: int,
    *,
    required_units: Sequence[str] = (),
) -> bool:
    return bool(
        _nearby_number_match(
            body,
            anchors=anchors,
            context_characters=context_characters,
            required_units=required_units,
        )
    )


def _has_nearby_query_numbers(
    body: str,
    query_numbers: Sequence[tuple[str, str | None]],
    anchors: Sequence[str],
    context_characters: int,
    required_units: Sequence[str],
) -> bool:
    matched = _nearby_number_match(
        body,
        anchors=anchors,
        context_characters=context_characters,
        targets=query_numbers,
        required_units=required_units,
    )
    return set(query_numbers).issubset(matched)


def _negative_claim_predicates(query: str) -> tuple[str, ...]:
    compact = _compact(query)
    return tuple(
        predicate
        for predicate in _CLAIM_PREDICATES
        if any(marker + predicate in compact for marker in ("不", "未", "没", "无"))
    )


def _contains_positive_predicate(body: str, predicate: str) -> bool:
    compact = _compact(body)
    start = 0
    while (position := compact.find(predicate, start)) >= 0:
        prefix = compact[max(0, position - 1) : position]
        if prefix not in {"不", "未", "没", "无"}:
            return True
        start = position + 1
    return False


def _is_negative_definition_only(query: str, body: str) -> bool:
    compact_query = _compact(query)
    compact_body = _compact(body)
    return "定义" in compact_query and "说明" not in compact_query and "不定义" in compact_body


def _composite_clauses(query: str) -> tuple[str, ...]:
    parts = re.split(r"(?:，|,|；|;)??\s*(?:以及|并且|同时|另外|还要)\s*", query)
    cleaned = tuple(part.strip(" \t\r\n?？。") for part in parts if part.strip(" \t\r\n?？。"))
    return cleaned if len(cleaned) >= 2 else ()


def _contains_term(text: str, term: str) -> bool:
    if not term[0].isascii():
        return term in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None


def _verified_vector_similarity(candidate: EvidenceCandidate) -> float | None:
    distance = candidate.vector_distance
    similarity = candidate.vector_score
    if (
        distance is None
        or similarity is None
        or isinstance(distance, bool)
        or isinstance(similarity, bool)
        or not isinstance(distance, (int, float))
        or not isinstance(similarity, (int, float))
        or not math.isfinite(distance)
        or not math.isfinite(similarity)
        or not 0 <= distance <= 2
        or not -1 <= similarity <= 1
        or not math.isclose(similarity, 1.0 - distance, rel_tol=0, abs_tol=1e-5)
    ):
        return None
    return similarity


def _polarity(text: str) -> str | None:
    has_negative = any(marker in text for marker in _NEGATIVE_MARKERS)
    affirmative_text = text
    for marker in _NEGATIVE_MARKERS:
        affirmative_text = affirmative_text.replace(marker, " ")
    has_positive = any(marker in affirmative_text for marker in _POSITIVE_MARKERS)
    if has_negative == has_positive:
        return None
    return "negative" if has_negative else "positive"


def _candidate_signal(
    candidate: EvidenceCandidate,
    *,
    query_text: str,
    question_type: str,
    anchors: tuple[str, ...],
    identifiers: tuple[str, ...],
    config: EvidenceSufficiencyConfig,
) -> EvidenceCandidateSignal:
    normalized_body = _normalize(candidate.content or "")
    compact_body = _compact(candidate.content or "")
    normalized_title = _normalize(candidate.file_title or "")
    query_numbers = _numeric_tokens(query_text)
    required_units = _requested_units(query_text)
    exact_phrase = (
        len(_compact(query_text)) >= config.minimum_phrase_characters
        and _compact(query_text) in compact_body
    )
    matched_anchors = tuple(anchor for anchor in anchors if _contains_term(normalized_body, anchor))
    coverage = len(matched_anchors) / len(anchors) if anchors else 0.0
    identifier_hits = tuple(
        identifier
        for identifier in identifiers
        if _contains_term(normalized_body, _normalize(identifier))
    )
    similarity = _verified_vector_similarity(candidate)
    reasons: list[str] = []

    if candidate.fts_rank is None or "fts" not in candidate.sources:
        reasons.append("FTS_SIGNAL_MISSING")
    if candidate.vector_rank is None or "vector" not in candidate.sources:
        reasons.append("VECTOR_SIGNAL_MISSING")
    if similarity is None:
        reasons.append("VECTOR_SIMILARITY_UNVERIFIED")
    elif similarity < config.min_vector_similarity:
        reasons.append("VECTOR_SIMILARITY_BELOW_THRESHOLD")

    def valid_rank(rank: object, maximum: int = MAX_EVIDENCE_CANDIDATES) -> bool:
        return isinstance(rank, int) and not isinstance(rank, bool) and 1 <= rank <= maximum

    ranks = (candidate.ranking_rank, candidate.fts_rank, candidate.vector_rank)
    if any(rank is not None and not valid_rank(rank) for rank in ranks):
        reasons.append("RANK_UNVERIFIED")
    if not valid_rank(candidate.ranking_rank, config.max_candidate_rank):
        reasons.append("RANK_BELOW_GATE")
    if candidate.fts_rank is not None and not valid_rank(
        candidate.fts_rank, config.max_original_rank
    ):
        reasons.append("RANK_BELOW_GATE")
    if candidate.vector_rank is not None and not valid_rank(
        candidate.vector_rank, config.max_original_rank
    ):
        reasons.append("RANK_BELOW_GATE")
    if not candidate.chunk_id or not candidate.file_id or not candidate.index_version_id:
        reasons.append("CANDIDATE_IDENTITY_INVALID")
    if not anchors or len(anchors) < config.minimum_anchor_count:
        if question_type != "exact_identifier":
            reasons.append("QUERY_ANCHORS_INSUFFICIENT")
    elif (
        len(matched_anchors) < config.minimum_anchor_count
        or coverage < config.minimum_anchor_coverage
    ) and not exact_phrase:
        reasons.append("BODY_ANCHOR_COVERAGE_LOW")
    if identifiers and len(identifier_hits) != len(identifiers):
        reasons.append("QUERY_IDENTIFIER_NOT_IN_BODY")
    if query_numbers and not _has_nearby_query_numbers(
        normalized_body,
        query_numbers,
        anchors,
        config.numeric_context_characters,
        required_units,
    ):
        reasons.append("QUERY_NUMERIC_VALUE_NOT_FOUND")
    elif question_type == "numeric_fact" and not _has_nearby_number(
        normalized_body,
        anchors,
        config.numeric_context_characters,
        required_units=required_units,
    ):
        reasons.append("NUMERIC_ANSWER_VALUE_NOT_FOUND")
    negative_predicates = _negative_claim_predicates(query_text)
    if negative_predicates and any(
        _contains_positive_predicate(candidate.content or "", predicate)
        for predicate in negative_predicates
    ):
        reasons.append("QUERY_CLAIM_CONTRADICTED")
    if _is_negative_definition_only(query_text, candidate.content or ""):
        reasons.append("QUERY_NEGATIVE_FACT_ONLY")
    if (
        not matched_anchors
        and not exact_phrase
        and any(_contains_term(normalized_title, anchor) for anchor in anchors)
    ):
        reasons.append("TITLE_ONLY_MATCH")

    semantic_anchors = _semantic_anchors(anchors)
    semantic_matches = tuple(
        anchor for anchor in semantic_anchors if _contains_term(normalized_body, anchor)
    )
    semantic_coverage = (
        len(semantic_matches) / len(semantic_anchors) if semantic_anchors else 0.0
    )
    has_numeric_block = any(
        reason in reasons
        for reason in ("QUERY_NUMERIC_VALUE_NOT_FOUND", "NUMERIC_ANSWER_VALUE_NOT_FOUND")
    )
    has_unusable_rank = any(reason in reasons for reason in ("RANK_UNVERIFIED", "RANK_BELOW_GATE"))
    lexical_evidence_verified = (
        "fts" in candidate.sources
        and candidate.fts_rank is not None
        and candidate.fts_rank <= config.max_original_rank
        and "vector" in candidate.sources
        and candidate.vector_rank is not None
        and candidate.vector_rank <= config.max_original_rank
        and similarity is not None
        and similarity >= config.min_fts_similarity
        and (exact_phrase or len(matched_anchors) >= config.minimum_anchor_count)
        and not has_numeric_block
        and not has_unusable_rank
    )
    semantic_evidence_verified = (
        "fts" not in candidate.sources
        and "vector" in candidate.sources
        and candidate.vector_rank is not None
        and candidate.vector_rank <= config.max_original_rank
        and similarity is not None
        and similarity >= config.min_semantic_similarity
        and len(semantic_matches) >= config.minimum_semantic_anchor_count
        and semantic_coverage >= config.minimum_semantic_anchor_coverage
        and not has_numeric_block
        and not has_unusable_rank
    )
    low_vector_exception = False
    if similarity is not None and similarity < config.min_vector_similarity:
        if lexical_evidence_verified:
            reasons.append("FTS_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD")
            low_vector_exception = True
        elif semantic_evidence_verified:
            reasons.append("SEMANTIC_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD")
            low_vector_exception = True

    blocking_reasons = {
        "FTS_SIGNAL_MISSING",
        "VECTOR_SIGNAL_MISSING",
        "VECTOR_SIMILARITY_UNVERIFIED",
        "VECTOR_SIMILARITY_BELOW_THRESHOLD",
        "RANK_BELOW_GATE",
        "RANK_UNVERIFIED",
        "CANDIDATE_IDENTITY_INVALID",
        "QUERY_ANCHORS_INSUFFICIENT",
        "BODY_ANCHOR_COVERAGE_LOW",
        "QUERY_IDENTIFIER_NOT_IN_BODY",
        "QUERY_NUMERIC_VALUE_NOT_FOUND",
        "NUMERIC_ANSWER_VALUE_NOT_FOUND",
        "QUERY_CLAIM_CONTRADICTED",
        "QUERY_NEGATIVE_FACT_ONLY",
        "TITLE_ONLY_MATCH",
    }
    if not low_vector_exception:
        blocking_reasons.add("VECTOR_SIMILARITY_BELOW_THRESHOLD")
    else:
        blocking_reasons.discard("VECTOR_SIMILARITY_BELOW_THRESHOLD")
        blocking_reasons.discard("BODY_ANCHOR_COVERAGE_LOW")
        if semantic_evidence_verified:
            blocking_reasons.discard("FTS_SIGNAL_MISSING")
    supporting = not any(reason in blocking_reasons for reason in reasons)
    if supporting:
        reasons.append("CANDIDATE_GATE_PASSED")
    return EvidenceCandidateSignal(
        identity=EvidenceCandidateIdentity(
            candidate.chunk_id, candidate.file_id, candidate.index_version_id
        ),
        candidate_rank=candidate.ranking_rank,
        fts_rank=candidate.fts_rank,
        vector_rank=candidate.vector_rank,
        vector_similarity=similarity,
        matched_anchors=matched_anchors,
        anchor_coverage=coverage,
        exact_body_phrase=exact_phrase,
        identifier_hits=identifier_hits,
        distinct_source_count=0,
        supporting=supporting,
        reason_codes=tuple(reasons),
    )


def _conflicting_values(
    signals: Sequence[EvidenceCandidateSignal],
    candidates: Sequence[EvidenceCandidate],
    question_type: str,
) -> bool:
    eligible = [
        (signal, candidate)
        for signal, candidate in zip(signals, candidates, strict=True)
        if signal.supporting
    ]
    by_file: dict[str, EvidenceCandidate] = {}
    for _, candidate in eligible:
        by_file.setdefault(candidate.file_id, candidate)
    if len(by_file) < 2:
        return False
    if question_type == "numeric_fact":
        values = {
            next(iter(_numeric_tokens(candidate.content or "")), None)
            for candidate in by_file.values()
        }
        values.discard(None)
        return len(values) > 1
    polarities = {_polarity(_normalize(candidate.content or "")) for candidate in by_file.values()}
    polarities.discard(None)
    return polarities == {"negative", "positive"}


def _clause_supported(
    candidate: EvidenceCandidate,
    clause: str,
    *,
    config: EvidenceSufficiencyConfig,
) -> bool:
    """Check one composite sub-question against the same auditable chunk body."""
    normalized_body = _normalize(candidate.content or "")
    compact_body = _compact(candidate.content or "")
    anchors = _query_anchors(clause)
    matched = tuple(anchor for anchor in anchors if _contains_term(normalized_body, anchor))
    exact_phrase = (
        len(_compact(clause)) >= config.minimum_phrase_characters
        and _compact(clause) in compact_body
    )
    identifiers = tuple(
        dict.fromkeys(_IDENTIFIER_PATTERN.findall(unicodedata.normalize("NFKC", clause).upper()))
    )
    if identifiers and not all(
        _contains_term(normalized_body, _normalize(identifier)) for identifier in identifiers
    ):
        return False
    required_units = _requested_units(clause)
    query_numbers = _numeric_tokens(clause)
    if query_numbers and not _has_nearby_query_numbers(
        normalized_body,
        query_numbers,
        anchors,
        config.numeric_context_characters,
        required_units,
    ):
        return False
    if _question_type(clause) == "numeric_fact" and not _has_nearby_number(
        normalized_body,
        anchors,
        config.numeric_context_characters,
        required_units=required_units,
    ):
        return False
    if _is_negative_definition_only(clause, candidate.content or ""):
        return False
    negative_predicates = _negative_claim_predicates(clause)
    if negative_predicates and any(
        _contains_positive_predicate(candidate.content or "", predicate)
        for predicate in negative_predicates
    ):
        return False
    if exact_phrase:
        return True
    return len(matched) >= config.minimum_anchor_count


def _composite_fully_supported(
    candidates: Sequence[EvidenceCandidate],
    signals: Sequence[EvidenceCandidateSignal],
    query_text: str,
    *,
    config: EvidenceSufficiencyConfig,
) -> bool:
    clauses = _composite_clauses(query_text)
    if not clauses:
        return False
    eligible = [
        candidate
        for candidate, signal in zip(candidates, signals, strict=True)
        if signal.supporting
    ]
    return bool(eligible) and all(
        any(_clause_supported(candidate, clause, config=config) for candidate in eligible)
        for clause in clauses
    )


def assess_evidence(
    candidates: Sequence[EvidenceCandidate],
    *,
    query_text: str,
    vector_requested: bool = True,
    fts_error: str | None = None,
    vector_error: str | None = None,
    config: EvidenceSufficiencyConfig = DEFAULT_EVIDENCE_CONFIG,
) -> EvidenceAssessment:
    """Classify ranked candidates for later citation binding; never generates an answer."""
    candidate_ids = tuple(
        EvidenceCandidateIdentity(candidate.chunk_id, candidate.file_id, candidate.index_version_id)
        for candidate in candidates
    )
    question_type = _question_type(query_text)
    if fts_error is not None or vector_error is not None:
        route_reasons = tuple(
            f"{route.upper()}_ERROR:{error}"
            for route, error in (("fts", fts_error), ("vector", vector_error))
            if error is not None
        )
        return EvidenceAssessment(
            status="unavailable",
            rules_version=config.rules_version,
            question_type=question_type,
            reason_codes=("RETRIEVAL_CHANNEL_FAILED", *route_reasons),
            candidate_ids=candidate_ids,
            signals=(),
            distinct_source_count=len({candidate.file_id for candidate in candidates}),
        )
    if not vector_requested:
        return EvidenceAssessment(
            status="unavailable",
            rules_version=config.rules_version,
            question_type=question_type,
            reason_codes=("VECTOR_ROUTE_NOT_REQUESTED",),
            candidate_ids=candidate_ids,
            signals=(),
            distinct_source_count=len({candidate.file_id for candidate in candidates}),
        )
    if not candidates:
        return EvidenceAssessment(
            status="insufficient",
            rules_version=config.rules_version,
            question_type=question_type,
            reason_codes=("EMPTY_RESULTS",),
            candidate_ids=(),
            signals=(),
            distinct_source_count=0,
            local_message=INSUFFICIENT_MESSAGE,
            suggestions=INSUFFICIENT_SUGGESTIONS,
        )
    if len(candidates) > MAX_EVIDENCE_CANDIDATES:
        return EvidenceAssessment(
            status="unavailable",
            rules_version=config.rules_version,
            question_type=question_type,
            reason_codes=("TOP_K_CONTRACT_VIOLATION",),
            candidate_ids=candidate_ids,
            signals=(),
            distinct_source_count=len({candidate.file_id for candidate in candidates}),
        )

    anchors = _query_anchors(query_text)
    identifiers = tuple(
        dict.fromkeys(
            _IDENTIFIER_PATTERN.findall(unicodedata.normalize("NFKC", query_text).upper())
        )
    )
    signals = tuple(
        _candidate_signal(
            candidate,
            query_text=query_text,
            question_type=question_type,
            anchors=anchors,
            identifiers=identifiers,
            config=config,
        )
        for candidate in candidates
    )
    supporting_sources = {
        candidate.file_id
        for candidate, signal in zip(candidates, signals, strict=True)
        if signal.supporting
    }
    signals = tuple(
        replace(signal, distinct_source_count=len(supporting_sources)) for signal in signals
    )
    overall_reasons: list[str] = []
    if question_type == "composite" and not _composite_fully_supported(
        candidates,
        signals,
        query_text,
        config=config,
    ):
        overall_reasons.append("COMPOSITE_OR_OPEN_LIST_QUESTION")
    if not anchors and question_type != "exact_identifier":
        overall_reasons.append("QUERY_ANCHORS_INSUFFICIENT")
    if len(supporting_sources) < config.minimum_distinct_sources and not overall_reasons:
        reason_priority = (
            "QUERY_IDENTIFIER_NOT_IN_BODY",
            "QUERY_NUMERIC_VALUE_NOT_FOUND",
            "NUMERIC_ANSWER_VALUE_NOT_FOUND",
            "QUERY_NEGATIVE_FACT_ONLY",
            "QUERY_CLAIM_CONTRADICTED",
            "QUERY_ANCHORS_INSUFFICIENT",
            "TITLE_ONLY_MATCH",
            "BODY_ANCHOR_COVERAGE_LOW",
            "VECTOR_SIMILARITY_BELOW_THRESHOLD",
        )
        for reason in reason_priority:
            if any(reason in signal.reason_codes for signal in signals):
                overall_reasons.append(reason)
                break
        else:
            overall_reasons.append("NO_CANDIDATE_PASSED_GATE")
    if not overall_reasons and _conflicting_values(signals, candidates, question_type):
        overall_reasons.append("CONFLICTING_EVIDENCE")

    if overall_reasons:
        return EvidenceAssessment(
            status="insufficient",
            rules_version=config.rules_version,
            question_type=question_type,
            reason_codes=tuple(dict.fromkeys(overall_reasons)),
            candidate_ids=candidate_ids,
            signals=signals,
            distinct_source_count=len(supporting_sources),
            local_message=INSUFFICIENT_MESSAGE,
            suggestions=INSUFFICIENT_SUGGESTIONS,
        )
    return EvidenceAssessment(
        status="supported",
        rules_version=config.rules_version,
        question_type=question_type,
        reason_codes=("SUPPORTING_CANDIDATE_FOUND",),
        candidate_ids=candidate_ids,
        signals=signals,
        distinct_source_count=len(supporting_sources),
    )


def unavailable_assessment(
    reason_code: str,
    *,
    query_text: str,
    route: str | None = None,
    config: EvidenceSufficiencyConfig = DEFAULT_EVIDENCE_CONFIG,
) -> EvidenceAssessment:
    reasons = (reason_code,)
    if route:
        reasons = (*reasons, f"ROUTE_{route.upper()}")
    return EvidenceAssessment(
        status="unavailable",
        rules_version=config.rules_version,
        question_type=_question_type(query_text),
        reason_codes=reasons,
        candidate_ids=(),
        signals=(),
        distinct_source_count=0,
    )
