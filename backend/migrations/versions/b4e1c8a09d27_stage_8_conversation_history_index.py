"""Add a partial index for active conversation history ordering."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e1c8a09d27"
down_revision: str | Sequence[str] | None = "e8b2c41d7a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_conversations_active_last_active",
        "conversations",
        ["last_active_at", "conversation_id"],
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_active_last_active", table_name="conversations")
