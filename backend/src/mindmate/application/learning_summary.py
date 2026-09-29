"""Build and persist deterministic learning-session summary snapshots.

The snapshot is intentionally local and evidence based.  It never calls a
Provider and it keeps the review plan explicit when the full spaced-review
model is not available in the current V1 runtime.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from mindmate.application.citations import citation_payload, list_feedback_citations
from mindmate.infrastructure.models import (
    FileRecord,
    KnowledgeBase,
    KnowledgePoint,
    LearningAttempt,
    LearningFeedback,
    LearningQuestion,
    LearningScope,
    LearningScopeFile,
    LearningSession,
    LearningSessionSummary,
    new_id,
)

SUMMARY_VERSION = 1
REVIEW_PLAN_NOT_ESTABLISHED = "未建立复习安排"


def build_learning_summary(
    session: Session,
    record: LearningSession,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a stable JSON-safe snapshot from persisted learning facts."""

    timestamp = generated_at or record.completed_at or record.updated_at or record.created_at
    questions = list(
        session.scalars(
            select(LearningQuestion)
            .where(LearningQuestion.learning_session_id == record.learning_session_id)
            .order_by(LearningQuestion.sequence_number)
        )
    )
    attempts = list(
        session.scalars(
            select(LearningAttempt)
            .where(LearningAttempt.learning_session_id == record.learning_session_id)
            .order_by(LearningAttempt.submitted_at, LearningAttempt.attempt_number)
        )
    )
    feedback_by_attempt: dict[str, LearningFeedback] = {}
    for attempt in attempts:
        feedback = session.scalar(
            select(LearningFeedback).where(LearningFeedback.attempt_id == attempt.attempt_id)
        )
        if feedback is not None:
            feedback_by_attempt[attempt.attempt_id] = feedback

    result_counts: Counter[str] = Counter()
    hints_by_level: Counter[str] = Counter()
    retry_count = 0
    for attempt in attempts:
        result = feedback_by_attempt.get(attempt.attempt_id)
        if result is not None:
            result_counts[result.result.upper()] += 1
        if attempt.status.upper() == "SKIPPED":
            result_counts["SKIPPED"] += 1
        if attempt.hint_level_used > 0:
            hints_by_level[str(attempt.hint_level_used)] += 1
        retry_count += max(attempt.attempt_number - 1, 0)

    completed_count = len(attempts)
    partial_count = result_counts["PARTIAL"]
    correct_count = result_counts["CORRECT"]
    incorrect_count = result_counts["INCORRECT"]
    skipped_count = result_counts["SKIPPED"]
    unjudged_count = sum(
        count
        for result, count in result_counts.items()
        if result not in {"CORRECT", "PARTIAL", "INCORRECT", "SKIPPED"}
    )
    unanswered_count = max(len(questions) - completed_count, 0)

    point_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"question_count": 0, "results": Counter()}
    )
    question_by_id = {question.question_id: question for question in questions}
    for attempt in attempts:
        question = question_by_id.get(attempt.question_id)
        if question is None:
            continue
        stats = point_stats[question.knowledge_point_id]
        stats["question_count"] += 1
        feedback = feedback_by_attempt.get(attempt.attempt_id)
        if feedback is None:
            stats["results"]["NO_FEEDBACK"] += 1
        else:
            stats["results"][feedback.result.upper()] += 1

    knowledge_points: list[dict[str, Any]] = []
    seen_points: set[str] = set()
    for question in questions:
        point_id = question.knowledge_point_id
        if point_id in seen_points:
            continue
        seen_points.add(point_id)
        point = session.get(KnowledgePoint, point_id)
        stats = point_stats.get(point_id, {"question_count": 0, "results": Counter()})
        results = stats["results"]
        if not results:
            status = "暂无反馈"
        elif results["INCORRECT"] or results["PARTIAL"] or results["NO_FEEDBACK"]:
            status = "需要复习"
        else:
            status = "本次正确"
        knowledge_points.append(
            {
                "knowledge_point_id": point_id,
                "title": point.canonical_title if point is not None else "暂无数据",
                "question_count": int(stats["question_count"]),
                "result_counts": dict(sorted(results.items())),
                "status": status,
            }
        )

    citations: list[dict[str, Any]] = []
    seen_citations: set[str] = set()
    for question in questions:
        for attempt in [item for item in attempts if item.question_id == question.question_id]:
            feedback = feedback_by_attempt.get(attempt.attempt_id)
            if feedback is None:
                continue
            for citation in list_feedback_citations(session, feedback.feedback_id):
                if citation.citation_id in seen_citations:
                    continue
                seen_citations.add(citation.citation_id)
                payload = citation_payload(session, citation)
                citations.append(
                    {
                        "citation_id": citation.citation_id,
                        "question_id": question.question_id,
                        "feedback_id": feedback.feedback_id,
                        "display_number": citation.display_number,
                        "file_name": payload["file_name"],
                        "file_id": payload["file_id"],
                        "chunk_id": payload["chunk_id"],
                        "line_start": payload["line_start"],
                        "line_end": payload["line_end"],
                        "page_start": payload["page_start"],
                        "page_end": payload["page_end"],
                        "excerpt": payload["excerpt"],
                        "source_status": payload["source_status"],
                        "can_open_source": payload["can_open_source"],
                    }
                )
                if len(citations) >= 8:
                    break
            if len(citations) >= 8:
                break
        if len(citations) >= 8:
            break

    scope = session.scalar(
        select(LearningScope).where(
            LearningScope.learning_session_id == record.learning_session_id
        )
    )
    knowledge_base = session.get(KnowledgeBase, record.knowledge_base_id)
    file_ids: list[str] = []
    files: list[dict[str, Any]] = []
    if scope is not None:
        file_ids = list(
            session.scalars(
                select(LearningScopeFile.file_id)
                .where(LearningScopeFile.learning_scope_id == scope.learning_scope_id)
                .order_by(LearningScopeFile.file_id)
            )
        )
        for file_id in file_ids:
            file = session.get(FileRecord, file_id)
            files.append(
                {
                    "file_id": file_id,
                    "file_name": file.display_name if file is not None else "暂无数据",
                    "source_status": (
                        "SOURCE_IN_TRASH"
                        if file is not None and file.deleted_at is not None
                        else "AVAILABLE"
                        if file is not None
                        else "SOURCE_DELETED"
                    ),
                }
            )

    scope_payload = {
        "knowledge_base_id": record.knowledge_base_id,
        "knowledge_base_name": knowledge_base.name if knowledge_base is not None else "暂无数据",
        "index_version_id": scope.index_version_id if scope is not None else None,
        "source_set_hash": scope.source_set_hash if scope is not None else None,
        "file_ids": file_ids,
        "files": files,
    }
    needs_review = partial_count + incorrect_count + skipped_count + unjudged_count
    if completed_count == 0:
        next_step = "暂无已提交作答，未形成可确认学习信号。"
    elif needs_review:
        next_step = "建议从需要复习的知识点、题目记录和关键引用开始复习。"
    else:
        next_step = "本次作答记录已保存；可在后续复习安排建立后再次巩固。"

    knowledge_text = "、".join(
        item["title"] for item in knowledge_points if item["title"] != "暂无数据"
    )
    summary_text = (
        f"{record.topic} 学习总结：完成 {completed_count}/{record.target_question_count} 题；"
        f"正确 {correct_count}，部分正确 {partial_count}，错误 {incorrect_count}，"
        f"跳过 {skipped_count}，无法判定 {unjudged_count}。"
        + (f"知识点：{knowledge_text}。" if knowledge_text else "")
        + f"{next_step}"
    )
    return {
        "summary_version": SUMMARY_VERSION,
        "snapshot_origin": "local_rules",
        "summary_text": summary_text,
        "topic": record.topic,
        "goal_text": record.goal_text,
        "goal_type": record.goal_type,
        "scope": scope_payload,
        "started_at": (record.started_at or record.created_at).isoformat()
        if (record.started_at or record.created_at)
        else None,
        "ended_at": record.completed_at.isoformat() if record.completed_at else None,
        "end_reason": record.end_reason,
        "planned_question_count": record.target_question_count,
        "completed_question_count": completed_count,
        "correct_count": correct_count,
        "partial_count": partial_count,
        "incorrect_count": incorrect_count,
        "skipped_count": skipped_count,
        "unjudged_count": unjudged_count,
        "unanswered_count": unanswered_count,
        "hints_used": sum(hints_by_level.values()),
        "hints_by_level": dict(sorted(hints_by_level.items())),
        "retry_count": retry_count,
        "knowledge_points": knowledge_points,
        "citations": citations,
        "review_plan": {
            "status": "NOT_ESTABLISHED",
            "intervals_days": [],
            "message": REVIEW_PLAN_NOT_ESTABLISHED,
        },
        "next_step": next_step,
        "generated_at": timestamp.isoformat(),
    }


