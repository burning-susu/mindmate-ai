from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, cast

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from mindmate.application.backups import create_backup, verify_backup
from mindmate.application.tasks import (
    cancel_task,
    checkpoint_task,
    claim_next_task,
    claim_task,
    create_task,
    recover_running_tasks,
)
from mindmate.infrastructure.models import BackgroundTask, Base, TaskAttempt, TaskEvent


def test_task_checkpoint_cancel_and_recovery(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}")
    Base.metadata.create_all(
        engine,
        tables=cast(Any, [BackgroundTask.__table__, TaskAttempt.__table__, TaskEvent.__table__]),
    )
    with Session(engine) as session:
        task = create_task(session, "stage3", "task-idempotency", {"step": 0})
        session.commit()
        claimed = claim_task(session, task.task_id, "worker-1")
        assert claimed is not None
        checkpoint_task(session, claimed, "copy", {"step": 1}, progress=20)
        session.commit()
        assert (
            session.scalar(
                select(BackgroundTask.status).where(BackgroundTask.task_id == task.task_id)
            )
            == "RUNNING"
        )
        assert recover_running_tasks(session) == 1
        session.commit()
        assert (
            session.scalar(
                select(BackgroundTask.status).where(BackgroundTask.task_id == task.task_id)
            )
            == "INTERRUPTED"
        )
        cancel_task(session, claimed)
        session.commit()
        assert (
            session.scalar(
                select(BackgroundTask.status).where(BackgroundTask.task_id == task.task_id)
            )
            == "CANCELLED"
        )


def test_workers_only_claim_registered_task_types(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'task-types.db').as_posix()}")
    Base.metadata.create_all(
        engine,
        tables=cast(Any, [BackgroundTask.__table__, TaskAttempt.__table__, TaskEvent.__table__]),
    )
    with Session(engine) as session:
        create_task(session, "FILE_IMPORT", "parse-only", {"items": []})
        knowledge = create_task(
            session,
            "KNOWLEDGE_MEMBERSHIP_ADD",
            "knowledge-only",
            {"items": []},
        )
        session.commit()

        claimed = claim_next_task(
            session,
            "knowledge-worker",
            task_types={"KNOWLEDGE_MEMBERSHIP_ADD"},
        )
        assert claimed is not None
        assert claimed.task_id == knowledge.task_id
        assert claimed.task_type == "KNOWLEDGE_MEMBERSHIP_ADD"


def test_backup_manifest_and_hash_verification(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_text("mindmate-stage3", encoding="utf-8")
    (source / "runtime").mkdir()
    (source / "runtime" / "ignored.log").write_text("runtime", encoding="utf-8")
    archive = tmp_path / "backup.mindmate-backup"

    manifest = create_backup(source, archive, "0002_stage3")
    assert manifest["file_count"] == 1
    verified = verify_backup(archive)
    assert verified["entries"][0]["path"] == "data.txt"
    with zipfile.ZipFile(archive) as handle:
        assert "manifest.json" in handle.namelist()
