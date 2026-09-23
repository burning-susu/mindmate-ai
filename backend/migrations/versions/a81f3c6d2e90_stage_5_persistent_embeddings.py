"""Add persistent embedding records and per-input embedding checkpoints.

Revision ID: a81f3c6d2e90
Revises: f2c7a1d8e904
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a81f3c6d2e90"
down_revision: str | Sequence[str] | None = "f2c7a1d8e904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_background_tasks_single_running_embedding",
        "background_tasks",
        ["task_type"],
        unique=True,
        sqlite_where=sa.text("task_type = 'INDEX_EMBED' AND status = 'RUNNING'"),
    )
    op.add_column(
        "index_versions",
        sa.Column(
            "embedding_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'NOT_STARTED'"),
        ),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column(
            "embedding_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column("embedding_reason_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column(
            "embedding_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_index_version_inputs_embedding_status",
        "index_version_inputs",
        ["index_version_id", "embedding_status"],
    )
    op.create_table(
        "embedding_records",
        sa.Column("embedding_record_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_config_id", sa.String(length=36), nullable=False),
        sa.Column("vector_store_record_id", sa.String(length=36), nullable=False),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("vector_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.chunk_id"]),
        sa.ForeignKeyConstraint(
            ["embedding_config_id"], ["embedding_configs.embedding_config_id"]
        ),
        sa.PrimaryKeyConstraint("embedding_record_id"),
        sa.UniqueConstraint("chunk_id", "embedding_config_id", name="uq_embedding_record_chunk_config"),
        sa.UniqueConstraint("vector_store_record_id"),
    )
    op.create_index(
        "ix_embedding_records_chunk_config_status",
        "embedding_records",
        ["chunk_id", "embedding_config_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_embedding_records_chunk_config_status", table_name="embedding_records")
    op.drop_table("embedding_records")
    op.drop_index(
        "ix_index_version_inputs_embedding_status", table_name="index_version_inputs"
    )
    op.drop_column("index_version_inputs", "embedded_at")
    op.drop_column("index_version_inputs", "embedding_count")
    op.drop_column("index_version_inputs", "embedding_reason_code")
    op.drop_column("index_version_inputs", "embedding_status")
    op.drop_column("index_versions", "embedding_status")
    op.drop_index(
        "uq_background_tasks_single_running_embedding", table_name="background_tasks"
    )
