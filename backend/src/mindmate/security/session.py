from __future__ import annotations

import secrets

SESSION_COOKIE = "mindmate_session"


class LocalSession:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)

    def matches(self, value: str | None) -> bool:
        return bool(value) and secrets.compare_digest(value, self.token)
