from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

REPO = "onnx-community/bge-small-zh-v1.5-ONNX"
REVISION = "main"
MODEL_DIR = Path(os.environ.get("MINDMATE_SPIKE_MODEL_DIR", "model-cache/bge-small-zh-v1.5-onnx"))
FILES = (
    "onnx/model.onnx",
    "onnx/model.onnx_data",
    "tokenizer.json",
    "tokenizer_config.json",
    "config.json",
)


def download() -> dict[str, Path]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return {
        name: Path(
            hf_hub_download(
                repo_id=REPO,
                filename=name,
                revision=REVISION,
                local_dir=MODEL_DIR,
                local_dir_use_symlinks=False,
            )
        )
        for name in FILES
    }


def pool(output: np.ndarray, mask: np.ndarray) -> np.ndarray:
    expanded = np.expand_dims(mask, axis=-1).astype(np.float32)
    pooled = (output * expanded).sum(axis=1) / np.clip(expanded.sum(axis=1), 1e-9, None)
    return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)


def run() -> None:
    paths = download()
    tokenizer = Tokenizer.from_file(str(paths["tokenizer.json"]))
    encoded = tokenizer.encode("这是一个本地 Embedding Windows Spike。")
    inputs = {
        "input_ids": np.asarray([encoded.ids], dtype=np.int64),
        "attention_mask": np.asarray([encoded.attention_mask], dtype=np.int64),
    }
    if any(
        item.name == "token_type_ids"
        for item in ort.InferenceSession(
            str(paths["onnx/model.onnx"]), providers=["CPUExecutionProvider"]
        ).get_inputs()
    ):
        inputs["token_type_ids"] = np.asarray([encoded.type_ids], dtype=np.int64)

    session = ort.InferenceSession(
        str(paths["onnx/model.onnx"]), providers=["CPUExecutionProvider"]
    )
    result = session.run(None, inputs)
    hidden = np.asarray(result[0])
    embedding = pool(hidden, inputs["attention_mask"])
    repeat = pool(np.asarray(session.run(None, inputs)[0]), inputs["attention_mask"])
    assert embedding.shape == (1, 512), embedding.shape
    assert np.allclose(embedding, repeat, atol=1e-5)
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    print(
        "onnx-bge PASS: "
        f"repo={REPO} revision={REVISION} shape={embedding.shape} "
        f"providers={session.get_providers()}"
    )
    for name, digest in hashes.items():
        print(f"  {name}: {digest}")


if __name__ == "__main__":
    run()
