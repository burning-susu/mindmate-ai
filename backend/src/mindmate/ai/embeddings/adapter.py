from __future__ import annotations

import os
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from tokenizers import Tokenizer

from mindmate.ai.embeddings.manifest import (
    CPU_THREAD_LIMIT,
    MAX_BATCH_SIZE,
    MODEL_DIMENSION,
    MODEL_MANIFEST,
    QUERY_INSTRUCTION,
    ModelManifest,
)
from mindmate.ai.embeddings.model_manager import ModelPaths

FloatVectors = NDArray[np.float32]


class EmbeddingInputMode(StrEnum):
    QUERY = "QUERY"
    DOCUMENT = "DOCUMENT"


class EmbeddingAdapterError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OnnxEmbeddingAdapter:
    """Mean-pools BGE token states and returns normalized 512-dimensional vectors."""

    def __init__(
        self,
        model: ModelPaths,
        *,
        manifest: ModelManifest = MODEL_MANIFEST,
        batch_size: int = MAX_BATCH_SIZE,
        cpu_threads: int = 2,
    ) -> None:
        if not 1 <= batch_size <= manifest.max_batch_size:
            raise ValueError(f"batch_size must be between 1 and {manifest.max_batch_size}.")
        if not 1 <= cpu_threads <= CPU_THREAD_LIMIT:
            raise ValueError(f"cpu_threads must be between 1 and {CPU_THREAD_LIMIT}.")
        if (
            model.model_revision != manifest.model_revision
            or model.artifact_fingerprint != manifest.fingerprint
        ):
            raise EmbeddingAdapterError("MODEL_REVISION_MISMATCH")
        if not model.model_path.is_file() or not model.tokenizer_path.is_file():
            raise EmbeddingAdapterError("MODEL_ASSET_MISSING")

        self._batch_size = batch_size
        self._manifest = manifest
        self._tokenizer = self._load_tokenizer(model.tokenizer_path)
        self._pad_id = self._tokenizer.token_to_id("[PAD]")
        if self._pad_id is None:
            raise EmbeddingAdapterError("TOKENIZER_PAD_TOKEN_MISSING")

        options = ort.SessionOptions()
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.intra_op_num_threads = min(cpu_threads, CPU_THREAD_LIMIT, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        try:
            self._session = ort.InferenceSession(
                str(model.model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception:
            raise EmbeddingAdapterError("ONNX_MODEL_LOAD_FAILED") from None
        self._input_names = self._validate_session()
        outputs = self._session.get_outputs()
        self._output_name = outputs[0].name

    @staticmethod
    def _load_tokenizer(path: Path) -> Tokenizer:
        try:
            return Tokenizer.from_file(str(path))
        except Exception:
            raise EmbeddingAdapterError("TOKENIZER_LOAD_FAILED") from None

    def _validate_session(self) -> frozenset[str]:
        inputs = self._session.get_inputs()
        names = {item.name for item in inputs}
        if not {"input_ids", "attention_mask"}.issubset(names):
            raise EmbeddingAdapterError("ONNX_INPUT_INVALID")
        if not names.issubset({"input_ids", "attention_mask", "token_type_ids"}):
            raise EmbeddingAdapterError("ONNX_INPUT_INVALID")
        if any(item.type != "tensor(int64)" for item in inputs):
            raise EmbeddingAdapterError("ONNX_INPUT_INVALID")
        outputs = self._session.get_outputs()
        if not outputs:
            raise EmbeddingAdapterError("ONNX_OUTPUT_INVALID")
        output = outputs[0]
        if (
            output.type != "tensor(float)"
            or not output.shape
            or output.shape[-1] != self._manifest.dimension
        ):
            raise EmbeddingAdapterError("ONNX_OUTPUT_INVALID")
        if self._manifest.dimension != MODEL_DIMENSION:
            raise EmbeddingAdapterError("MODEL_DIMENSION_MISMATCH")
        if self._session.get_providers() != ["CPUExecutionProvider"]:
            raise EmbeddingAdapterError("ONNX_CPU_PROVIDER_REQUIRED")
        return frozenset(names)

    def embed_query(self, text: str) -> FloatVectors:
        return self.embed_batch([text], mode=EmbeddingInputMode.QUERY)[0]

    def embed_documents(self, texts: Sequence[str]) -> FloatVectors:
        return self.embed_batch(texts, mode=EmbeddingInputMode.DOCUMENT)

    def embed_batch(
        self,
        texts: Sequence[str],
        *,
        mode: EmbeddingInputMode = EmbeddingInputMode.DOCUMENT,
    ) -> FloatVectors:
        try:
            input_mode = EmbeddingInputMode(mode)
        except (TypeError, ValueError):
            raise EmbeddingAdapterError("EMBEDDING_MODE_INVALID") from None
        if not texts:
            return np.empty((0, self._manifest.dimension), dtype=np.float32)

        results: list[FloatVectors] = []
        for start in range(0, len(texts), self._batch_size):
            group = texts[start : start + self._batch_size]
            prepared = [self._prepare_text(text, input_mode) for text in group]
            results.append(self._embed_group(prepared))
        return np.concatenate(results, axis=0).astype(np.float32, copy=False)

    def _prepare_text(self, text: str, mode: EmbeddingInputMode) -> str:
        if not isinstance(text, str):
            raise EmbeddingAdapterError("EMBEDDING_TEXT_INVALID")
        if not text.strip():
            raise EmbeddingAdapterError("EMBEDDING_TEXT_EMPTY")
        prepared = f"{QUERY_INSTRUCTION}{text}" if mode is EmbeddingInputMode.QUERY else text
        if len(prepared) > self._manifest.max_input_characters:
            raise EmbeddingAdapterError("EMBEDDING_TEXT_TOO_LARGE")
        return prepared

    def _embed_group(self, texts: list[str]) -> FloatVectors:
        try:
            rows = self._tokenizer.encode_batch(texts, add_special_tokens=True)
        except Exception:
            raise EmbeddingAdapterError("TOKENIZATION_FAILED") from None
        lengths = [len(row.ids) for row in rows]
        if any(length > self._manifest.max_sequence_length for length in lengths):
            raise EmbeddingAdapterError("EMBEDDING_TEXT_EXCEEDS_MODEL_LIMIT")
        max_length = max(lengths)
        input_ids = np.full((len(rows), max_length), self._pad_id, dtype=np.int64)
        attention_mask = np.zeros((len(rows), max_length), dtype=np.int64)
        token_type_ids = np.zeros((len(rows), max_length), dtype=np.int64)
        for index, row in enumerate(rows):
            length = lengths[index]
            input_ids[index, :length] = row.ids
            attention_mask[index, :length] = row.attention_mask
            token_type_ids[index, :length] = row.type_ids

        feed = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = token_type_ids
        try:
            hidden = np.asarray(
                self._session.run([self._output_name], feed)[0],
                dtype=np.float32,
            )
        except Exception:
            raise EmbeddingAdapterError("ONNX_INFERENCE_FAILED") from None
        if (
            hidden.ndim != 3
            or hidden.shape[:2] != input_ids.shape
            or hidden.shape[2] != self._manifest.dimension
            or not np.isfinite(hidden).all()
        ):
            raise EmbeddingAdapterError("ONNX_OUTPUT_INVALID")

        weights = attention_mask[:, :, None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / weights.sum(axis=1)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        if not np.isfinite(norms).all() or np.any(norms <= 1e-12):
            raise EmbeddingAdapterError("EMBEDDING_VECTOR_INVALID")
        vectors = pooled / norms
        if vectors.shape != (len(rows), self._manifest.dimension) or not np.isfinite(
            vectors
        ).all():
            raise EmbeddingAdapterError("EMBEDDING_VECTOR_INVALID")
        return vectors.astype(np.float32, copy=False)
