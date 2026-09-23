from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from tokenizers import Tokenizer, models, pre_tokenizers, processors

from mindmate.ai.embeddings import adapter as adapter_module
from mindmate.ai.embeddings.adapter import (
    EmbeddingAdapterError,
    EmbeddingInputMode,
    OnnxEmbeddingAdapter,
)
from mindmate.ai.embeddings.manifest import ModelFile, ModelManifest
from mindmate.ai.embeddings.model_manager import ModelPaths


def fixture_manifest() -> ModelManifest:
    files = (
        ModelFile("onnx/model.onnx", 1, hashlib.sha256(b"m").hexdigest()),
        ModelFile("tokenizer.json", 1, hashlib.sha256(b"t").hexdigest()),
        ModelFile("config.json", 1, hashlib.sha256(b"c").hexdigest()),
    )
    return ModelManifest(
        base_model_id="BAAI/bge-small-zh-v1.5",
        base_revision="a" * 40,
        artifact_repository_id="Xenova/bge-small-zh-v1.5",
        artifact_revision="b" * 40,
        license="MIT",
        files=files,
    )


def create_model_paths(tmp_path: Path, manifest: ModelManifest) -> ModelPaths:
    directory = tmp_path / manifest.fingerprint
    (directory / "onnx").mkdir(parents=True)
    (directory / "onnx/model.onnx").write_bytes(b"m")
    (directory / "tokenizer.json").write_bytes(b"t")
    (directory / "config.json").write_bytes(b"c")

    vocab = {
        "[PAD]": 0,
        "[UNK]": 1,
        "[CLS]": 2,
        "[SEP]": 3,
        "alpha": 4,
        "beta": 5,
        "gamma": 6,
    }
    tokenizer = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    tokenizer.post_processor = processors.BertProcessing(("[SEP]", 3), ("[CLS]", 2))
    tokenizer.save(str(directory / "tokenizer.json"))
    return ModelPaths(
        install_directory=directory,
        model_path=directory / "onnx/model.onnx",
        tokenizer_path=directory / "tokenizer.json",
        config_path=directory / "config.json",
        model_revision=manifest.model_revision,
        artifact_fingerprint=manifest.fingerprint,
    )


class FakeInput:
    def __init__(self, name: str) -> None:
        self.name = name
        self.type = "tensor(int64)"


class FakeOutput:
    name = "last_hidden_state"
    type = "tensor(float)"
    shape = ["batch_size", "sequence_length", 512]


class FakeSession:
    def __init__(
        self,
        *,
        providers: list[str] | None = None,
        input_names: tuple[str, ...] = ("input_ids", "attention_mask", "token_type_ids"),
        output_mode: str = "normal",
    ) -> None:
        self.providers = providers or ["CPUExecutionProvider"]
        self.input_names = input_names
        self.output_mode = output_mode
        self.batch_sizes: list[int] = []
        self.last_feed: dict[str, np.ndarray] | None = None
        self.feeds: list[dict[str, np.ndarray]] = []

    def get_inputs(self) -> list[FakeInput]:
        return [FakeInput(name) for name in self.input_names]

    def get_outputs(self) -> list[FakeOutput]:
        return [FakeOutput()]

    def get_providers(self) -> list[str]:
        return self.providers

    def run(self, _output_names: list[str], feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        ids = feed["input_ids"]
        mask = feed["attention_mask"]
        self.batch_sizes.append(ids.shape[0])
        self.last_feed = feed
        self.feeds.append({key: value.copy() for key, value in feed.items()})
        if self.output_mode == "zero":
            return [np.zeros((*ids.shape, 512), dtype=np.float32)]
        hidden = np.zeros((*ids.shape, 512), dtype=np.float32)
        hidden[:, :, 0] = ids + 1
        hidden[:, :, 1] = np.arange(ids.shape[1], dtype=np.float32) + 1
        hidden[:, :, 2] = mask * 2
        if self.output_mode == "nonfinite":
            hidden[0, 0, 0] = np.nan
        return [hidden]


@pytest.fixture
def adapter_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = fixture_manifest()
    paths = create_model_paths(tmp_path, manifest)
    sessions: list[FakeSession] = []

    def make_session(
        *,
        providers: list[str] | None = None,
        input_names: tuple[str, ...] = ("input_ids", "attention_mask", "token_type_ids"),
        output_mode: str = "normal",
        batch_size: int = 16,
    ) -> OnnxEmbeddingAdapter:
        def session_factory(*_args: Any, **_kwargs: Any) -> FakeSession:
            session = FakeSession(
                providers=providers,
                input_names=input_names,
                output_mode=output_mode,
            )
            sessions.append(session)
            return session

        monkeypatch.setattr(adapter_module.ort, "InferenceSession", session_factory)
        return OnnxEmbeddingAdapter(paths, manifest=manifest, batch_size=batch_size)

    return make_session, sessions, paths, manifest


def test_batch_outputs_are_finite_normalized_deterministic_and_bounded(adapter_factory) -> None:
    make_adapter, sessions, _, _ = adapter_factory
    adapter = make_adapter()
    vectors = adapter.embed_documents(["alpha beta", "alpha", "gamma"])
    repeated = adapter.embed_documents(["alpha beta", "alpha", "gamma"])

    assert vectors.shape == (3, 512)
    assert vectors.dtype == np.float32
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-6)
    assert np.array_equal(vectors, repeated)
    assert sessions[0].batch_sizes == [3, 3]


