from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from mindmate.ai.embeddings.manifest import (
    BAAI_MODEL_ID,
    BAAI_MODEL_REVISION,
    MODEL_MANIFEST,
    ONNX_REPOSITORY_ID,
    ONNX_REPOSITORY_REVISION,
    ModelFile,
    ModelManifest,
)
from mindmate.ai.embeddings.model_manager import (
    ModelManager,
    ModelManagerError,
    ModelState,
)


def fixture_artifacts(
    *,
    wrong_model_hash: bool = False,
    model_payload: bytes = b"offline onnx fixture",
):
    payloads = {
        "onnx/model.onnx": model_payload,
        "tokenizer.json": b"offline tokenizer fixture",
        "config.json": json.dumps(
            {
                "model_type": "bert",
                "hidden_size": 512,
                "max_position_embeddings": 512,
                "num_hidden_layers": 4,
                "vocab_size": 21_128,
            },
            separators=(",", ":"),
        ).encode(),
    }
    files = tuple(
        ModelFile(
            path=name,
            size_bytes=len(payload),
            sha256=(
                "0" * 64
                if wrong_model_hash and name == "onnx/model.onnx"
                else hashlib.sha256(payload).hexdigest()
            ),
        )
        for name, payload in payloads.items()
    )
    manifest = ModelManifest(
        base_model_id="BAAI/bge-small-zh-v1.5",
        base_revision="a" * 40,
        artifact_repository_id="Xenova/bge-small-zh-v1.5",
        artifact_revision="b" * 40,
        license="MIT",
        files=files,
    )
    return manifest, payloads


