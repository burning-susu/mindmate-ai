from __future__ import annotations

import os
from collections.abc import MutableMapping
from threading import RLock
from typing import Protocol

import keyring
from keyring.errors import PasswordDeleteError

CREDENTIAL_SERVICE = "MindMateAI"


class CredentialStoreError(RuntimeError):
    """Raised when the configured operating-system credential store is unavailable."""

    def __init__(self, code: str = "CREDENTIAL_STORE_UNAVAILABLE") -> None:
        super().__init__(code)
        self.code = code


class CredentialStorePort(Protocol):
    def set_secret(self, secret_reference: str, secret: str) -> None: ...

    def get_secret(self, secret_reference: str) -> str | None: ...

    def has_secret(self, secret_reference: str) -> bool: ...

    def delete_secret(self, secret_reference: str) -> None: ...


class WindowsCredentialStore:
    """Use Windows Credential Manager through keyring without a disk fallback."""

    def __init__(self, keyring_module=keyring) -> None:
        self._keyring = keyring_module
        self._lock = RLock()

    def _ensure_windows_backend(self) -> None:
        if os.name != "nt":
            raise CredentialStoreError("WINDOWS_CREDENTIAL_MANAGER_UNAVAILABLE")
        try:
            backend = self._keyring.get_keyring()
            module_name = backend.__class__.__module__
        except Exception as exc:  # pragma: no cover - backend-specific failure
            raise CredentialStoreError() from exc
        if not module_name.startswith("keyring.backends.Windows"):
            raise CredentialStoreError("WINDOWS_CREDENTIAL_MANAGER_UNAVAILABLE")

    def set_secret(self, secret_reference: str, secret: str) -> None:
        if not secret_reference or not secret:
            raise CredentialStoreError("CREDENTIAL_VALUE_INVALID")
        with self._lock:
            self._ensure_windows_backend()
            try:
                self._keyring.set_password(CREDENTIAL_SERVICE, secret_reference, secret)
                stored = self._keyring.get_password(CREDENTIAL_SERVICE, secret_reference)
            except Exception as exc:  # pragma: no cover - backend-specific failure
                raise CredentialStoreError() from exc
            if stored != secret:
                raise CredentialStoreError("CREDENTIAL_WRITE_NOT_VERIFIED")

    def get_secret(self, secret_reference: str) -> str | None:
        if not secret_reference:
            return None
        with self._lock:
            self._ensure_windows_backend()
            try:
                return self._keyring.get_password(CREDENTIAL_SERVICE, secret_reference)
            except Exception as exc:  # pragma: no cover - backend-specific failure
                raise CredentialStoreError() from exc

    def has_secret(self, secret_reference: str) -> bool:
        value = self.get_secret(secret_reference)
        return bool(value)

    def delete_secret(self, secret_reference: str) -> None:
        if not secret_reference:
            return
        with self._lock:
            self._ensure_windows_backend()
            try:
                if self._keyring.get_password(CREDENTIAL_SERVICE, secret_reference) is None:
                    return
                self._keyring.delete_password(CREDENTIAL_SERVICE, secret_reference)
            except PasswordDeleteError:
                return
            except Exception as exc:  # pragma: no cover - backend-specific failure
                raise CredentialStoreError() from exc


class InMemoryCredentialStore:
    """Explicit isolated fake used by tests and local HTTP fixtures."""

    def __init__(self) -> None:
        self._values: MutableMapping[str, str] = {}
        self._lock = RLock()

    def set_secret(self, secret_reference: str, secret: str) -> None:
        if not secret_reference or not secret:
            raise CredentialStoreError("CREDENTIAL_VALUE_INVALID")
        with self._lock:
            self._values[secret_reference] = secret

    def get_secret(self, secret_reference: str) -> str | None:
        with self._lock:
            return self._values.get(secret_reference)

    def has_secret(self, secret_reference: str) -> bool:
        with self._lock:
            return bool(self._values.get(secret_reference))

    def delete_secret(self, secret_reference: str) -> None:
        with self._lock:
            self._values.pop(secret_reference, None)


__all__ = [
    "CREDENTIAL_SERVICE",
    "CredentialStoreError",
    "CredentialStorePort",
    "InMemoryCredentialStore",
    "WindowsCredentialStore",
]
