"""stage 5 knowledge base presentation fields

Revision ID: c7d5e8a1f204
Revises: 9f3a1c7e2b40
Create Date: 2026-09-23 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d5e8a1f204"
down_revision: Union[str, Sequence[str], None] = "9f3a1c7e2b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_bases", sa.Column("icon", sa.String(length=50)))
    op.add_column("knowledge_bases", sa.Column("color", sa.String(length=20)))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_bases") as batch_op:
        batch_op.drop_column("color")
        batch_op.drop_column("icon")
