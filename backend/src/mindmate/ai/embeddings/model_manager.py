from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from time import monotonic
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx

from mindmate.ai.embeddings.manifest import (
    MAX_DOWNLOAD_BYTES,
    MODEL_DIRECTORY_NAME,
    MODEL_MANIFEST,
    ModelFile,
    ModelManifest,
)

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5
DOWNLOAD_CHUNK_BYTES = 64 * 1024
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class ModelState(StrEnum):
    READY = "READY"
    MISSING = "MISSING"
    MISSING_OFFLINE = "MISSING_OFFLINE"
    CORRUPT = "CORRUPT"
    INSTALLING = "INSTALLING"


class ModelManagerError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ModelPaths:
    install_directory: Path
    model_path: Path
    tokenizer_path: Path
    config_path: Path
    model_revision: str
    artifact_fingerprint: str


@dataclass(frozen=True)
class ModelProgress:
    file_path: str
    file_bytes_downloaded: int
    file_size_bytes: int
    total_bytes_downloaded: int
    total_size_bytes: int


@dataclass(frozen=True)
class ModelStatus:
    state: ModelState
    model_revision: str
    artifact_fingerprint: str
    total_size_bytes: int
    error_code: str | None = None


ProgressCallback = Callable[[ModelProgress], None]


def _lock_for(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


class ModelManager:
    """Fetches one immutable public model artifact and publishes only verified files."""

    def __init__(
        self,
        model_root: Path,
        *,
        manifest: ModelManifest = MODEL_MANIFEST,
        transport: httpx.BaseTransport | None = None,
        connect_timeout_seconds: float = 10,
        read_timeout_seconds: float = 30,
        total_timeout_seconds: float = 900,
    ) -> None:
        if (
            connect_timeout_seconds <= 0
            or read_timeout_seconds <= 0
            or total_timeout_seconds <= 0
        ):
            raise ValueError("Download timeouts must be positive.")
        self.model_root = model_root.expanduser().resolve()
        self.manifest = manifest
        self.transport = transport
        self.timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=10,
            pool=10,
        )
        self.total_timeout_seconds = total_timeout_seconds
        self.model_parent = self.model_root / MODEL_DIRECTORY_NAME
        self.install_directory = self.model_parent / manifest.fingerprint
        self.partial_directory = self.model_parent / f"{manifest.fingerprint}.partial"
        self.error_path = self.model_parent / f"{manifest.fingerprint}.error.json"
        self._lock = _lock_for(self.install_directory)

    def status(self, *, offline: bool = False) -> ModelStatus:
        if not self._lock.acquire(blocking=False):
            return self._status(ModelState.INSTALLING)
        try:
            if self._model_parent_is_unsafe():
                return self._status(ModelState.CORRUPT, "MODEL_PATH_UNSAFE")
            error_code = self._read_error_code()
            if self.install_directory.is_symlink():
                return self._status(ModelState.CORRUPT, "MODEL_PATH_UNSAFE")
            if self.install_directory.exists():
                try:
                    self._verified_paths(self.install_directory)
                except ModelManagerError as error:
                    return self._status(ModelState.CORRUPT, error.code)
                return self._status(ModelState.READY)
            state = ModelState.MISSING_OFFLINE if offline else ModelState.MISSING
            return self._status(state, error_code)
        finally:
            self._lock.release()

    def ensure_installed(
        self,
        *,
        allow_download: bool = True,
        cancel_event: threading.Event | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ModelPaths:
        with self._lock:
            if self._model_parent_is_unsafe():
                raise ModelManagerError("MODEL_PATH_UNSAFE")
            if self.install_directory.is_symlink():
                raise ModelManagerError("MODEL_PATH_UNSAFE")
            if self.install_directory.exists():
                try:
                    return self._verified_paths(self.install_directory)
                except ModelManagerError:
                    pass
            if not allow_download:
                code = (
                    "MODEL_MISSING_OFFLINE"
                    if not self.install_directory.exists()
                    else "MODEL_INSTALL_NOT_VERIFIED"
                )
                raise ModelManagerError(code)

            try:
                self._ensure_layout()
                self._download_and_publish(
                    cancel_event,
                    progress_callback,
                    deadline=monotonic() + self.total_timeout_seconds,
                )
                return self._verified_paths(self.install_directory)
            except ModelManagerError as error:
                self._record_error(error.code)
                raise
            except (httpx.ConnectError, httpx.ConnectTimeout):
                self._record_error("MODEL_DOWNLOAD_OFFLINE")
                raise ModelManagerError("MODEL_DOWNLOAD_OFFLINE") from None
            except httpx.TimeoutException:
                self._record_error("MODEL_DOWNLOAD_TIMEOUT")
                raise ModelManagerError("MODEL_DOWNLOAD_TIMEOUT") from None
            except httpx.HTTPError:
                self._record_error("MODEL_DOWNLOAD_FAILED")
                raise ModelManagerError("MODEL_DOWNLOAD_FAILED") from None
            except OSError:
                self._record_error("MODEL_INSTALL_FAILED")
                raise ModelManagerError("MODEL_INSTALL_FAILED") from None

    def _ensure_layout(self) -> None:
        self.model_root.mkdir(parents=True, exist_ok=True)
        if self.model_parent.is_symlink():
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        self.model_parent.mkdir(parents=True, exist_ok=True)
        if not self.model_parent.resolve().is_relative_to(self.model_root):
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        if self.install_directory.is_symlink():
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        if self.partial_directory.is_symlink():
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        self.partial_directory.mkdir(parents=True, exist_ok=True)

    def _download_and_publish(
        self,
        cancel_event: threading.Event | None,
        progress_callback: ProgressCallback | None,
        *,
        deadline: float,
    ) -> None:
        total_downloaded = 0
        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            for item in self.manifest.files:
                self._check_download_state(cancel_event, deadline)
                target = self._safe_file_path(self.partial_directory, item.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if self._matches_file(target, item):
                    total_downloaded += item.size_bytes
                    self._emit(
                        progress_callback,
                        ModelProgress(
                            item.path,
                            item.size_bytes,
                            item.size_bytes,
                            total_downloaded,
                            self.manifest.total_size_bytes,
                        ),
                    )
                    continue
                total_downloaded += self._download_file(
                    client,
                    item,
                    target,
                    total_downloaded,
                    cancel_event,
                    progress_callback,
                    deadline,
                )

        self._check_download_state(cancel_event, deadline)
        self._validate_directory(self.partial_directory)
        self._publish()
        try:
            self.error_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _download_file(
        self,
        client: httpx.Client,
        item: ModelFile,
        target: Path,
        total_before_file: int,
        cancel_event: threading.Event | None,
        progress_callback: ProgressCallback | None,
        deadline: float,
    ) -> int:
        source = (
            f"https://huggingface.co/{self.manifest.artifact_repository_id}/resolve/"
            f"{self.manifest.artifact_revision}/{item.path}"
        )
        response = self._open_response(client, source)
        try:
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    announced_size = int(content_length)
                except ValueError:
                    raise ModelManagerError("MODEL_SOURCE_SIZE_INVALID") from None
                if announced_size != item.size_bytes:
                    raise ModelManagerError("MODEL_SOURCE_SIZE_MISMATCH")

            received = 0
            with target.open("wb") as output:
                for chunk in response.iter_bytes(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    self._check_download_state(cancel_event, deadline)
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > item.size_bytes or received > MAX_DOWNLOAD_BYTES:
                        raise ModelManagerError("MODEL_SOURCE_SIZE_EXCEEDED")
                    output.write(chunk)
                    self._emit(
                        progress_callback,
                        ModelProgress(
                            item.path,
                            received,
                            item.size_bytes,
                            total_before_file + received,
                            self.manifest.total_size_bytes,
                        ),
                    )
            if received != item.size_bytes:
                raise ModelManagerError("MODEL_SOURCE_SIZE_MISMATCH")
            if not self._matches_file(target, item):
                raise ModelManagerError("MODEL_HASH_MISMATCH")
            return received
        finally:
            response.close()

    def _open_response(self, client: httpx.Client, source: str) -> httpx.Response:
        current_url = source
        for redirect_count in range(MAX_REDIRECTS + 1):
            request = client.build_request(
                "GET",
                current_url,
                headers={"Accept-Encoding": "identity"},
            )
            response = client.send(request, stream=True, follow_redirects=False)
            if response.status_code in REDIRECT_STATUSES:
                location = response.headers.get("location")
                response.close()
                if location is None or redirect_count == MAX_REDIRECTS:
                    raise ModelManagerError("MODEL_DOWNLOAD_REDIRECT_INVALID")
                next_url = urljoin(current_url, location)
                if not self._is_trusted_download_url(next_url):
                    raise ModelManagerError("MODEL_DOWNLOAD_REDIRECT_INVALID")
                current_url = next_url
                continue
            if response.status_code == 404:
                response.close()
                raise ModelManagerError("MODEL_SOURCE_FILE_MISSING")
            if response.status_code != 200:
                response.close()
                raise ModelManagerError("MODEL_DOWNLOAD_HTTP_ERROR")
            return response
        raise ModelManagerError("MODEL_DOWNLOAD_REDIRECT_INVALID")

    @staticmethod
    def _is_trusted_download_url(value: str) -> bool:
        try:
            parsed = urlparse(value)
            port = parsed.port
        except ValueError:
            return False
        host = (parsed.hostname or "").lower()
        trusted_host = (
            host == "huggingface.co"
            or host.endswith(".huggingface.co")
            or host == "hf.co"
            or host.endswith(".hf.co")
        )
        return (
            parsed.scheme == "https"
            and trusted_host
            and parsed.username is None
            and parsed.password is None
            and port in {None, 443}
        )

    @staticmethod
    def _check_download_state(
        cancel_event: threading.Event | None,
        deadline: float,
    ) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ModelManagerError("MODEL_DOWNLOAD_CANCELLED")
        if monotonic() >= deadline:
            raise ModelManagerError("MODEL_DOWNLOAD_TIMEOUT")

    def _validate_directory(self, directory: Path) -> None:
        expected = {item.path for item in self.manifest.files}
        actual: set[str] = set()
        if directory.is_symlink():
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ModelManagerError("MODEL_PATH_UNSAFE")
            if path.is_file():
                actual.add(path.relative_to(directory).as_posix())
        if actual != expected:
            raise ModelManagerError("MODEL_FILES_INCOMPLETE")
        for item in self.manifest.files:
            path = self._safe_file_path(directory, item.path)
            if not self._matches_file(path, item):
                raise ModelManagerError("MODEL_HASH_MISMATCH")
        self._validate_config(self._safe_file_path(directory, "config.json"))

    def _verified_paths(self, directory: Path) -> ModelPaths:
        self._validate_directory(directory)
        return ModelPaths(
            install_directory=directory,
            model_path=self._safe_file_path(directory, "onnx/model.onnx"),
            tokenizer_path=self._safe_file_path(directory, "tokenizer.json"),
            config_path=self._safe_file_path(directory, "config.json"),
            model_revision=self.manifest.model_revision,
            artifact_fingerprint=self.manifest.fingerprint,
        )

    def _safe_file_path(self, directory: Path, relative_path: str) -> Path:
        parts = relative_path.split("/")
        if (
            not relative_path
            or "\\" in relative_path
            or ":" in relative_path
            or PurePosixPath(relative_path).is_absolute()
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        if directory.is_symlink():
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        base = directory.resolve()
        target = directory.joinpath(*parts)
        current = directory
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ModelManagerError("MODEL_PATH_UNSAFE")
        if not target.resolve().is_relative_to(base):
            raise ModelManagerError("MODEL_PATH_UNSAFE")
        return target

    def _validate_config(self, path: Path) -> None:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ModelManagerError("MODEL_CONFIG_INVALID") from None
        expected = {
            "model_type": "bert",
            "hidden_size": self.manifest.dimension,
            "max_position_embeddings": self.manifest.max_sequence_length,
            "num_hidden_layers": 4,
            "vocab_size": 21_128,
        }
        if any(config.get(key) != value for key, value in expected.items()):
            raise ModelManagerError("MODEL_CONFIG_INVALID")

    @staticmethod
    def _matches_file(path: Path, item: ModelFile) -> bool:
        try:
            if path.is_symlink() or path.stat().st_size != item.size_bytes:
                return False
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK_BYTES), b""):
                    digest.update(chunk)
            return digest.hexdigest() == item.sha256
        except OSError:
            return False

    def _publish(self) -> None:
        if not self.install_directory.exists():
            try:
                os.replace(self.partial_directory, self.install_directory)
            except OSError:
                raise ModelManagerError("MODEL_PUBLISH_FAILED") from None
            return

        backup = self.model_parent / f"{self.manifest.fingerprint}.invalid-{uuid4().hex}"
        try:
            os.replace(self.install_directory, backup)
            os.replace(self.partial_directory, self.install_directory)
        except OSError:
            if backup.exists() and not self.install_directory.exists():
                try:
                    os.replace(backup, self.install_directory)
                except OSError:
                    pass
            raise ModelManagerError("MODEL_PUBLISH_FAILED") from None

    def _record_error(self, code: str) -> None:
        try:
            if self._model_parent_is_unsafe() or self.error_path.is_symlink():
                return
            self.model_parent.mkdir(parents=True, exist_ok=True)
            temporary = self.model_parent / f"{self.error_path.name}.{uuid4().hex}.tmp"
            payload = {"artifact_fingerprint": self.manifest.fingerprint, "error_code": code}
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary, self.error_path)
        except OSError:
            return

    def _read_error_code(self) -> str | None:
        if self._model_parent_is_unsafe():
            return "MODEL_PATH_UNSAFE"
        if not self.error_path.exists():
            return None
        if self.error_path.is_symlink():
            return "MODEL_STATUS_UNSAFE"
        try:
            payload = json.loads(self.error_path.read_text(encoding="utf-8"))
            code = payload.get("error_code")
            if (
                payload.get("artifact_fingerprint") == self.manifest.fingerprint
                and isinstance(code, str)
                and re.fullmatch(r"[A-Z0-9_]{1,80}", code)
            ):
                return code
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        return "MODEL_STATUS_INVALID"

    def _status(self, state: ModelState, error_code: str | None = None) -> ModelStatus:
        return ModelStatus(
            state=state,
            model_revision=self.manifest.model_revision,
            artifact_fingerprint=self.manifest.fingerprint,
            total_size_bytes=self.manifest.total_size_bytes,
            error_code=error_code,
        )

    def _model_parent_is_unsafe(self) -> bool:
        return self.model_parent.is_symlink() or not self.model_parent.resolve().is_relative_to(
            self.model_root
        )

    @staticmethod
    def _emit(callback: ProgressCallback | None, progress: ModelProgress) -> None:
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            raise ModelManagerError("MODEL_PROGRESS_CALLBACK_FAILED") from None
