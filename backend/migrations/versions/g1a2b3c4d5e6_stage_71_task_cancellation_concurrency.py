"""Persist task cancellation causes for target trash and configurable worker limits."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "f78c9e8a1042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "background_tasks",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_tasks",
        sa.Column("cancel_reason_code", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("background_tasks", "cancel_reason_code")
    op.drop_column("background_tasks", "cancel_requested_at")
