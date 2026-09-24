from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from mindmate.config import Settings

PREVIOUS_REVISION = "bc554b1b4366"
CURRENT_REVISION = "6b3e91a0c4d7"


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
    assert {
        "chunking_configs",
        "embedding_configs",
        "index_versions",
        "index_version_inputs",
        "chunks",
        "fts_chunk_map",
    }.issubset(set(inspect(engine).get_table_names()))
    assert "chunking_status" in column_names(engine, "index_versions")
    assert {
        "chunk_status",
        "chunk_reason_code",
        "chunk_count",
        "chunked_at",
    }.issubset(column_names(engine, "index_version_inputs"))
    assert "fts_status" in column_names(engine, "index_versions")
    assert {
        "fts_status",
        "fts_reason_code",
        "fts_count",
        "fts_indexed_at",
    }.issubset(column_names(engine, "index_version_inputs"))
    with engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='index_chunk_fts'"
            )
        ) == 1
    engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    engine = database_engine(settings)
    assert "row_version" not in column_names(engine, "folders")
    assert "row_version" not in column_names(engine, "tags")
    assert "parse_retry_count" not in column_names(engine, "files")
    assert "icon" not in column_names(engine, "knowledge_bases")
    assert "index_versions" not in inspect(engine).get_table_names()
    assert "fts_chunk_map" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT COUNT(*) FROM sqlite_master WHERE name='index_chunk_fts'")
        ) == 0
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


def test_stage9_membership_and_task_data_survive_index_schema_upgrade(tmp_path: Path) -> None:
    config, settings = migration_config(tmp_path)
    command.upgrade(config, "c7d5e8a1f204")
    engine = database_engine(settings)
    timestamp = "2026-09-23 08:00:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO content_objects (
                    content_object_id, sha256, byte_size, detected_mime_type,
                    storage_relative_path, storage_state, reference_count, created_at
                ) VALUES ('content-9', :sha256, 9, 'text/plain', 'objects/nine.txt',
                          'READY', 1, :timestamp)
                """
            ),
            {"sha256": "9" * 64, "timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO files (
                    file_id, content_object_id, display_name, extension, document_type,
                    folder_id, status, source_name, content_hash, byte_size,
                    parse_revision_id, parse_failure_stage, parse_error_id, parse_retry_count,
                    created_at, updated_at, row_version
                ) VALUES ('file-9', 'content-9', 'nine.txt', '.txt', 'TXT', NULL,
                          'PARSED', 'nine.txt', :sha256, 9, 'parse-9', NULL, NULL, 0,
                          :timestamp, :timestamp, 1)
                """
            ),
            {"sha256": "9" * 64, "timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_bases (
                    knowledge_base_id, name, description, icon, color, status,
                    active_index_version_id, created_at, updated_at, deleted_at,
                    purge_after, row_version
                ) VALUES ('kb-9', '第九批知识库', NULL, 'book-open', '#176b87',
                          'PREPARING', NULL, :timestamp, :timestamp, NULL, NULL, 2)
                """
            ),
            {"timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_base_files (
                    knowledge_base_file_id, knowledge_base_id, file_id, membership_status,
                    index_state, added_at, removed_at
                ) VALUES ('member-9', 'kb-9', 'file-9', 'ACTIVE', 'PENDING', :timestamp, NULL)
                """
            ),
            {"timestamp": timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO background_tasks (
                    task_id, task_type, status, phase, priority, progress, idempotency_key,
                    parent_task_id, checkpoint_version, checkpoint_json, error_summary,
                    lease_owner, lease_until, created_at, updated_at, started_at,
                    completed_at, row_version
                ) VALUES ('task-9', 'KNOWLEDGE_MEMBERSHIP_ADD', 'QUEUED', NULL, 0, NULL,
                          'stage9-task', NULL, 0, '{}', NULL, NULL, NULL, :timestamp,
                          :timestamp, NULL, NULL, 1)
                """
            ),
            {"timestamp": timestamp},
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = database_engine(settings)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == CURRENT_REVISION
        assert connection.scalar(
            text("SELECT membership_status FROM knowledge_base_files WHERE knowledge_base_file_id='member-9'")
        ) == "ACTIVE"
        assert connection.scalar(
            text("SELECT status FROM background_tasks WHERE task_id='task-9'")
        ) == "QUEUED"
        assert connection.scalar(
            text("SELECT active_index_version_id FROM knowledge_bases WHERE knowledge_base_id='kb-9'")
        ) is None
        assert connection.scalar(text("PRAGMA quick_check")) == "ok"
    engine.dispose()
