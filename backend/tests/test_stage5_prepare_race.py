from __future__ import annotations

from types import SimpleNamespace

from scripts import prepare_stage5_fixed_ready as prepare
from sqlalchemy.exc import IntegrityError


def test_prepare_reuses_stage_enqueued_by_activation_worker(monkeypatch) -> None:
    version_id = "version-1"
    key = f"index-stage:{version_id}:embedding"
    existing = SimpleNamespace(
        task_id="runtime-task",
        task_type="INDEX_EMBED",
        idempotency_key=key,
        checkpoint_json={"index_version_id": version_id},
    )
    state = {"rolled_back": False, "waited_for": None}

    class Session:
        def __init__(self, step: int) -> None:
            self.step = step

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalars(self, _query):
            return []

        def get(self, _model, _id):
            return SimpleNamespace(embedding_status="COMPLETED" if self.step == 2 else "NOT_STARTED")

        def commit(self):
            raise IntegrityError("INSERT background_tasks", {}, Exception("UNIQUE constraint failed"))

        def rollback(self):
            state["rolled_back"] = True

        def scalar(self, _query):
            return existing

    sessions = iter((Session(0), Session(1), Session(2)))
    app = SimpleNamespace(state=SimpleNamespace(session_factory=lambda: next(sessions)))
    monkeypatch.setattr(
        prepare,
        "_wait_persisted_task",
        lambda _app, task_id: state.update(waited_for=task_id),
    )

    prepare._enqueue_and_wait_index_stage(
        app,
        "knowledge-base-1",
        version_id,
        task_type="INDEX_EMBED",
        status_field="embedding_status",
        enqueue=lambda _session, _version, _key: SimpleNamespace(task_id="script-task"),
        key_suffix="embedding",
    )

    assert state == {"rolled_back": True, "waited_for": "runtime-task"}
