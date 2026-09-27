"""Add a local history full-text projection.

The migration creates the projection tables only. It does not scan existing
messages or questions. A bounded backfill marks the index READY after it
catches up; startup must not wait for that scan.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a50e7c1b9d44"
down_revision: str | Sequence[str] | None = "c8d4f1a27b63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_search_state",
        sa.Column("state_key", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("state_key"),
    )
    op.execute(
        "INSERT INTO history_search_state (state_key, status, error_code, updated_at) "
        "VALUES ('projection', 'PENDING', NULL, CURRENT_TIMESTAMP)"
    )
    op.create_table(
        "history_search_owners",
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("owner_type", "owner_id"),
    )
    op.create_table(
        "history_search_documents",
        sa.Column("document_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint(
            "owner_type", "section", "source_id", name="uq_history_search_source"
        ),
    )
    op.create_index(
        "ix_history_search_owner",
        "history_search_documents",
        ["owner_type", "owner_id"],
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE history_search_fts USING fts5(
            content UNINDEXED,
            han_bigrams,
            han_unigrams,
            terms,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_history_search_conversation_delete
        AFTER DELETE ON conversations
        BEGIN
            DELETE FROM history_search_fts
            WHERE rowid IN (
                SELECT document_id FROM history_search_documents
                WHERE owner_type = 'conversation' AND owner_id = OLD.conversation_id
            );
            DELETE FROM history_search_documents
            WHERE owner_type = 'conversation' AND owner_id = OLD.conversation_id;
            DELETE FROM history_search_owners
            WHERE owner_type = 'conversation' AND owner_id = OLD.conversation_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_history_search_learning_delete
        AFTER DELETE ON learning_sessions
        BEGIN
            DELETE FROM history_search_fts
            WHERE rowid IN (
                SELECT document_id FROM history_search_documents
                WHERE owner_type = 'learning' AND owner_id = OLD.learning_session_id
            );
            DELETE FROM history_search_documents
            WHERE owner_type = 'learning' AND owner_id = OLD.learning_session_id;
            DELETE FROM history_search_owners
            WHERE owner_type = 'learning' AND owner_id = OLD.learning_session_id;
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_history_search_learning_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_history_search_conversation_delete")
    op.execute("DROP TABLE IF EXISTS history_search_fts")
    op.drop_index("ix_history_search_owner", table_name="history_search_documents")
    op.drop_table("history_search_documents")
    op.drop_table("history_search_owners")
    op.drop_table("history_search_state")
