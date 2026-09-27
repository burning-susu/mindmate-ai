"""Bounded maintenance worker for expired history trash rows.

Stops with the application process. Does not run inside request handlers.
"""

from __future__ import annotations

import logging
from threading import Event, Thread

from sqlalchemy.orm import Session, sessionmaker

from mindmate.application.history_purge import DEFAULT_BATCH, purge_expired_history

logger = logging.getLogger(__name__)


class HistoryTrashPurgeWorker:
    """Scan expired soft-deleted history owners in small batches."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        poll_seconds: float = 30.0,
        batch_size: int = DEFAULT_BATCH,
    ) -> None:
        self._session_factory = session_factory
        self._poll_seconds = max(0.05, poll_seconds)
        self._batch_size = max(1, min(batch_size, 50))
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="history-trash-purge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

    def run_once(self) -> dict[str, object]:
        """Execute one bounded purge cycle. Used by tests and explicit maintenance."""
        session = self._session_factory()
        try:
            return purge_expired_history(session, limit=self._batch_size)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                stats = self.run_once()
            except Exception:
                logger.exception("history trash purge cycle failed")
                self._stop.wait(self._poll_seconds)
                continue
            purged = int(stats.get("purged_conversations", 0) or 0) + int(
                stats.get("purged_learning_sessions", 0) or 0
            )
            # Idle longer when the batch was empty; keep scanning while work remains.
            wait = self._poll_seconds if purged == 0 else 0.05
            self._stop.wait(wait)
