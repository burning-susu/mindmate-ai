"""Persist request stages and price snapshots for local budget reconciliation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f78c9e8a1042"
down_revision: str | Sequence[str] | None = "7f39d81c0a64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("ai_operations", "learning_provider_operations"):
        op.add_column(
            table,
            sa.Column(
                "request_stage",
                sa.String(length=30),
                server_default=sa.text("'NOT_SENT'"),
                nullable=False,
            ),
        )
        op.add_column(
            table,
            sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("request_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("reserved_estimate_usd", sa.Numeric(18, 8), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("price_snapshot_json", sa.JSON(), nullable=True),
        )

    op.execute(
        sa.text(
            "UPDATE ai_operations SET request_stage = CASE "
            "WHEN usage_input_tokens IS NOT NULL AND usage_output_tokens IS NOT NULL THEN 'USAGE_KNOWN' "
            "WHEN status IN ('QUEUED', 'PENDING') THEN 'NOT_SENT' ELSE 'UNKNOWN' END "
            "WHERE upper(provider) IN ('DEEPSEEK', 'OPENAI', 'ONLINE')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE learning_provider_operations SET request_stage = CASE "
            "WHEN usage_input_tokens IS NOT NULL AND usage_output_tokens IS NOT NULL THEN 'USAGE_KNOWN' "
            "ELSE 'UNKNOWN' END"
        )
    )


def downgrade() -> None:
    for table in ("learning_provider_operations", "ai_operations"):
        op.drop_column(table, "price_snapshot_json")
        op.drop_column(table, "reserved_estimate_usd")
        op.drop_column(table, "request_sent_at")
        op.drop_column(table, "reserved_at")
        op.drop_column(table, "request_stage")
