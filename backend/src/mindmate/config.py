from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINDMATE_", env_file=".env", extra="ignore")

    env: str = "development"
    data_dir: Path | None = None
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    provider_mode: str = "mock"
    provider_base_url: str = "https://api.deepseek.com"
    provider_model: str = "deepseek-flash"
    log_level: str = "INFO"
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    alembic_ini: Path = Path(__file__).resolve().parents[2] / "alembic.ini"

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return self.data_dir.expanduser().resolve()
        return (Path.home() / "AppData" / "Local" / "MindMateAI").resolve()

    @property
    def database_path(self) -> Path:
        return self.resolved_data_dir / "database" / "mindmate.db"

    @property
    def runtime_dir(self) -> Path:
        return self.resolved_data_dir / "runtime"

    def ensure_data_dirs(self) -> None:
        for name in (
            "database",
            "objects",
            "parsed",
            "vectors",
            "previews",
            "tasks",
            "backups",
            "logs",
            "cache",
            "config",
            "runtime",
        ):
            (self.resolved_data_dir / name).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
