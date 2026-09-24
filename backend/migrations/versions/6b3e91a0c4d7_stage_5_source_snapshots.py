"""Persist private server-validated retrieval source snapshots.

Revision ID: 6b3e91a0c4d7
Revises: e4a7810c9b62
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b3e91a0c4d7"
down_revision: str | Sequence[str] | None = "e4a7810c9b62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_snapshots",
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column(
            "binding_status",
            sa.String(length=20),
            server_default=sa.text("'UNBOUND'"),
            nullable=False,
        ),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("file_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("file_version_snapshot", sa.String(length=64), nullable=True),
        sa.Column("parse_revision_snapshot", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_content_sha256", sa.String(length=64), nullable=True),
        sa.Column("heading_path_snapshot", sa.JSON(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(excerpt) <= 1200", name="ck_source_snapshot_excerpt_length"),
        sa.CheckConstraint("binding_status = 'UNBOUND'", name="ck_source_snapshot_unbound"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.chunk_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("source_snapshot_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_source_snapshot_idempotency_key"),
    )
    op.create_index(
        "ix_source_snapshots_scope",
        "source_snapshots",
        ["knowledge_base_id", "index_version_id"],
    )
    op.execute(
        """
        CREATE TRIGGER trg_source_snapshots_file_purge
        BEFORE DELETE ON files
        FOR EACH ROW
        BEGIN
            UPDATE source_snapshots
            SET file_id = NULL,
                chunk_id = NULL,
                file_version_snapshot = NULL,
                parse_revision_snapshot = NULL,
                chunk_content_sha256 = NULL,
                excerpt = '',
                excerpt_sha256 = '',
                source_deleted_at = CURRENT_TIMESTAMP
            WHERE file_id = OLD.file_id;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_source_snapshots_file_purge")
    op.drop_index("ix_source_snapshots_scope", table_name="source_snapshots")
    op.drop_table("source_snapshots")
