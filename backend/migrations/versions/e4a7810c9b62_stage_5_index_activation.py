"""Record index activation failures without exposing them through the API.

Revision ID: e4a7810c9b62
Revises: d60f2e8a7c31
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a7810c9b62"
down_revision: str | Sequence[str] | None = "d60f2e8a7c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "index_versions",
        sa.Column("activation_error_code", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("index_versions", "activation_error_code")
