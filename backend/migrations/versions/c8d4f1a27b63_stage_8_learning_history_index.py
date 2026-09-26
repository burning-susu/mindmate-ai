"""Add a partial index for active learning history ordering."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d4f1a27b63"
down_revision: str | Sequence[str] | None = "b4e1c8a09d27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_learning_sessions_active_updated",
        "learning_sessions",
        ["updated_at", "learning_session_id"],
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_learning_sessions_active_updated", table_name="learning_sessions")
