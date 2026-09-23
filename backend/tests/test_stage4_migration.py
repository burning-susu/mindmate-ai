from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from mindmate.config import Settings

PREVIOUS_REVISION = "bc554b1b4366"
CURRENT_REVISION = "c7d5e8a1f204"


def migration_config(data_dir: Path) -> tuple[Config, Settings]:
    settings = Settings(data_dir=data_dir, env="test")
    config = Config(str(settings.alembic_ini))
    config.attributes["settings"] = settings
    return config, settings


def database_engine(settings: Settings):
    return create_engine(f"sqlite:///{settings.database_path.as_posix()}")


def column_names(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_empty_database_upgrade_downgrade_and_reupgrade(tmp_path: Path) -> None:
    config, settings = migration_config(tmp_path)
    command.upgrade(config, "head")

    engine = database_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_REVISION
        assert connection.scalar(text("PRAGMA quick_check")) == "ok"
    assert "row_version" in column_names(engine, "folders")
    assert "row_version" in column_names(engine, "tags")
    assert {
        "parse_failure_stage",
        "parse_error_id",
        "parse_retry_count",
    }.issubset(column_names(engine, "files"))
    assert {"icon", "color"}.issubset(column_names(engine, "knowledge_bases"))
    engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    engine = database_engine(settings)
    assert "row_version" not in column_names(engine, "folders")
    assert "row_version" not in column_names(engine, "tags")
    assert "parse_retry_count" not in column_names(engine, "files")
    assert "icon" not in column_names(engine, "knowledge_bases")
    engine.dispose()

    command.upgrade(config, "head")
    engine = database_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_REVISION
        assert connection.scalar(text("PRAGMA quick_check")) == "ok"
    engine.dispose()


def test_existing_stage3_data_is_preserved_and_backfilled(tmp_path: Path) -> None:
    config, settings = migration_config(tmp_path)
    command.upgrade(config, PREVIOUS_REVISION)
    engine = database_engine(settings)
    timestamp = "2026-09-22 20:30:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO content_objects (
                    content_object_id, sha256, byte_size, detected_mime_type,
                    storage_relative_path, storage_state, reference_count, created_at
                ) VALUES (
                    'content-1', :sha256, 7, 'text/plain', 'objects/sample.txt',
                    'READY', 1, :timestamp
                )
                """
            ),
            {"sha256": "a" * 64, "timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO folders (
                    folder_id, parent_folder_id, name, normalized_name, sort_order,
                    created_at, updated_at
                ) VALUES ('folder-1', NULL, '资料', '资料', 0, :timestamp, :timestamp)
                """
            ),
            {"timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_bases (
                    knowledge_base_id, name, description, status, active_index_version_id,
                    created_at, updated_at, row_version
                ) VALUES (
                    'kb-1', '已有知识库', '迁移前数据', 'EMPTY', NULL,
                    :timestamp, :timestamp, 2
                )
                """
            ),
            {"timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO tags (tag_id, name, normalized_name, color, created_at, updated_at)
                VALUES ('tag-1', '重点', '重点', '#176b87', :timestamp, :timestamp)
                """
            ),
            {"timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO files (
                    file_id, content_object_id, display_name, extension, document_type,
                    folder_id, status, source_name, content_hash, byte_size,
                    parse_revision_id, created_at, updated_at, row_version
                ) VALUES (
                    'file-1', 'content-1', 'sample.txt', '.txt', 'TXT', 'folder-1',
                    'PARSED', 'sample.txt', :sha256, 7, 'parse-1', :timestamp, :timestamp, 3
                )
                """
            ),
            {"sha256": "a" * 64, "timestamp": timestamp},
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = database_engine(settings)
    with engine.connect() as connection:
        folder = connection.execute(
            text("SELECT name, row_version FROM folders WHERE folder_id = 'folder-1'")
        ).one()
        tag = connection.execute(
            text("SELECT name, row_version FROM tags WHERE tag_id = 'tag-1'")
        ).one()
        file_record = connection.execute(
            text(
                """
                SELECT display_name, row_version, parse_failure_stage,
                       parse_error_id, parse_retry_count
                FROM files WHERE file_id = 'file-1'
                """
            )
        ).one()
        assert tuple(folder) == ("资料", 1)
        assert tuple(tag) == ("重点", 1)
        assert tuple(file_record) == ("sample.txt", 3, None, None, 0)
        knowledge_base = connection.execute(
            text(
                "SELECT name, description, icon, color, row_version "
                "FROM knowledge_bases WHERE knowledge_base_id = 'kb-1'"
            )
        ).one()
        assert tuple(knowledge_base) == ("已有知识库", "迁移前数据", None, None, 2)
        assert connection.scalar(text("PRAGMA quick_check")) == "ok"
    engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    engine = database_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT COUNT(*) FROM folders WHERE folder_id = 'folder-1'")
        ) == 1
        assert connection.scalar(text("SELECT row_version FROM folders")) == 1
        assert connection.scalar(text("SELECT parse_retry_count FROM files")) == 0
        assert connection.scalar(
            text("SELECT COUNT(*) FROM knowledge_bases WHERE knowledge_base_id = 'kb-1'")
        ) == 1
        assert connection.scalar(text("PRAGMA quick_check")) == "ok"
    engine.dispose()
