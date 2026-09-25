"""Bind knowledge-base answer versions to validated source snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "a7c9e1f2b304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "citations",
        sa.Column("citation_id", sa.String(length=36), nullable=False),
        sa.Column("answer_version_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("display_number", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("file_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("file_version_snapshot", sa.String(length=64), nullable=True),
        sa.Column("heading_path_snapshot", sa.JSON(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("excerpt_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "source_status",
            sa.String(length=40),
            server_default=sa.text("'AVAILABLE'"),
            nullable=False,
        ),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_version_id"], ["answer_versions.answer_version_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"], ["source_snapshots.source_snapshot_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.chunk_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("citation_id"),
        sa.UniqueConstraint(
            "answer_version_id", "display_number", name="uq_citation_answer_number"
        ),
        sa.UniqueConstraint(
            "answer_version_id", "source_snapshot_id", name="uq_citation_answer_snapshot"
        ),
    )
    op.create_index(
        "ix_citations_answer_version", "citations", ["answer_version_id", "display_number"]
    )
    op.create_index("ix_citations_source_snapshot", "citations", ["source_snapshot_id"])
    op.execute(
        """
        CREATE TRIGGER trg_citations_file_purge
        BEFORE DELETE ON files
        FOR EACH ROW
        BEGIN
            UPDATE citations
            SET file_id = NULL,
                chunk_id = NULL,
                excerpt = NULL,
                excerpt_sha256 = NULL,
                source_status = 'SOURCE_DELETED',
                source_deleted_at = CURRENT_TIMESTAMP
            WHERE file_id = OLD.file_id;
        END;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_citations_file_purge")
    op.drop_index("ix_citations_source_snapshot", table_name="citations")
    op.drop_index("ix_citations_answer_version", table_name="citations")
    op.drop_table("citations")
