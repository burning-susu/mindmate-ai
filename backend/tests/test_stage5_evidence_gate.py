from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from mindmate.application.evidence_gate import (
    DEFAULT_EVIDENCE_CONFIG,
    INSUFFICIENT_MESSAGE,
    EvidenceCandidateIdentity,
    EvidenceSufficiencyConfig,
    assess_evidence,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    chunk_id: str
    file_id: str
    index_version_id: str
    content: str | None
    file_title: str | None = None
    fts_rank: int | None = 1
    vector_rank: int | None = 1
    vector_distance: float | None = 0.08
    vector_score: float | None = 0.92
    ranking_rank: int | None = 1
    sources: tuple[str, ...] = ("fts", "vector")
    exact_match_bonus: float = 0.0
    ranking_score: float = 0.0
    diversity_adjustment: float = 0.0


def _candidate(
    content: str,
    *,
    chunk_id: str = "chunk-1",
    file_id: str = "file-1",
    file_title: str | None = None,
    fts_rank: int | None = 1,
    vector_rank: int | None = 1,
    vector_similarity: float | None = 0.92,
    candidate_rank: int | None = 1,
) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        file_id=file_id,
        index_version_id="version-building",
        content=content,
        file_title=file_title,
        fts_rank=fts_rank,
        vector_rank=vector_rank,
        vector_distance=(1.0 - vector_similarity if vector_similarity is not None else None),
        vector_score=vector_similarity,
        ranking_rank=candidate_rank,
    )


def test_supports_exact_and_reasonably_rephrased_single_file_evidence() -> None:
    exact = _candidate("向量数据库是一种用于存储和检索向量数据的系统。")
    rewritten = _candidate(
        "向量数据库存储向量，并通过向量空间完成相似内容检索。",
        chunk_id="chunk-rewrite",
    )

    exact_result = assess_evidence([exact], query_text="什么是向量数据库？")
    rewrite_result = assess_evidence([rewritten], query_text="向量数据库怎么存储向量？")

    assert exact_result.status == "supported"
    assert exact_result.question_type == "definition"
    assert exact_result.distinct_source_count == 1
    assert exact_result.candidate_ids[0].chunk_id == "chunk-1"
    assert rewrite_result.status == "supported"
    assert rewrite_result.reason_codes == ("SUPPORTING_CANDIDATE_FOUND",)


def test_high_similarity_does_not_support_a_missing_numeric_answer() -> None:
    candidate = _candidate(
        "资料会按照安全要求保存，索引构建完成后才允许检索。",
        file_title="资料保存期限是多少天",
        vector_similarity=0.99,
    )
    candidate = replace(candidate, exact_match_bonus=10.0, ranking_score=10.0)

    result = assess_evidence([candidate], query_text="资料保存期限是多少天？")

    assert result.status == "insufficient"
    assert "NUMERIC_ANSWER_VALUE_NOT_FOUND" in result.reason_codes
    assert result.local_message == INSUFFICIENT_MESSAGE
    assert result.candidate_ids


def test_short_terms_title_only_and_missing_identifier_are_not_support() -> None:
    title_only = _candidate(
        "后台任务根据状态领取并保存检查点。",
        file_title="向量数据库",
    )
    title_result = assess_evidence([title_only], query_text="什么是向量数据库？")
    short_result = assess_evidence([_candidate("AI 是一个短缩写。")], query_text="AI")
    wrong_identifier = _candidate("DEC-RAG-007 规定知识库候选数。")
    identifier_result = assess_evidence(
        [wrong_identifier], query_text="DEC-RAG-008 证据不足规则是什么？"
    )

    assert title_result.status == "insufficient"
    assert "TITLE_ONLY_MATCH" in title_result.reason_codes
    assert short_result.status == "insufficient"
    assert "QUERY_ANCHORS_INSUFFICIENT" in short_result.reason_codes
    assert identifier_result.status == "insufficient"
    assert "QUERY_IDENTIFIER_NOT_IN_BODY" in identifier_result.signals[0].reason_codes


def test_weak_or_unverified_vector_signal_never_passes_the_gate() -> None:
    weak = _candidate(
        "向量数据库存储向量数据。",
        vector_similarity=0.45,
    )
    unknown = replace(weak, vector_distance=None, vector_score=None)

    weak_result = assess_evidence([weak], query_text="什么是向量数据库？")
    unknown_result = assess_evidence([unknown], query_text="什么是向量数据库？")

    assert weak_result.status == "insufficient"
    assert "VECTOR_SIMILARITY_BELOW_THRESHOLD" in weak_result.reason_codes
    assert unknown_result.status == "insufficient"
    assert "VECTOR_SIMILARITY_UNVERIFIED" in unknown_result.signals[0].reason_codes


def test_verified_fts_body_evidence_can_pass_below_default_vector_threshold() -> None:
    result = assess_evidence(
        [_candidate("向量数据库存储向量数据。", vector_similarity=0.78)],
        query_text="什么是向量数据库？",
    )

    assert result.status == "supported"
    assert "FTS_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD" in result.signals[0].reason_codes


def test_numeric_claim_requires_the_queried_value_and_unit() -> None:
    wrong_value = _candidate("普通 API 请求超时时间为 30 秒。", vector_similarity=0.92)
    wrong_result = assess_evidence(
        [wrong_value], query_text="普通 API 请求超时上限是 29 秒吗？"
    )
    right_result = assess_evidence(
        [wrong_value], query_text="普通 API 请求超时上限是多少秒？"
    )

    assert wrong_result.status == "insufficient"
    assert "QUERY_NUMERIC_VALUE_NOT_FOUND" in wrong_result.reason_codes
    assert right_result.status == "supported"


