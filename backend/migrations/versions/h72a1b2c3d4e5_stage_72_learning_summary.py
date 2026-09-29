"""Persist deterministic learning summary snapshots for history and restart reads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h72a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_session_summaries",
        sa.Column("summary_id", sa.String(length=36), nullable=False),
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("summary_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learning_session_id"],
            ["learning_sessions.learning_session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("summary_id"),
        sa.UniqueConstraint(
            "learning_session_id", name="uq_learning_session_summary_session"
        ),
    )
    op.create_index(
        "ix_learning_session_summaries_session",
        "learning_session_summaries",
        ["learning_session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_session_summaries_session",
        table_name="learning_session_summaries",
    )
    op.drop_table("learning_session_summaries")
