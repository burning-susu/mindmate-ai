"""stage 4 concurrency and parse failure persistence

Revision ID: 9f3a1c7e2b40
Revises: bc554b1b4366
Create Date: 2026-09-22 20:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f3a1c7e2b40"
down_revision: Union[str, Sequence[str], None] = "bc554b1b4366"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "folders", sa.Column("row_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "tags", sa.Column("row_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column("files", sa.Column("parse_failure_stage", sa.String(length=80)))
    op.add_column("files", sa.Column("parse_error_id", sa.String(length=100)))
    op.add_column(
        "files", sa.Column("parse_retry_count", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_column("parse_retry_count")
        batch_op.drop_column("parse_error_id")
        batch_op.drop_column("parse_failure_stage")
    with op.batch_alter_table("tags") as batch_op:
        batch_op.drop_column("row_version")
    with op.batch_alter_table("folders") as batch_op:
        batch_op.drop_column("row_version")
