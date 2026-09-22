from __future__ import annotations

import uuid

import keyring


def run() -> None:
    service = f"MindMateAI-Spike-{uuid.uuid4()}"
    username = "stage1-test"
    secret = "stage1-ephemeral-secret"
    keyring.set_password(service, username, secret)
    assert keyring.get_password(service, username) == secret
    keyring.delete_password(service, username)
    assert keyring.get_password(service, username) is None
    print(f"credential-manager PASS: backend={keyring.get_keyring().__class__.__name__}")


if __name__ == "__main__":
    run()
