"""Create the stage 0 application metadata table."""

from alembic import op
import sqlalchemy as sa

revision = "0001_stage0_app_meta"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.String(length=500), nullable=False),
    )
    op.bulk_insert(
        sa.table("app_meta", sa.column("key", sa.String), sa.column("value", sa.String)),
        [{"key": "schema_version", "value": "0001_stage0_app_meta"}],
    )


def downgrade() -> None:
    op.drop_table("app_meta")
