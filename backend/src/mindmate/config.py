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
    parser_timeout_seconds: float = 30.0
    parser_memory_limit_bytes: int = 512 * 1024 * 1024
    parse_worker_poll_seconds: float = 0.1
    parse_worker_lease_seconds: int = 60
    parse_worker_max_retries: int = 2
    knowledge_worker_poll_seconds: float = 0.1
    knowledge_worker_lease_seconds: int = 60
    index_worker_poll_seconds: float = 0.1
    index_worker_lease_seconds: int = 60
    index_chunk_worker_poll_seconds: float = 0.1
    index_chunk_worker_lease_seconds: int = 60
    index_embedding_worker_poll_seconds: float = 0.1
    index_embedding_worker_lease_seconds: int = 60
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

    @property
    def model_dir(self) -> Path:
        return self.resolved_data_dir / "models"

    @property
    def vectors_dir(self) -> Path:
        return self.resolved_data_dir / "vectors"

    def ensure_data_dirs(self) -> None:
        for name in (
            "database",
            "objects",
            "parsed",
            "vectors",
            "previews",
            "tasks",
            "backups",
            "models",
            "logs",
            "cache",
            "config",
            "runtime",
        ):
            (self.resolved_data_dir / name).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
