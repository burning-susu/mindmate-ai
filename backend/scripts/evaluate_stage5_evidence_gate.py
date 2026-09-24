from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import prepare_stage5_fixed_ready as fixed_ready
from fastapi.testclient import TestClient
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
ANNOTATIONS_PATH = REPOSITORY_ROOT / "docs" / "test-data" / "stage5-fixed-ready" / "evidence-gate-v1-queries.json"
REPORT_NAME = "stage5-evidence-gate-v1-report.json"
DEFAULT_EVALUATION_DATA_DIR = fixed_ready.DEFAULT_DATA_DIR.parent / "mindmate-ai-stage5-evidence-gate-v1"
SIMULATED_THRESHOLDS = (0.65, 0.70, 0.75, 0.82, 0.85)
CONFUSION_KEYS = ("true_positive", "false_negative", "false_positive", "true_negative")


class EvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ObservedCandidate:
    chunk_id: str
    file_id: str
    index_version_id: str
    fts_rank: int | None
    vector_rank: int | None
    vector_distance: float | None
    vector_score: float | None
    content: str
    file_title: str
    ranking_rank: int
    sources: tuple[str, ...]


def _load_annotations() -> dict[str, Any]:
    payload = json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("dataset_id") != "stage5-evidence-gate-v1":
        raise EvaluationError("评测标注文件版本或数据集 ID 不匹配。")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) < 20:
        raise EvaluationError("固定评测集少于 20 条。")
    item_ids: set[str] = set()
    core_count = 0
    for item in items:
        if not isinstance(item, dict):
            raise EvaluationError("评测标注项不是对象。")
        item_id = item.get("id")
        if not isinstance(item_id, str) or item_id in item_ids:
            raise EvaluationError(f"评测项 ID 缺失或重复：{item_id}")
        item_ids.add(item_id)
        if item.get("knowledge_base") not in {"primary", "decoy", "evaluation"}:
            raise EvaluationError(f"评测项知识库范围未知：{item_id}")
        review_status = item.get("review_status")
        sufficient = item.get("expected_sufficient")
        if review_status == "core":
            if not isinstance(sufficient, bool):
                raise EvaluationError(f"核心标注缺少人工真值：{item_id}")
            if sufficient and not item.get("allowed_support_files"):
                raise EvaluationError(f"可回答样本缺少允许的支持文件：{item_id}")
            if not sufficient and not item.get("rejection_reason"):
                raise EvaluationError(f"拒答样本缺少人工拒绝理由：{item_id}")
            core_count += 1
        elif review_status == "needs_review":
            if sufficient is not None or not item.get("review_reason"):
                raise EvaluationError(f"needs_review 样本必须保留空真值和复核原因：{item_id}")
        else:
            raise EvaluationError(f"评测项 review_status 无效：{item_id}")
    if core_count < 20:
        raise EvaluationError(f"核心样本少于 20 条：{core_count}")
    return payload


def _empty_confusion() -> dict[str, int]:
    return dict.fromkeys(CONFUSION_KEYS, 0)


def _classify(expected_sufficient: bool, actual_status: str) -> str:
    if actual_status == "unavailable":
        raise EvaluationError("检索返回 unavailable；模型、索引或通道故障不能计作严格拒答。")
    if actual_status not in {"supported", "insufficient"}:
        raise EvaluationError(f"检索状态未知：{actual_status}")
    if expected_sufficient:
        return "true_positive" if actual_status == "supported" else "false_negative"
    return "false_positive" if actual_status == "supported" else "true_negative"


def _add_case_to_summary(summary: dict[str, Any], case: dict[str, Any]) -> None:
    if case["review_status"] != "core":
        summary["needs_review_count"] += 1
        return
    confusion_key = case["classification"]
    summary["confusion_matrix"][confusion_key] += 1
    summary["core_count"] += 1
    if case["expected_sufficient"] and case["top8_contains_annotated_evidence"]:
        summary["answerable_top8_hits"] += 1
    if case["classification"] == "false_negative":
        reason = (
            "evidence_retrieved_but_gate_rejected"
            if case["top8_contains_annotated_evidence"]
            else "annotated_evidence_missing_from_top8"
        )
        summary["false_negative_kinds"][reason] = (
            summary["false_negative_kinds"].get(reason, 0) + 1
        )
    if case["supported_without_annotated_evidence"]:
        summary["supported_without_annotated_evidence_count"] += 1
    summary["cross_scope_candidate_count"] += len(case["cross_scope_candidates"])