def test_negative_claim_cannot_be_supported_by_a_positive_fact() -> None:
    result = assess_evidence(
        [_candidate("示例模块的审计记录保留期限为 12 天。")],
        query_text="示例模块的审计记录不保留 12 天，对吗？",
    )

    assert result.status == "insufficient"
    assert "QUERY_CLAIM_CONTRADICTED" in result.signals[0].reason_codes


def test_composite_question_requires_each_clause_in_the_evidence() -> None:
    full = _candidate(
        "普通 API 查询时限为 30 秒。后台任务不使用这个请求超时值。"
    )
    partial = _candidate("普通 API 查询时限为 30 秒。")
    question = "普通 API 查询时限是多少秒，以及后台任务是否共用该时限？"

    assert assess_evidence([full], query_text=question).status == "supported"
    partial_result = assess_evidence([partial], query_text=question)
    assert partial_result.status == "insufficient"
    assert "COMPOSITE_OR_OPEN_LIST_QUESTION" in partial_result.reason_codes


def test_vector_only_semantic_path_requires_a_verified_floor() -> None:
    candidate = replace(
        _candidate(
            "演练系统 API 单次请求超时时间为 47 秒。这个数值只属于独立演练环境。",
            vector_similarity=0.601,
        ),
        fts_rank=None,
        sources=("vector",),
    )
    result = assess_evidence(
        [candidate], query_text="演练环境的一般 API 调用上限是多少秒？"
    )

    assert result.status == "supported"
    assert "SEMANTIC_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD" in result.signals[0].reason_codes


def test_composite_questions_and_conflicting_sources_fail_closed() -> None:
    partial = _candidate("向量数据库存储向量并支持相似检索。")
    composite = assess_evidence(
        [partial], query_text="向量数据库如何存储向量？并且它的限制是什么？"
    )
    conflict = assess_evidence(
        [
            _candidate("资料有效期限为 7 天。", file_id="file-a"),
            _candidate(
                "资料有效期限为 30 天。",
                chunk_id="chunk-2",
                file_id="file-b",
                candidate_rank=2,
            ),
        ],
        query_text="资料有效期限是多少天？",
    )

    assert composite.status == "insufficient"
    assert "COMPOSITE_OR_OPEN_LIST_QUESTION" in composite.reason_codes
    assert conflict.status == "insufficient"
    assert "CONFLICTING_EVIDENCE" in conflict.reason_codes
    assert conflict.distinct_source_count == 2

    polarity_conflict = assess_evidence(
        [
            _candidate("本地索引允许检索，索引状态保持 BUILDING。", file_id="file-c"),
            _candidate(
                "本地索引不允许检索，索引状态保持 BUILDING。",
                chunk_id="chunk-4",
                file_id="file-d",
                candidate_rank=2,
            ),
        ],
        query_text="本地索引是否允许检索？",
    )
    assert polarity_conflict.status == "insufficient"
    assert "CONFLICTING_EVIDENCE" in polarity_conflict.reason_codes


def test_repeated_chunks_do_not_inflate_distinct_source_coverage() -> None:
    config = EvidenceSufficiencyConfig(minimum_distinct_sources=2)
    repeated = [
        _candidate("向量数据库存储向量数据。", chunk_id="chunk-1", file_id="same-file"),
        _candidate(
            "向量数据库存储向量数据。",
            chunk_id="chunk-2",
            file_id="same-file",
            candidate_rank=2,
        ),
    ]

    result = assess_evidence(
        repeated,
        query_text="什么是向量数据库？",
        config=config,
    )

    assert result.status == "insufficient"
    assert result.distinct_source_count == 1
    assert result.candidate_ids == tuple(
        EvidenceCandidateIdentity(item.chunk_id, item.file_id, item.index_version_id)
        for item in repeated
    )


def test_route_failures_are_unavailable_and_never_refusal_copy() -> None:
    candidate = _candidate("向量数据库存储向量数据。")
    failed = assess_evidence(
        [candidate],
        query_text="什么是向量数据库？",
        vector_error="VECTOR_STORE_UNAVAILABLE",
    )
    missing_vector = assess_evidence(
        [candidate],
        query_text="什么是向量数据库？",
        vector_requested=False,
    )

    assert failed.status == "unavailable"
    assert "VECTOR_ERROR:VECTOR_STORE_UNAVAILABLE" in failed.reason_codes
    assert failed.local_message is None
    assert missing_vector.status == "unavailable"
    assert "VECTOR_ROUTE_NOT_REQUESTED" in missing_vector.reason_codes
    assert missing_vector.local_message is None
    assert not hasattr(failed, "citations")


def test_empty_results_return_fixed_safe_message_and_validated_config() -> None:
    empty = assess_evidence([], query_text="什么是向量数据库？")

    assert empty.status == "insufficient"
    assert empty.reason_codes == ("EMPTY_RESULTS",)
    assert empty.local_message == INSUFFICIENT_MESSAGE
    assert empty.suggestions
    assert DEFAULT_EVIDENCE_CONFIG.rules_version == "evidence-gate-v1"
    with pytest.raises(ValueError, match="EVIDENCE_CONFIG_INVALID"):
        EvidenceSufficiencyConfig(min_vector_similarity=1.2)
    with pytest.raises(ValueError, match="EVIDENCE_RULE_VERSION_UNSUPPORTED"):
        EvidenceSufficiencyConfig(rules_version="future-version")
