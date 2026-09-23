from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

BAAI_MODEL_ID = "BAAI/bge-small-zh-v1.5"
BAAI_MODEL_REVISION = "7999e1d3359715c523056ef9478215996d62a620"
ONNX_REPOSITORY_ID = "Xenova/bge-small-zh-v1.5"
ONNX_REPOSITORY_REVISION = "75c43b069aac4d136ba6bc1122f995fedcfd2781"
MODEL_LICENSE = "MIT"
MODEL_DIMENSION = 512
MAX_SEQUENCE_LENGTH = 512
MAX_INPUT_CHARACTERS = 16_000
MAX_BATCH_SIZE = 16
CPU_THREAD_LIMIT = 4
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
MODEL_DIRECTORY_NAME = "bge-small-zh-v1.5"
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class ModelFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ModelManifest:
    base_model_id: str
    base_revision: str
    artifact_repository_id: str
    artifact_revision: str
    license: str
    files: tuple[ModelFile, ...]
    dimension: int = MODEL_DIMENSION
    max_sequence_length: int = MAX_SEQUENCE_LENGTH
    max_input_characters: int = MAX_INPUT_CHARACTERS
    max_batch_size: int = MAX_BATCH_SIZE

    def __post_init__(self) -> None:
        repository_pattern = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*"
        if (
            re.fullmatch(repository_pattern, self.base_model_id) is None
            or re.fullmatch(repository_pattern, self.artifact_repository_id) is None
        ):
            raise ValueError("Model repositories must be fixed Hugging Face repository IDs.")
        for revision in (self.base_revision, self.artifact_revision):
            if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
                raise ValueError("Model revisions must be immutable 40-character commits.")
        if not self.files or len({item.path for item in self.files}) != len(self.files):
            raise ValueError("Model manifest files must be non-empty and unique.")
        if sum(item.size_bytes for item in self.files) > MAX_DOWNLOAD_BYTES:
            raise ValueError("Model manifest exceeds the configured download size limit.")
        for item in self.files:
            parts = item.path.split("/")
            if (
                not item.path
                or "\\" in item.path
                or ":" in item.path
                or PurePosixPath(item.path).is_absolute()
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise ValueError("Model manifest contains an unsafe relative path.")
            if item.size_bytes <= 0 or re.fullmatch(r"[0-9a-f]{64}", item.sha256) is None:
                raise ValueError("Model manifest contains an invalid size or SHA-256.")
        required = {"onnx/model.onnx", "tokenizer.json", "config.json"}
        if not required.issubset({item.path for item in self.files}):
            raise ValueError("Model manifest is missing a required inference artifact.")
        if self.dimension != 512 or self.max_sequence_length != 512:
            raise ValueError("The frozen BGE model contract requires 512 dimensions and tokens.")
        if not 1 <= self.max_batch_size <= MAX_BATCH_SIZE:
            raise ValueError("The model batch limit is outside the configured resource bound.")
        if not 1 <= self.max_input_characters <= MAX_INPUT_CHARACTERS:
            raise ValueError("The model character limit is outside the configured resource bound.")

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)

    @property
    def fingerprint(self) -> str:
        payload = {
            "base_model_id": self.base_model_id,
            "base_revision": self.base_revision,
            "artifact_repository_id": self.artifact_repository_id,
            "artifact_revision": self.artifact_revision,
            "license": self.license,
            "files": [
                {"path": item.path, "size_bytes": item.size_bytes, "sha256": item.sha256}
                for item in self.files
            ],
            "inference": {
                "dimension": self.dimension,
                "max_sequence_length": self.max_sequence_length,
                "max_input_characters": self.max_input_characters,
                "max_batch_size": self.max_batch_size,
                "pooling": "attention-mask-mean",
                "normalization": "l2",
                "query_instruction": QUERY_INSTRUCTION,
            },
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def model_revision(self) -> str:
        return (
            f"{self.base_revision};{self.artifact_revision};"
            f"{self.fingerprint}"
        )


MODEL_MANIFEST = ModelManifest(
    base_model_id=BAAI_MODEL_ID,
    base_revision=BAAI_MODEL_REVISION,
    artifact_repository_id=ONNX_REPOSITORY_ID,
    artifact_revision=ONNX_REPOSITORY_REVISION,
    license=MODEL_LICENSE,
    files=(
        ModelFile(
            "onnx/model.onnx",
            94_851_877,
            "69a0b846f4f116b5e6aabf9546ea6754d02264f3211a13a1bd69b31b8040749a",
        ),
        ModelFile(
            "tokenizer.json",
            439_125,
            "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26",
        ),
        ModelFile(
            "config.json",
            716,
            "d4193ead3a810fd694fa8a31d7fc72fbaebc0668b603e398734bf2f6538ff42f",
        ),
    ),
)

MODEL_ARTIFACT_FINGERPRINT = MODEL_MANIFEST.fingerprint
MODEL_REVISION = MODEL_MANIFEST.model_revision
