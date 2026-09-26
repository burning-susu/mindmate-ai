from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from numpy.typing import NDArray

from mindmate.ai.embeddings.model_manager import ModelManager, ModelManagerError, ModelState

if TYPE_CHECKING:
    from mindmate.ai.embeddings.adapter import OnnxEmbeddingAdapter


class RetrievalQueryEncoderError(RuntimeError):
    def __init__(self, code: str, *, phase: str = "unknown", model_state: str = "unknown") -> None:
        super().__init__(code)
        self.code = code
        self.phase = phase
        self.model_state = model_state


class LocalRetrievalQueryEncoder:
    """Lazily loads the verified local query model without downloading it."""

    def __init__(self, model_root: Path) -> None:
        self._manager = ModelManager(model_root)
        self._adapter: OnnxEmbeddingAdapter | None = None
        self._lock = Lock()

    def embed_query(self, text: str) -> NDArray[Any]:
        with self._lock:
            if self._adapter is None:
                status = self._manager.status(offline=True)
                if status.state is not ModelState.READY:
                    code = status.error_code or (
                        "MODEL_MISSING_OFFLINE"
                        if status.state is ModelState.MISSING_OFFLINE
                        else "MODEL_UNAVAILABLE"
                    )
                    raise RetrievalQueryEncoderError(
                        code, phase="preflight", model_state=status.state.value
                    )
                try:
                    paths = self._manager.ensure_installed(allow_download=False)
                except ModelManagerError as error:
                    raise RetrievalQueryEncoderError(error.code, phase="verification") from None

                from mindmate.ai.embeddings.adapter import (
                    EmbeddingAdapterError,
                    OnnxEmbeddingAdapter,
                )

                try:
                    self._adapter = OnnxEmbeddingAdapter(paths)
                except EmbeddingAdapterError as error:
                    raise RetrievalQueryEncoderError(error.code, phase="load") from None

            from mindmate.ai.embeddings.adapter import EmbeddingAdapterError

            try:
                return self._adapter.embed_query(text)
            except EmbeddingAdapterError as error:
                raise RetrievalQueryEncoderError(error.code, phase="inference") from None