def ensure_learning_summary(
    session: Session,
    record: LearningSession,
    *,
    generated_at: datetime | None = None,
) -> LearningSessionSummary | None:
    """Insert the immutable first snapshot, safely replaying concurrent calls."""

    if record.status not in {"COMPLETED", "FAILED", "SOURCE_INVALID"}:
        return None
    existing = session.scalar(
        select(LearningSessionSummary).where(
            LearningSessionSummary.learning_session_id == record.learning_session_id
        )
    )
    if existing is not None:
        return existing
    timestamp = generated_at or record.completed_at or record.updated_at or record.created_at
    snapshot = build_learning_summary(session, record, generated_at=generated_at)
    session.execute(
        sqlite_insert(LearningSessionSummary)
        .values(
            summary_id=new_id(),
            learning_session_id=record.learning_session_id,
            summary_version=SUMMARY_VERSION,
            snapshot_json=snapshot,
            created_at=timestamp,
            updated_at=timestamp,
        )
        .on_conflict_do_nothing(index_elements=["learning_session_id"])
    )
    return session.scalar(
        select(LearningSessionSummary).where(
            LearningSessionSummary.learning_session_id == record.learning_session_id
        )
    )


def summary_snapshot(
    session: Session,
    record: LearningSession,
) -> dict[str, Any] | None:
    summary = ensure_learning_summary(session, record)
    return None if summary is None else dict(summary.snapshot_json)


__all__ = [
    "REVIEW_PLAN_NOT_ESTABLISHED",
    "SUMMARY_VERSION",
    "build_learning_summary",
    "ensure_learning_summary",
    "summary_snapshot",
]