def transport_for(
    manifest: ModelManifest,
    payloads: dict[str, bytes],
    *,
    missing_file: str | None = None,
    wrong_length_file: str | None = None,
    chunked_file: str | None = None,
    request_log: list[str] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request_log is not None:
            request_log.append(path)
        if missing_file is not None and path.endswith(f"/{missing_file}"):
            return httpx.Response(404, request=request)
        item_path = next(name for name in payloads if path.endswith(f"/{name}"))
        body = payloads[item_path]
        headers = {"Content-Length": str(len(body))}
        if wrong_length_file == item_path:
            headers["Content-Length"] = str(len(body) + 1)
        if chunked_file == item_path:
            return httpx.Response(
                200,
                headers=headers,
                stream=ChunkedStream(body),
                request=request,
            )
        return httpx.Response(200, headers=headers, content=body, request=request)

    return httpx.MockTransport(handler)


class ChunkedStream(httpx.SyncByteStream):
    def __init__(self, content: bytes) -> None:
        midpoint = max(1, len(content) // 2)
        self._chunks = (content[:midpoint], content[midpoint:])

    def __iter__(self):
        yield from self._chunks

    def close(self) -> None:
        return


def test_manifest_uses_immutable_revisions_and_known_model_checksums() -> None:
    assert MODEL_MANIFEST.base_model_id == BAAI_MODEL_ID
    assert MODEL_MANIFEST.base_revision == BAAI_MODEL_REVISION
    assert MODEL_MANIFEST.artifact_repository_id == ONNX_REPOSITORY_ID
    assert MODEL_MANIFEST.artifact_revision == ONNX_REPOSITORY_REVISION
    assert MODEL_MANIFEST.license == "MIT"
    assert len(MODEL_MANIFEST.fingerprint) == 64
    assert len(MODEL_MANIFEST.model_revision) <= 200
    assert MODEL_MANIFEST.total_size_bytes == 95_291_718
    assert {item.path for item in MODEL_MANIFEST.files} == {
        "onnx/model.onnx",
        "tokenizer.json",
        "config.json",
    }


@pytest.mark.parametrize("unsafe_path", ["../escape", r"onnx\..\escape", "/absolute"])
def test_manifest_rejects_unsafe_artifact_paths(unsafe_path: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        ModelManifest(
            base_model_id="BAAI/bge-small-zh-v1.5",
            base_revision="a" * 40,
            artifact_repository_id="Xenova/bge-small-zh-v1.5",
            artifact_revision="b" * 40,
            license="MIT",
            files=(
                ModelFile(unsafe_path, 1, "0" * 64),
                ModelFile("tokenizer.json", 1, "0" * 64),
                ModelFile("config.json", 1, "0" * 64),
            ),
        )


def test_install_verifies_hashes_reports_progress_and_handles_offline(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts()
    manager = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=transport_for(manifest, payloads),
    )

    assert manager.status(offline=True).state is ModelState.MISSING_OFFLINE
    with pytest.raises(ModelManagerError, match="MODEL_MISSING_OFFLINE"):
        manager.ensure_installed(allow_download=False)

    progress = []
    installed = manager.ensure_installed(progress_callback=progress.append)

    assert manager.status().state is ModelState.READY
    assert installed.install_directory.is_dir()
    assert installed.model_revision == manifest.model_revision
    assert installed.artifact_fingerprint == manifest.fingerprint
    assert not manager.partial_directory.exists()
    assert len(progress) >= len(manifest.files)
    assert progress[-1].total_bytes_downloaded == manifest.total_size_bytes
    for item in manifest.files:
        assert hashlib.sha256((installed.install_directory / item.path).read_bytes()).hexdigest() == (
            item.sha256
        )


def test_hash_mismatch_keeps_partial_files_and_persisted_error(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts(wrong_model_hash=True)
    manager = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=transport_for(manifest, payloads),
    )

    with pytest.raises(ModelManagerError, match="MODEL_HASH_MISMATCH"):
        manager.ensure_installed()

    assert not manager.install_directory.exists()
    assert manager.partial_directory.is_dir()
    status = manager.status(offline=True)
    assert status.state is ModelState.MISSING_OFFLINE
    assert status.error_code == "MODEL_HASH_MISMATCH"


def test_missing_file_and_truncated_download_are_stable_failures(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts()
    missing = ModelManager(
        tmp_path / "missing",
        manifest=manifest,
        transport=transport_for(manifest, payloads, missing_file="tokenizer.json"),
    )
    with pytest.raises(ModelManagerError, match="MODEL_SOURCE_FILE_MISSING"):
        missing.ensure_installed()
    assert (missing.partial_directory / "onnx/model.onnx").is_file()
    assert not missing.install_directory.exists()

    truncated = ModelManager(
        tmp_path / "truncated",
        manifest=manifest,
        transport=transport_for(
            manifest,
            payloads,
            wrong_length_file="onnx/model.onnx",
        ),
    )
    with pytest.raises(ModelManagerError, match="MODEL_SOURCE_SIZE_MISMATCH"):
        truncated.ensure_installed()
    assert not truncated.install_directory.exists()


def test_cancel_preserves_partial_download_and_retry_publishes_atomically(
    tmp_path: Path,
) -> None:
    manifest, payloads = fixture_artifacts(model_payload=b"m" * (64 * 1024 + 100))
    manager = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=transport_for(manifest, payloads, chunked_file="onnx/model.onnx"),
    )
    cancelled = threading.Event()

    def cancel_after_first_chunk(progress) -> None:
        if progress.file_path == "onnx/model.onnx" and progress.file_bytes_downloaded:
            cancelled.set()

    with pytest.raises(ModelManagerError, match="MODEL_DOWNLOAD_CANCELLED"):
        manager.ensure_installed(
            cancel_event=cancelled,
            progress_callback=cancel_after_first_chunk,
        )

    partial_model = manager.partial_directory / "onnx/model.onnx"
    assert partial_model.is_file()
    assert partial_model.stat().st_size < len(payloads["onnx/model.onnx"])
    assert manager.status().error_code == "MODEL_DOWNLOAD_CANCELLED"

    retry = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=transport_for(manifest, payloads),
    )
    installed = retry.ensure_installed()
    assert retry.status().state is ModelState.READY
    assert installed.model_path.is_file()
    assert not retry.error_path.exists()


def test_cancel_on_final_download_chunk_does_not_publish(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts()
    manager = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=transport_for(manifest, payloads),
    )
    cancelled = threading.Event()

    def cancel_after_last_file(progress) -> None:
        if progress.file_path == "config.json" and (
            progress.file_bytes_downloaded == progress.file_size_bytes
        ):
            cancelled.set()

    with pytest.raises(ModelManagerError, match="MODEL_DOWNLOAD_CANCELLED"):
        manager.ensure_installed(
            cancel_event=cancelled,
            progress_callback=cancel_after_last_file,
        )

    assert not manager.install_directory.exists()
    assert manager.partial_directory.is_dir()
    assert manager.status().error_code == "MODEL_DOWNLOAD_CANCELLED"


def test_concurrent_installation_publishes_one_complete_copy(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts()
    request_log: list[str] = []
    request_guard = threading.Lock()

    def factory() -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            with request_guard:
                request_log.append(request.url.path)
            time.sleep(0.01)
            path = next(name for name in payloads if request.url.path.endswith(f"/{name}"))
            body = payloads[path]
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(body))},
                content=body,
                request=request,
            )

        return httpx.MockTransport(handler)

    managers = [
        ModelManager(tmp_path, manifest=manifest, transport=factory()),
        ModelManager(tmp_path, manifest=manifest, transport=factory()),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        installed = list(pool.map(lambda manager: manager.ensure_installed(), managers))

    assert installed[0].install_directory == installed[1].install_directory
    assert len(request_log) == len(manifest.files)
    assert managers[0].status().state is ModelState.READY


def test_untrusted_redirect_is_rejected_before_following(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url)
        return httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1/private"},
            request=request,
        )

    manager = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelManagerError, match="MODEL_DOWNLOAD_REDIRECT_INVALID"):
        manager.ensure_installed()
    assert len(requests) == 1


def test_network_timeout_is_mapped_without_publishing_partial_model(tmp_path: Path) -> None:
    manifest, _ = fixture_artifacts()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture timeout", request=request)

    manager = ModelManager(
        tmp_path,
        manifest=manifest,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelManagerError, match="MODEL_DOWNLOAD_TIMEOUT"):
        manager.ensure_installed()

    assert not manager.install_directory.exists()
    assert manager.status().error_code == "MODEL_DOWNLOAD_TIMEOUT"


def test_model_config_mismatch_is_not_published(tmp_path: Path) -> None:
    manifest, payloads = fixture_artifacts()
    payloads["config.json"] = payloads["config.json"].replace(b"512", b"384", 1)
    files = tuple(
        ModelFile(
            item.path,
            len(payloads[item.path]),
            hashlib.sha256(payloads[item.path]).hexdigest(),
        )
        for item in manifest.files
    )
    changed = ModelManifest(
        base_model_id=manifest.base_model_id,
        base_revision=manifest.base_revision,
        artifact_repository_id=manifest.artifact_repository_id,
        artifact_revision=manifest.artifact_revision,
        license=manifest.license,
        files=files,
    )
    manager = ModelManager(
        tmp_path,
        manifest=changed,
        transport=transport_for(changed, payloads),
    )

    with pytest.raises(ModelManagerError, match="MODEL_CONFIG_INVALID"):
        manager.ensure_installed()
    assert not manager.install_directory.exists()
