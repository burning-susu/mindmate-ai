"""Add a SQLite guard for the single active backup task."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f39d81c0a64"
down_revision: str | Sequence[str] | None = "d17a5e9c4b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_backups_one_active_create",
        "backups",
        [sa.text("(1)")],
        unique=True,
        sqlite_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_backups_one_active_create", table_name="backups")
