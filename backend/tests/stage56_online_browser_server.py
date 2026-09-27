from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from mindmate.config import Settings
from mindmate.infrastructure.db import create_session_factory, create_sqlite_engine
from mindmate.main import create_app
from test_stage5_source_snapshots import _seed_active_index
from test_stage7_learning_session import PUBLIC_FILE, _Encoder, _Query, _supported_public


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--api-port", default=8001, type=int)
    parser.add_argument("--web-port", default=5174, type=int)
    args = parser.parse_args()

    settings = Settings(
        data_dir=args.data_dir,
        env="test",
        learning_provider_fixture=True,
        allowed_origins=(f"http://127.0.0.1:{args.web_port}",),
        parse_worker_poll_seconds=60,
        knowledge_worker_poll_seconds=60,
        index_worker_poll_seconds=60,
        index_chunk_worker_poll_seconds=60,
        index_embedding_worker_poll_seconds=60,
        index_fts_worker_poll_seconds=60,
        index_activation_worker_poll_seconds=60,
        chat_worker_poll_seconds=60,
        history_purge_poll_seconds=60,
        task_retention_poll_seconds=60,
    )
    settings.ensure_data_dirs()
    alembic = Config(str(settings.alembic_ini))
    alembic.attributes["settings"] = settings
    command.upgrade(alembic, "head")

    engine = create_sqlite_engine(settings.database_path)
    factory = create_session_factory(engine)
    content = PUBLIC_FILE.read_text(encoding="utf-8")
    data = _seed_active_index(
        factory,
        settings,
        content=content,
        display_name="服务超时策略.txt",
    )
    engine.dispose()

    app = create_app(settings)
    app.state.learning_encoder_getter = _Encoder
    app.state.learning_query_getter = lambda _settings: _Query(_supported_public(data, content))
    print(f"STAGE56_REAL_KB_ID={data.knowledge_base_id}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.api_port, log_level="warning")


if __name__ == "__main__":
    main()