def _new_summary() -> dict[str, Any]:
    return {
        "core_count": 0,
        "needs_review_count": 0,
        "confusion_matrix": _empty_confusion(),
        "false_negative_kinds": {},
        "supported_without_annotated_evidence_count": 0,
        "answerable_top8_hits": 0,
        "cross_scope_candidate_count": 0,
    }


def _signal_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        candidate
        for case in cases
        for candidate in case["actual_result"].get("candidates", [])
    ]
    fts_count = sum(candidate.get("fts_rank") is not None for candidate in candidates)
    vector_count = sum(candidate.get("vector_rank") is not None for candidate in candidates)
    return {
        "top8_candidate_count": len(candidates),
        "fts_candidate_count": fts_count,
        "vector_candidate_count": vector_count,
        "dual_channel_candidate_count": sum(
            candidate.get("fts_rank") is not None and candidate.get("vector_rank") is not None
            for candidate in candidates
        ),
        "vector_only_candidate_count": sum(
            candidate.get("fts_rank") is None and candidate.get("vector_rank") is not None
            for candidate in candidates
        ),
        "fts_only_candidate_count": sum(
            candidate.get("fts_rank") is not None and candidate.get("vector_rank") is None
            for candidate in candidates
        ),
        "candidate_rows_without_any_raw_rank": sum(
            candidate.get("fts_rank") is None and candidate.get("vector_rank") is None
            for candidate in candidates
        ),
        "final_rank_valid_count": sum(
            isinstance(candidate.get("rank"), int) and 1 <= candidate["rank"] <= 8
            for candidate in candidates
        ),
        "raw_fts_rank_valid_count": sum(
            candidate.get("fts_rank") is not None
            and isinstance(candidate.get("fts_rank"), int)
            and 1 <= candidate["fts_rank"] <= 30
            for candidate in candidates
        ),
        "raw_vector_rank_valid_count": sum(
            candidate.get("vector_rank") is not None
            and isinstance(candidate.get("vector_rank"), int)
            and 1 <= candidate["vector_rank"] <= 30
            for candidate in candidates
        ),
    }


def _summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _new_summary()
    by_category: dict[str, dict[str, Any]] = defaultdict(_new_summary)
    for case in cases:
        _add_case_to_summary(summary, case)
        _add_case_to_summary(by_category[case["category"]], case)
    summary["false_negative_kinds"] = dict(summary["false_negative_kinds"])
    summary["answerable_top8_evidence_hit_rate"] = (
        summary["answerable_top8_hits"]
        / sum(
            case["expected_sufficient"] is True
            for case in cases
            if case["review_status"] == "core"
        )
        if any(
            case["expected_sufficient"] is True and case["review_status"] == "core"
            for case in cases
        )
        else None
    )
    summary["confusion_total"] = sum(summary["confusion_matrix"].values())
    summary["retrieval_status_counts"] = dict(
        Counter(case["actual_status"] for case in cases)
    )
    summary["reason_code_counts"] = dict(
        Counter(
            reason
            for case in cases
            for reason in case["actual_result"].get("reason_codes", [])
        )
    )
    summary["top8_signal_summary"] = _signal_summary(cases)
    summary["by_category"] = {
        category: {
            **value,
            "false_negative_kinds": dict(value["false_negative_kinds"]),
            "confusion_total": sum(value["confusion_matrix"].values()),
            "top8_signal_summary": _signal_summary(
                [case for case in cases if case["category"] == category]
            ),
        }
        for category, value in sorted(by_category.items())
    }
    if summary["confusion_total"] != summary["core_count"]:
        raise EvaluationError("混淆表总数与核心样本数不一致。")
    return summary


