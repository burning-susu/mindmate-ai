"""Persist idempotent multi-question generation state.

The session fields let a restarted client distinguish a pending next-question
request from a completed question. The partial unique index protects replayed
generation requests while leaving legacy NULL values unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d17a5e9c4b20"
down_revision: str | Sequence[str] | None = "b55c0e1a8d27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learning_sessions") as batch:
        batch.add_column(sa.Column("pending_question_request_id", sa.String(length=128)))
        batch.add_column(sa.Column("pending_question_request_hash", sa.String(length=64)))
    with op.batch_alter_table("learning_questions") as batch:
        batch.add_column(sa.Column("generated_request_hash", sa.String(length=64)))
    op.create_index(
        "uq_learning_question_generated_request",
        "learning_questions",
        ["learning_session_id", "generated_request_id"],
        unique=True,
        sqlite_where=sa.text("generated_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_learning_question_generated_request", table_name="learning_questions"
    )
    with op.batch_alter_table("learning_questions") as batch:
        batch.drop_column("generated_request_hash")
    with op.batch_alter_table("learning_sessions") as batch:
        batch.drop_column("pending_question_request_hash")
        batch.drop_column("pending_question_request_id")
