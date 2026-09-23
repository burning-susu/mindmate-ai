from __future__ import annotations

import numpy as np

from mindmate.ai.embeddings.adapter import OnnxEmbeddingAdapter
from mindmate.ai.embeddings.manifest import MODEL_MANIFEST
from mindmate.ai.embeddings.model_manager import ModelManager, ModelProgress
from mindmate.config import Settings


def progress_reporter():
    last_bucket = [-1]

    def report(progress: ModelProgress) -> None:
        percent = progress.total_bytes_downloaded * 100 // progress.total_size_bytes
        bucket = percent // 10
        if bucket > last_bucket[0]:
            print(f"model-download: {percent}%")
            last_bucket[0] = bucket

    return report


def run() -> None:
    manager = ModelManager(Settings().model_dir)
    model = manager.ensure_installed(progress_callback=progress_reporter())
    adapter = OnnxEmbeddingAdapter(model)
    vectors = adapter.embed_batch(
        [
            "为这个句子生成表示以用于检索相关文章：什么是向量数据库？",
            "向量数据库通过向量相似度搜索存储和检索文本嵌入。",
        ]
    )
    assert vectors.shape == (2, 512), vectors.shape
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)

    print(
        "onnx-bge PASS: "
        f"base={MODEL_MANIFEST.base_model_id}@{MODEL_MANIFEST.base_revision} "
        f"artifact={MODEL_MANIFEST.artifact_repository_id}@"
        f"{MODEL_MANIFEST.artifact_revision} "
        f"fingerprint={MODEL_MANIFEST.fingerprint} "
        f"providers=CPUExecutionProvider shape={vectors.shape}"
    )
    for item in MODEL_MANIFEST.files:
        print(f"  {item.path}: sha256={item.sha256}")


if __name__ == "__main__":
    run()