def _model_metadata(app: Any, knowledge_base_id: str) -> dict[str, Any]:
    from mindmate.ai.embeddings.manifest import MODEL_MANIFEST
    from mindmate.infrastructure.models import (
        ChunkingConfig,
        EmbeddingConfig,
        FileRecord,
        IndexVersion,
        KnowledgeBase,
        KnowledgeBaseFile,
    )

    with app.state.session_factory() as session:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None or knowledge_base.active_index_version_id is None:
            raise EvaluationError(f"知识库缺少活动索引：{knowledge_base_id}")
        version = session.get(IndexVersion, knowledge_base.active_index_version_id)
        if version is None or version.status != "READY":
            raise EvaluationError(f"活动索引不是 READY：{knowledge_base_id}")
        embedding = session.get(EmbeddingConfig, version.embedding_config_id)
        chunking = session.get(ChunkingConfig, version.chunking_config_id)
        if embedding is None or chunking is None:
            raise EvaluationError(f"索引配置缺失：{version.index_version_id}")
        members = list(
            session.execute(
                select(FileRecord.file_id, FileRecord.display_name)
                .join(KnowledgeBaseFile, KnowledgeBaseFile.file_id == FileRecord.file_id)
                .where(
                    KnowledgeBaseFile.knowledge_base_id == knowledge_base_id,
                    KnowledgeBaseFile.membership_status == "ACTIVE",
                    KnowledgeBaseFile.index_state == "READY",
                    FileRecord.status == "PARSED",
                    FileRecord.deleted_at.is_(None),
                )
                .order_by(FileRecord.display_name)
            )
        )
        active_members = {str(file_id): str(name) for file_id, name in members}
        return {
            "knowledge_base_id": knowledge_base_id,
            "index_version_id": version.index_version_id,
            "index_status": version.status,
            "chunking_config": {
                "config_version": chunking.config_version,
                "algorithm_id": chunking.algorithm_id,
                "measurement_unit": chunking.measurement_unit,
                "target_size": chunking.target_size,
                "min_size": chunking.min_size,
                "max_size": chunking.max_size,
                "overlap_size": chunking.overlap_size,
                "structure_rules_hash": chunking.structure_rules_hash,
                "config_fingerprint": chunking.config_fingerprint,
            },
            "embedding_config": {
                "config_version": embedding.config_version,
                "provider_type": embedding.provider_type,
                "model_name": embedding.model_name,
                "model_revision": embedding.model_revision,
                "vector_dimension": embedding.vector_dimension,
                "normalization": embedding.normalization,
                "distance_metric": embedding.distance_metric,
                "config_fingerprint": embedding.config_fingerprint,
            },
            "vector_engine": version.vector_engine,
            "vector_engine_version": version.vector_engine_version,
            "active_scope_files": active_members,
            "model_manifest": {
                "base_model_id": MODEL_MANIFEST.base_model_id,
                "base_revision": MODEL_MANIFEST.base_revision,
                "artifact_repository_id": MODEL_MANIFEST.artifact_repository_id,
                "artifact_revision": MODEL_MANIFEST.artifact_revision,
                "license": MODEL_MANIFEST.license,
                "dimension": MODEL_MANIFEST.dimension,
                "fingerprint": MODEL_MANIFEST.fingerprint,
                "file_hashes": {item.path: item.sha256 for item in MODEL_MANIFEST.files},
            },
        }


def _observed_candidates(payload: dict[str, Any]) -> list[ObservedCandidate]:
    result: list[ObservedCandidate] = []
    for item in payload.get("candidates", []):
        sources = tuple(
            source
            for source, rank in (("fts", item.get("fts_rank")), ("vector", item.get("vector_rank")))
            if rank is not None
        )
        result.append(
            ObservedCandidate(
                chunk_id=str(item["chunk_id"]),
                file_id=str(item["file_id"]),
                index_version_id=str(payload["index_version_id"]),
                fts_rank=item.get("fts_rank"),
                vector_rank=item.get("vector_rank"),
                vector_distance=item.get("cosine_distance"),
                vector_score=item.get("cosine_similarity"),
                content=str(item.get("excerpt", "")),
                file_title=str(item.get("file_name", "")),
                ranking_rank=int(item["rank"]),
                sources=sources,
            )
        )
    return result


def _offline_sensitivity(cases: list[dict[str, Any]]) -> dict[str, Any]:
    from mindmate.application.evidence_gate import DEFAULT_EVIDENCE_CONFIG, assess_evidence

    output: dict[str, Any] = {
        "mode": "offline_simulation_on_observed_top8",
        "runtime_configuration_changed": False,
        "thresholds": {},
    }
    for threshold in SIMULATED_THRESHOLDS:
        simulated_cases: list[dict[str, Any]] = []
        config = replace(DEFAULT_EVIDENCE_CONFIG, min_vector_similarity=threshold)
        for case in cases:
            if case["review_status"] != "core":
                continue
            assessment = assess_evidence(
                _observed_candidates(case["actual_result"]),
                query_text=case["question"],
                config=config,
            )
            simulated_cases.append(
                {
                    **case,
                    "actual_status": assessment.status,
                    "classification": _classify(case["expected_sufficient"], assessment.status),
                }
            )
        summary = _summarize(simulated_cases)
        output["thresholds"][str(threshold)] = {
            "confusion_matrix": summary["confusion_matrix"],
            "core_count": summary["core_count"],
            "supported_count": (
                summary["confusion_matrix"]["true_positive"]
                + summary["confusion_matrix"]["false_positive"]
            ),
            "false_negative_kinds": summary["false_negative_kinds"],
        }
    return output


