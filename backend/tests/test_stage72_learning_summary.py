"""Stage 72: persisted learning summaries and history search locations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete, select

from mindmate.infrastructure.models import (
    FileRecord,
    HistorySearchDocument,
    LearningSessionSummary,
)
from test_stage7_learning_session import _headers
from test_stage8_learning_history import _client, _create, _submit_first_option


def test_completed_session_persists_summary_and_searches_it(tmp_path: Path) -> None:
    client, data = _client(tmp_path)
    try:
        created = _create(client, data.knowledge_base_id, "stage72-summary-complete")
        _submit_first_option(client, created, "stage72-summary-answer")
        session_id = created["learning_session_id"]
        response = client.get(f"/api/v1/learning-sessions/{session_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        summary = payload["summary"]
        assert payload["status"] == "COMPLETED"
        assert summary["summary_version"] == 1
        assert summary["planned_question_count"] == 1
        assert summary["completed_question_count"] == 1
        assert summary["correct_count"] + summary["incorrect_count"] == 1
        assert summary["review_plan"]["message"] == "未建立复习安排"
        assert summary["scope"]["file_ids"] == [data.file_id]
        assert summary["citations"]

        searched = client.get(
            "/api/v1/history/learning-sessions",
            params={"q": "学习总结"},
        )
        assert searched.status_code == 200, searched.text
        item = next(
            item for item in searched.json()["items"] if item["learning_session_id"] == session_id
        )
        assert any(location["section"] == "summary" for location in item["locations"])

        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            stored = session.scalar(
                select(LearningSessionSummary).where(
                    LearningSessionSummary.learning_session_id == session_id
                )
            )
            assert stored is not None
            assert stored.snapshot_json["summary_text"] == summary["summary_text"]
    finally:
        client.__exit__(None, None, None)


def test_manual_end_and_legacy_backfill_are_deterministic(tmp_path: Path) -> None:
    client, data = _client(tmp_path)
    try:
        created = _create(client, data.knowledge_base_id, "stage72-summary-manual")
        session_id = created["learning_session_id"]
        ended = client.post(
            f"/api/v1/learning-sessions/{session_id}/finish",
            headers=_headers("stage72-summary-finish"),
            json={"expected_session_version": created["row_version"]},
        )
        assert ended.status_code == 200, ended.text
        first = ended.json()["summary"]
        assert first["end_reason"] == "USER_ENDED"
        assert first["completed_question_count"] == 0
        assert first["unanswered_count"] == 1

        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            session.execute(
                delete(LearningSessionSummary).where(
                    LearningSessionSummary.learning_session_id == session_id
                )
            )
            session.commit()
        backfilled = client.get(f"/api/v1/learning-sessions/{session_id}")
        assert backfilled.status_code == 200, backfilled.text
        second = backfilled.json()["summary"]
        assert second == first
        with factory() as session:
            rows = list(
                session.scalars(
                    select(LearningSessionSummary).where(
                        LearningSessionSummary.learning_session_id == session_id
                    )
                )
            )
            assert len(rows) == 1
    finally:
        client.__exit__(None, None, None)


def test_summary_citation_tracks_source_trash_and_purge_removes_owned_snapshot(
    tmp_path: Path,
) -> None:
    client, data = _client(tmp_path)
    try:
        created = _create(client, data.knowledge_base_id, "stage72-summary-source")
        _submit_first_option(client, created, "stage72-summary-source-answer")
        session_id = created["learning_session_id"]
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            file_record = session.get(FileRecord, data.file_id)
            assert file_record is not None
            file_record.deleted_at = datetime.now(UTC)
            session.commit()
        current = client.get(f"/api/v1/learning-sessions/{session_id}")
        assert current.status_code == 200, current.text
        citations = current.json()["summary"]["citations"]
        assert citations
        assert citations[0]["can_open_source"] is False
        assert citations[0]["source_status"] != "AVAILABLE"

        listed = client.get("/api/v1/history/learning-sessions").json()["items"]
        row = next(item for item in listed if item["learning_session_id"] == session_id)
        trashed = client.delete(
            f"/api/v1/learning-sessions/{session_id}",
            headers=_headers("stage72-summary-trash"),
            params={"expected_version": row["row_version"]},
        )
        assert trashed.status_code == 200, trashed.text
        restored = client.post(
            f"/api/v1/learning-sessions/{session_id}/restore",
            headers=_headers("stage72-summary-restore"),
            params={"expected_version": trashed.json()["row_version"]},
        )
        assert restored.status_code == 200, restored.text
        trashed_again = client.delete(
            f"/api/v1/learning-sessions/{session_id}",
            headers=_headers("stage72-summary-trash-again"),
            params={"expected_version": restored.json()["row_version"]},
        )
        assert trashed_again.status_code == 200, trashed_again.text
        purged = client.delete(
            f"/api/v1/learning-sessions/{session_id}/permanent",
            headers=_headers("stage72-summary-purge"),
            params={"expected_version": trashed_again.json()["row_version"], "confirmed": "true"},
        )
        assert purged.status_code == 200, purged.text
        with factory() as session:
            assert session.scalar(
                select(LearningSessionSummary).where(
                    LearningSessionSummary.learning_session_id == session_id
                )
            ) is None
            assert not session.scalar(
                select(HistorySearchDocument.document_id).where(
                    HistorySearchDocument.owner_id == session_id
                )
            )
    finally:
        client.__exit__(None, None, None)
