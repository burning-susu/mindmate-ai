from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, cast

import numpy as np

from mindmate.ai.embeddings.model_manager import ModelManager, ModelState
from mindmate.application.retrieval_test_queries import (
    LocalRetrievalQueryEncoder,
    RetrievalQueryEncoderError,
)


class _Gate:
    """Test lock that records a blocking acquire and releases it on demand."""

    def __init__(self) -> None:
        self._inner = threading.Lock()
        self.blocking_entered = threading.Event()
        self.allow = threading.Event()

    def acquire(self, blocking: bool = True) -> bool:
        if not blocking:
            return self._inner.acquire(blocking=False)
        self.blocking_entered.set()
        if not self.allow.wait(2):
            return False
        return self._inner.acquire(blocking=True)

    def release(self) -> None:
        self._inner.release()


def test_nonblocking_status_stays_installing_while_the_model_lock_is_held(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path)
    assert manager._lock.acquire(blocking=False)
    try:
        status = manager.status(offline=True)
    finally:
        manager._lock.release()
    assert status.state is ModelState.INSTALLING
    assert status.error_code is None


def test_blocking_status_waits_until_the_model_lock_is_released(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path)
    assert manager._lock.acquire(blocking=False)
    observed: list[ModelState] = []
    finished = threading.Event()

    def read() -> None:
        observed.append(manager.status(offline=True, block=True).state)
        finished.set()

    thread = threading.Thread(target=read)
    thread.start()
    try:
        assert finished.wait(0.2) is False
        assert manager.status(offline=True).state is ModelState.INSTALLING
    finally:
        manager._lock.release()
    assert finished.wait(2)
    thread.join(1)
    assert observed == [ModelState.MISSING_OFFLINE]


def test_query_encoder_waits_out_status_lock_instead_of_model_unavailable(tmp_path: Path) -> None:
    encoder = LocalRetrievalQueryEncoder(tmp_path)
    gate = _Gate()
    cast(Any, encoder._manager)._lock = gate
    errors: list[RetrievalQueryEncoderError] = []
    finished = threading.Event()

    def encode() -> None:
        try:
            encoder.embed_query("固定诊断问题")
        except RetrievalQueryEncoderError as error:
            errors.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=encode)
    thread.start()
    assert gate.blocking_entered.wait(2)
    assert finished.is_set() is False
    gate.allow.set()
    assert finished.wait(2)
    thread.join(1)
    assert len(errors) == 1
    assert errors[0].code == "MODEL_MISSING_OFFLINE"
    assert errors[0].phase == "status_precheck"
    assert errors[0].model_state == ModelState.MISSING_OFFLINE.value


def test_query_encoder_loads_when_blocking_status_is_ready(
    tmp_path: Path, monkeypatch
) -> None:
    encoder = LocalRetrievalQueryEncoder(tmp_path)
    calls: list[bool] = []

    def status(*, offline: bool = False, block: bool = False):
        del offline
        calls.append(block)
        if not block:
            return encoder._manager._status(ModelState.INSTALLING)
        return encoder._manager._status(ModelState.READY)

    class _Paths:
        model_revision = encoder._manager.manifest.model_revision
        artifact_fingerprint = encoder._manager.manifest.fingerprint

    class _Adapter:
        def __init__(self, model: _Paths) -> None:
            self.model = model

        def embed_query(self, text: str) -> np.ndarray:
            assert text == "固定诊断问题"
            return np.ones(4, dtype=np.float32)

    monkeypatch.setattr(encoder._manager, "status", status)
    monkeypatch.setattr(encoder._manager, "ensure_installed", lambda **kwargs: _Paths())
    monkeypatch.setattr("mindmate.ai.embeddings.adapter.OnnxEmbeddingAdapter", _Adapter)

    vector = encoder.embed_query("固定诊断问题")
    assert calls == [True]
    assert vector.shape == (4,)