def _result_signature(cases: list[dict[str, Any]]) -> str:
    stable_fields = []
    for case in cases:
        response = case["actual_result"]
        stable_fields.append(
            {
                "id": case["id"],
                "status": response["status"],
                "index_version_id": response["index_version_id"],
                "reason_codes": response["reason_codes"],
                "candidates": response["candidates"],
            }
        )
    canonical = json.dumps(stable_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_cases(
    client: TestClient,
    annotations: dict[str, Any],
    kb_ids: dict[str, str],
    metadata: dict[str, dict[str, Any]],
    repetition: int,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for item in annotations["items"]:
        kb_key = item["knowledge_base"]
        key = f"stage5-eval-{repetition}-{item['id']}"
        response = client.post(
            f"/api/v1/knowledge-bases/{kb_ids[kb_key]}/retrieval-tests",
            headers=fixed_ready._headers(key),
            json={"question": item["question"]},
        )
        result = fixed_ready._request_json(response)
        _validate_candidate_signals(result, item["id"])
        actual_status = result.get("status")
        if not isinstance(actual_status, str):
            raise EvaluationError(f"检索响应缺少状态字段：{item['id']}")
        classification = None
        if item["review_status"] == "core":
            classification = _classify(item["expected_sufficient"], actual_status)
        active_ids = set(metadata[kb_key]["active_scope_files"])
        scope_violations = [
            candidate
            for candidate in result.get("candidates", [])
            if candidate.get("file_id") not in active_ids
        ]
        allowed_files = item.get("allowed_support_files", [])
        evidence_hit = (
            any(candidate.get("file_name") in allowed_files for candidate in result["candidates"])
            if item["expected_sufficient"] is True
            else None
        )
        supported_without_evidence = actual_status == "supported" and not (
            any(candidate.get("file_name") in allowed_files for candidate in result["candidates"])
            if allowed_files
            else False
        )
        cases.append(
            {
                "id": item["id"],
                "category": item["category"],
                "knowledge_base": kb_key,
                "question": item["question"],
                "review_status": item["review_status"],
                "expected_sufficient": item["expected_sufficient"],
                "expected_fact": item["expected_fact"],
                "allowed_support_files": allowed_files,
                "rejection_reason": item["rejection_reason"],
                "review_reason": item.get("review_reason"),
                "actual_status": actual_status,
                "classification": classification,
                "top8_contains_annotated_evidence": evidence_hit,
                "supported_without_annotated_evidence": supported_without_evidence,
                "top8_scope_is_valid": not scope_violations,
                "cross_scope_candidates": scope_violations,
                "actual_result": result,
            }
        )
    if any(not case["top8_scope_is_valid"] for case in cases):
        return cases
    return cases


def _validate_candidate_signals(result: dict[str, Any], item_id: str) -> None:
    candidates = result.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) > 8:
        raise EvaluationError(f"Top 8 候选数量无效：{item_id}")
    for position, candidate in enumerate(candidates, 1):
        final_rank = candidate.get("rank")
        fts_rank = candidate.get("fts_rank")
        vector_rank = candidate.get("vector_rank")
        if not isinstance(final_rank, int) or isinstance(final_rank, bool) or final_rank != position:
            raise EvaluationError(f"最终候选排名无效：{item_id}/{position}/{final_rank}")
        if fts_rank is not None and (
            not isinstance(fts_rank, int) or isinstance(fts_rank, bool) or not 1 <= fts_rank <= 30
        ):
            raise EvaluationError(f"FTS 原始排名无效：{item_id}/{fts_rank}")
        if vector_rank is not None and (
            not isinstance(vector_rank, int)
            or isinstance(vector_rank, bool)
            or not 1 <= vector_rank <= 30
        ):
            raise EvaluationError(f"Vector 原始排名无效：{item_id}/{vector_rank}")
        bm25 = candidate.get("bm25")
        if (fts_rank is None and bm25 is not None) or (
            fts_rank is not None and (not isinstance(bm25, (int, float)) or not math.isfinite(bm25))
        ):
            raise EvaluationError(f"FTS 排名与 BM25 分数不一致：{item_id}/{position}")
        distance = candidate.get("cosine_distance")
        similarity = candidate.get("cosine_similarity")
        distance_value: float | None = None
        similarity_value: float | None = None
        if vector_rank is None:
            if distance is not None or similarity is not None:
                raise EvaluationError(f"Vector 排名与余弦信号不一致：{item_id}/{position}")
        else:
            if not isinstance(distance, (int, float)) or not isinstance(similarity, (int, float)):
                raise EvaluationError(f"Vector 余弦信号缺失：{item_id}/{position}")
            distance_value = float(distance)
            similarity_value = float(similarity)
            if (
                not math.isfinite(distance_value)
                or not math.isfinite(similarity_value)
                or not math.isclose(
                    similarity_value, 1 - distance_value, rel_tol=0, abs_tol=1e-5
                )
            ):
                raise EvaluationError(f"Vector 余弦距离/相似度未通过一致性检查：{item_id}/{position}")
        similarity_consistent = vector_rank is None
        if vector_rank is not None:
            if distance_value is None or similarity_value is None:
                raise EvaluationError(f"Vector 余弦信号缺失：{item_id}/{position}")
            similarity_consistent = math.isclose(
                similarity_value, 1 - distance_value, rel_tol=0, abs_tol=1e-5
            )
        candidate["rank_validity"] = {
            "final_rank": True,
            "fts_rank": fts_rank is None or 1 <= fts_rank <= 30,
            "vector_rank": vector_rank is None or 1 <= vector_rank <= 30,
            "bm25_present_for_fts_hit": (fts_rank is None) == (bm25 is None),
            "vector_similarity_consistent": similarity_consistent,
        }


def _similarity_distribution(cases: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        candidate["cosine_similarity"]
        for case in cases
        for candidate in case["actual_result"].get("candidates", [])
        if isinstance(candidate.get("cosine_similarity"), (int, float))
    ]
    values.sort()
    return {
        "candidate_count": len(values),
        "min": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "max": max(values) if values else None,
        "values_by_case": {
            case["id"]: [
                candidate["cosine_similarity"]
                for candidate in case["actual_result"].get("candidates", [])
                if candidate.get("cosine_similarity") is not None
            ]
            for case in cases
        },
    }


def run(data_dir: Path, model_cache: Path, repetitions: int) -> dict[str, Any]:
    from mindmate.ai.embeddings.model_manager import ModelManager
    from mindmate.application.evidence_gate import DEFAULT_EVIDENCE_CONFIG
    from mindmate.application.hybrid_search import DEFAULT_HYBRID_RANKING_CONFIG
    from mindmate.config import Settings
    from mindmate.main import create_app

    if repetitions < 2 or repetitions > 5:
        raise EvaluationError("复跑次数必须在 2 到 5 之间。")
    annotations = _load_annotations()
    preparation = fixed_ready.run(data_dir, model_cache)
    resolved_data_dir = data_dir.expanduser().resolve()
    model_status = ModelManager(resolved_data_dir / "models").status(offline=True)
    if str(model_status.state) != "READY":
        raise EvaluationError(f"本地模型离线校验失败：{model_status.error_code}")
    kb_ids = {
        key: str(preparation["knowledge_bases"][key]["knowledge_base_id"])
        for key in annotations["knowledge_bases"]
    }
    settings = Settings(data_dir=resolved_data_dir, env="development", provider_mode="mock")
    app = create_app(settings)
    report: dict[str, Any] = {
        "schema_version": 1,
        "dataset_id": annotations["dataset_id"],
        "annotation_source": "docs/test-data/stage5-fixed-ready/evidence-gate-v1-queries.json",
        "annotation_policy": annotations["annotation_policy"],
        "provider_mode": "mock",
        "deepseek_called": False,
        "model_state": str(model_status.state),
        "model_artifact_fingerprint": model_status.artifact_fingerprint,
        "evidence_gate_parameters": asdict(DEFAULT_EVIDENCE_CONFIG),
        "ranking_parameters": asdict(DEFAULT_HYBRID_RANKING_CONFIG),
        "knowledge_bases": {},
        "core_sample_count": sum(item["review_status"] == "core" for item in annotations["items"]),
        "needs_review_count": sum(
            item["review_status"] == "needs_review" for item in annotations["items"]
        ),
        "runs": [],
    }

    started = time.monotonic()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        session = fixed_ready._request_json(
            client.post("/api/v1/system/session", headers={"Origin": fixed_ready.ORIGIN})
        )
        if session.get("status") != "ready":
            raise EvaluationError("无法建立隔离实例本地会话。")
        metadata = {key: _model_metadata(app, kb_id) for key, kb_id in kb_ids.items()}
        for key, values in metadata.items():
            expected_files = set(annotations["knowledge_bases"][key]["expected_scope_files"])
            actual_files = set(values["active_scope_files"].values())
            if expected_files != actual_files:
                raise EvaluationError(
                    f"知识库活动范围与标注不一致：{key}; expected={sorted(expected_files)}; actual={sorted(actual_files)}"
                )
            expected_version = preparation["knowledge_bases"][key]["index_version_id"]
            if values["index_version_id"] != expected_version:
                raise EvaluationError(f"索引版本与 READY 准备报告不一致：{key}")
        report["knowledge_bases"] = metadata
        before_counts = fixed_ready._resource_counts(app)
        run_signatures: list[str] = []
        for repetition in range(1, repetitions + 1):
            cases = _run_cases(client, annotations, kb_ids, metadata, repetition)
            unavailable = [case for case in cases if case["actual_status"] == "unavailable"]
            if unavailable:
                raise EvaluationError(
                    "检索异常不能计为拒答："
                    + json.dumps(
                        [{"id": case["id"], "result": case["actual_result"]} for case in unavailable],
                        ensure_ascii=False,
                    )
                )
            confusion = _summarize(cases)
            run_signatures.append(_result_signature(cases))
            report["runs"].append(
                {
                    "repetition": repetition,
                    "confusion_summary": confusion,
                    "similarity_distribution": _similarity_distribution(cases),
                    "false_negatives": [
                        case for case in cases if case["classification"] == "false_negative"
                    ],
                    "false_positives": [
                        case for case in cases if case["classification"] == "false_positive"
                    ],
                    "supported_without_annotated_evidence": [
                        case for case in cases if case["supported_without_annotated_evidence"]
                    ],
                    "cross_scope_candidates": [
                        case for case in cases if case["cross_scope_candidates"]
                    ],
                    "needs_review_results": [
                        case for case in cases if case["review_status"] == "needs_review"
                    ],
                    "cases": cases,
                }
            )
        after_counts = fixed_ready._resource_counts(app)
        if before_counts != after_counts:
            raise EvaluationError(
                f"只读评测改变了隔离数据资源计数：before={before_counts}; after={after_counts}"
            )
        report["resource_counts_before_queries"] = before_counts
        report["resource_counts_after_queries"] = after_counts
    report["reproducibility"] = {
        "requested_repetitions": repetitions,
        "result_signatures": run_signatures,
        "stable": len(set(run_signatures)) == 1,
        "resource_counts_unchanged": True,
    }
    if not report["reproducibility"]["stable"]:
        raise EvaluationError("同一进程内复跑结果不稳定。")
    first_run_cases = report["runs"][0]["cases"]
    report["offline_threshold_sensitivity"] = _offline_sensitivity(first_run_cases)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["evaluation_status"] = "COMPLETED"
    report_path = resolved_data_dir / REPORT_NAME
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the fixed evidence gate against real local ONNX retrieval results."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_EVALUATION_DATA_DIR)
    parser.add_argument("--model-cache", type=Path, default=fixed_ready.DEFAULT_MODEL_CACHE)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    try:
        report = run(args.data_dir, args.model_cache, args.repeat)
    except Exception as error:
        print(
            json.dumps({"evaluation_status": "FAILED", "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    first = report["runs"][0]
    print(
        json.dumps(
            {
                "evaluation_status": report["evaluation_status"],
                "report": str(args.data_dir / REPORT_NAME),
                "core_sample_count": report["core_sample_count"],
                "needs_review_count": report["needs_review_count"],
                "confusion_matrix": first["confusion_summary"]["confusion_matrix"],
                "result_stable": report["reproducibility"]["stable"],
                "elapsed_seconds": report["elapsed_seconds"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
