"""Add a recoverable per-IndexVersion FTS5 projection.

Revision ID: d60f2e8a7c31
Revises: a81f3c6d2e90
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d60f2e8a7c31"
down_revision: str | Sequence[str] | None = "a81f3c6d2e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "index_versions",
        sa.Column(
            "fts_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'NOT_STARTED'"),
        ),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column(
            "fts_status", sa.String(length=30), nullable=False, server_default=sa.text("'PENDING'")
        ),
    )
    op.add_column(
        "index_version_inputs", sa.Column("fts_reason_code", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "index_version_inputs",
        sa.Column("fts_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "index_version_inputs", sa.Column("fts_indexed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_index_version_inputs_fts_status",
        "index_version_inputs",
        ["index_version_id", "fts_status"],
    )
    op.create_index(
        "uq_background_tasks_single_running_fts",
        "background_tasks",
        ["task_type"],
        unique=True,
        sqlite_where=sa.text("task_type = 'INDEX_FTS' AND status = 'RUNNING'"),
    )
    op.create_table(
        "fts_chunk_map",
        sa.Column("fts_row_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("parse_revision_id", sa.String(length=36), nullable=False),
        sa.Column("chunking_config_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["index_version_id"], ["index_versions.index_version_id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.chunk_id"]),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"]),
        sa.ForeignKeyConstraint(
            ["chunking_config_id"], ["chunking_configs.chunking_config_id"]
        ),
        sa.PrimaryKeyConstraint("fts_row_id"),
        sa.UniqueConstraint(
            "index_version_id", "chunk_id", name="uq_fts_chunk_version_chunk"
        ),
    )
    op.create_index(
        "ix_fts_chunk_map_version_file", "fts_chunk_map", ["index_version_id", "file_id"]
    )
    op.create_index("ix_fts_chunk_map_chunk", "fts_chunk_map", ["chunk_id"])
    op.execute(
        """
        CREATE VIRTUAL TABLE index_chunk_fts USING fts5(
            content UNINDEXED,
            han_bigrams,
            han_unigrams,
            terms,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )


def downgrade() -> None:
    # FTS rows are derived and can be rebuilt from Chunk; this downgrade does not
    # touch authoritative Chunk, EmbeddingRecord, or vector data.
    op.execute("DROP TABLE index_chunk_fts")
    op.drop_index("ix_fts_chunk_map_chunk", table_name="fts_chunk_map")
    op.drop_index("ix_fts_chunk_map_version_file", table_name="fts_chunk_map")
    op.drop_table("fts_chunk_map")
    op.drop_index(
        "uq_background_tasks_single_running_fts", table_name="background_tasks"
    )
    op.drop_index("ix_index_version_inputs_fts_status", table_name="index_version_inputs")
    op.drop_column("index_version_inputs", "fts_indexed_at")
    op.drop_column("index_version_inputs", "fts_count")
    op.drop_column("index_version_inputs", "fts_reason_code")
    op.drop_column("index_version_inputs", "fts_status")
    op.drop_column("index_versions", "fts_status")
