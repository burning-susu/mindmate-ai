"""Persist learning Provider calls separately from chat operations.

Chat AiOperation rows require a conversation and two messages. Learning calls
keep their own ledger so a restart can see that a paid request was already
committed, without inventing a chat transcript.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b55c0e1a8d27"
down_revision: str | Sequence[str] | None = "a50e7c1b9d44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learning_sessions") as batch:
        batch.add_column(sa.Column("requested_model", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("resolved_model", sa.String(length=200), nullable=True))
    with op.batch_alter_table("learning_feedbacks") as batch:
        batch.add_column(
            sa.Column(
                "explanation_origin",
                sa.String(length=40),
                nullable=False,
                server_default="local_rule",
            )
        )
        batch.add_column(
            sa.Column(
                "live_model_called",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
    op.create_table(
        "learning_provider_operations",
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=True),
        sa.Column("attempt_id", sa.String(length=36), nullable=True),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("client_request_id", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("requested_model", sa.String(length=100), nullable=False),
        sa.Column("resolved_model", sa.String(length=200), nullable=True),
        sa.Column("prompt_template_version", sa.String(length=80), nullable=False),
        sa.Column("usage_input_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_output_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_total_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.learning_session_id"]
        ),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_learning_provider_operation_idempotency"),
        sa.UniqueConstraint("client_request_id", name="uq_learning_provider_operation_client"),
    )
    op.create_index(
        "ix_learning_provider_operations_session",
        "learning_provider_operations",
        ["learning_session_id", "task_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_provider_operations_session", table_name="learning_provider_operations"
    )
    op.drop_table("learning_provider_operations")
    with op.batch_alter_table("learning_feedbacks") as batch:
        batch.drop_column("live_model_called")
        batch.drop_column("explanation_origin")
    with op.batch_alter_table("learning_sessions") as batch:
        batch.drop_column("resolved_model")
        batch.drop_column("requested_model")
