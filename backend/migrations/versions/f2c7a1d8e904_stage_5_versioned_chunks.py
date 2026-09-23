"""Add reusable versioned file chunks and chunking checkpoints.

Revision ID: f2c7a1d8e904
Revises: d91f4a6b2c30
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c7a1d8e904"
down_revision: str | Sequence[str] | None = "d91f4a6b2c30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "index_versions",
        sa.Column(
            "chunking_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'NOT_STARTED'"),
        ),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column(
            "chunk_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column("chunk_reason_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "index_version_inputs",
        sa.Column("chunked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_index_version_inputs_chunk_status",
        "index_version_inputs",
        ["index_version_id", "chunk_status"],
    )
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("parse_revision_id", sa.String(length=36), nullable=False),
        sa.Column("chunking_config_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("source_kind", sa.String(length=30), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "length_unit",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'UNICODE_CHARACTER'"),
        ),
        sa.Column("length_value", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chunking_config_id"], ["chunking_configs.chunking_config_id"]),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"]),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.UniqueConstraint(
            "file_id",
            "parse_revision_id",
            "chunking_config_id",
            "sequence_number",
            name="uq_chunk_file_parse_config_sequence",
        ),
    )
    op.create_index(
        "ix_chunks_file_parse_config",
        "chunks",
        ["file_id", "parse_revision_id", "chunking_config_id"],
    )
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_chunks_content_hash", table_name="chunks")
    op.drop_index("ix_chunks_file_parse_config", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(
        "ix_index_version_inputs_chunk_status", table_name="index_version_inputs"
    )
    op.drop_column("index_version_inputs", "chunked_at")
    op.drop_column("index_version_inputs", "chunk_count")
    op.drop_column("index_version_inputs", "chunk_reason_code")
    op.drop_column("index_version_inputs", "chunk_status")
    op.drop_column("index_versions", "chunking_status")