def test_batches_split_at_configured_limit_and_mean_pool_ignores_padding(
    adapter_factory,
) -> None:
    make_adapter, sessions, _, _ = adapter_factory
    adapter = make_adapter(batch_size=2)
    vectors = adapter.embed_documents(["alpha beta", "alpha", "gamma", "beta", "alpha"])

    assert vectors.shape == (5, 512)
    assert sessions[0].batch_sizes == [2, 2, 1]
    first_mask = sessions[0].feeds[0]["attention_mask"]
    assert first_mask.shape == (2, 4)
    assert first_mask[0].tolist() == [1, 1, 1, 1]
    assert first_mask[1].tolist() == [1, 1, 1, 0]


def test_query_instruction_differs_from_document_input(adapter_factory) -> None:
    make_adapter, sessions, _, _ = adapter_factory
    adapter = make_adapter()
    query = adapter.embed_query("alpha")
    document = adapter.embed_batch(["alpha"], mode=EmbeddingInputMode.DOCUMENT)[0]

    assert not np.array_equal(query, document)
    assert "token_type_ids" in sessions[0].last_feed


def test_oversized_inputs_are_rejected_without_truncation(adapter_factory) -> None:
    make_adapter, _, _, _ = adapter_factory
    adapter = make_adapter()

    with pytest.raises(EmbeddingAdapterError, match="EMBEDDING_TEXT_EXCEEDS_MODEL_LIMIT"):
        adapter.embed_documents([" ".join(["alpha"] * 511)])
    with pytest.raises(EmbeddingAdapterError, match="EMBEDDING_TEXT_TOO_LARGE"):
        adapter.embed_documents(["x" * 16_001])
    with pytest.raises(EmbeddingAdapterError, match="EMBEDDING_TEXT_EMPTY"):
        adapter.embed_documents([" \t\n"])


def test_model_fails_closed_on_provider_and_vector_errors(adapter_factory) -> None:
    make_adapter, _, _, _ = adapter_factory
    with pytest.raises(EmbeddingAdapterError, match="ONNX_CPU_PROVIDER_REQUIRED"):
        make_adapter(providers=["CPUExecutionProvider", "CUDAExecutionProvider"])

    make_adapter, _, _, _ = adapter_factory
    zero_adapter = make_adapter(output_mode="zero")
    with pytest.raises(EmbeddingAdapterError, match="EMBEDDING_VECTOR_INVALID"):
        zero_adapter.embed_documents(["alpha"])

    make_adapter, _, _, _ = adapter_factory
    nonfinite_adapter = make_adapter(output_mode="nonfinite")
    with pytest.raises(EmbeddingAdapterError, match="ONNX_OUTPUT_INVALID"):
        nonfinite_adapter.embed_documents(["alpha"])


def test_optional_token_type_input_is_supported(adapter_factory) -> None:
    make_adapter, sessions, _, _ = adapter_factory
    adapter = make_adapter(input_names=("input_ids", "attention_mask"))
    vector = adapter.embed_query("alpha")

    assert vector.shape == (512,)
    assert "token_type_ids" not in sessions[0].last_feed


def test_wrong_artifact_revision_is_rejected(adapter_factory) -> None:
    _, _, paths, manifest = adapter_factory
    invalid = ModelPaths(
        install_directory=paths.install_directory,
        model_path=paths.model_path,
        tokenizer_path=paths.tokenizer_path,
        config_path=paths.config_path,
        model_revision="wrong",
        artifact_fingerprint=paths.artifact_fingerprint,
    )
    with pytest.raises(EmbeddingAdapterError, match="MODEL_REVISION_MISMATCH"):
        OnnxEmbeddingAdapter(invalid, manifest=manifest)


def test_importing_application_does_not_load_onnx_runtime_or_tokenizer() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import mindmate.main; "
                "assert 'onnxruntime' not in sys.modules; "
                "assert 'tokenizers' not in sys.modules"
            ),
        ],
        capture_output=True,
        check=False,
        cwd=Path.cwd(),
        text=True,
    )

    assert result.returncode == 0, result.stderr
