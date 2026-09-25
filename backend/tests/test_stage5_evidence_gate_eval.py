# pyright: reportMissingImports=false
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_stage5_evidence_gate as evaluation  # noqa: E402


def test_unavailable_is_never_counted_as_a_strict_refusal() -> None:
    with pytest.raises(evaluation.EvaluationError, match="不能计作严格拒答"):
        evaluation._classify(False, "unavailable")


def test_fixed_labels_have_at_least_twenty_core_cases_and_review_is_unlabeled() -> None:
    annotations = evaluation._load_annotations()
    items = annotations["items"]

    assert sum(item["review_status"] == "core" for item in items) >= 20
    assert all(
        item["expected_sufficient"] is None and item["review_reason"]
        for item in items
        if item["review_status"] == "needs_review"
    )
    assert all(
        item["allowed_support_files"]
        for item in items
        if item["review_status"] == "core" and item["expected_sufficient"]
    )


def test_hard_negative_labels_are_independent_and_all_rejecting() -> None:
    hard_negatives = evaluation._load_hard_negatives()
    assert len(hard_negatives["items"]) >= 6
    assert all(
        item["review_status"] == "hard_negative" and item["expected_sufficient"] is False
        for item in hard_negatives["items"]
    )


def test_confusion_summary_excludes_needs_review_and_totals_core_cases() -> None:
    cases = [
        {
            "id": "supported-hit",
            "category": "direct",
            "review_status": "core",
            "actual_status": "supported",
            "actual_result": {"reason_codes": [], "candidates": []},
            "expected_sufficient": True,
            "classification": "true_positive",
            "top8_contains_annotated_evidence": True,
            "supported_without_annotated_evidence": False,
            "cross_scope_candidates": [],
        },
        {
            "id": "false-refusal",
            "category": "direct",
            "review_status": "core",
            "actual_status": "insufficient",
            "actual_result": {"reason_codes": [], "candidates": []},
            "expected_sufficient": True,
            "classification": "false_negative",
            "top8_contains_annotated_evidence": False,
            "supported_without_annotated_evidence": False,
            "cross_scope_candidates": [],
        },
        {
            "id": "correct-refusal",
            "category": "no-answer",
            "review_status": "core",
            "actual_status": "insufficient",
            "actual_result": {"reason_codes": [], "candidates": []},
            "expected_sufficient": False,
            "classification": "true_negative",
            "top8_contains_annotated_evidence": None,
            "supported_without_annotated_evidence": False,
            "cross_scope_candidates": [],
        },
        {
            "id": "ambiguous",
            "category": "ambiguous",
            "review_status": "needs_review",
            "actual_status": "insufficient",
            "actual_result": {"reason_codes": [], "candidates": []},
            "expected_sufficient": None,
            "classification": None,
            "top8_contains_annotated_evidence": None,
            "supported_without_annotated_evidence": False,
            "cross_scope_candidates": [],
        },
    ]

    summary = evaluation._summarize(cases)

    assert summary["core_count"] == 3
    assert summary["needs_review_count"] == 1
    assert summary["confusion_total"] == 3
    assert summary["false_negative_kinds"] == {"annotated_evidence_missing_from_top8": 1}


def test_confusion_summary_counts_independently_labeled_hard_negatives() -> None:
    summary = evaluation._summarize(
        [
            {
                "review_status": "hard_negative",
                "expected_sufficient": False,
                "actual_status": "insufficient",
                "classification": "true_negative",
                "top8_contains_annotated_evidence": None,
                "supported_without_annotated_evidence": False,
                "cross_scope_candidates": [],
                "category": "wrong_numeric_value",
                "actual_result": {"reason_codes": [], "candidates": []},
            }
        ]
    )
    assert summary["core_count"] == 1
    assert summary["confusion_matrix"] == {
        "true_positive": 0,
        "false_negative": 0,
        "false_positive": 0,
        "true_negative": 1,
    }
