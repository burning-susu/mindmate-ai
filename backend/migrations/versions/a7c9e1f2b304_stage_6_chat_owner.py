"""Persist the stage 6 general chat owner and generation boundary."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9e1f2b304"
down_revision: str | Sequence[str] | None = "6b3e91a0c4d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("title_source", sa.String(length=20), server_default=sa.text("'AUTO'"), nullable=False),
        sa.Column("current_mode", sa.String(length=30), server_default=sa.text("'GENERAL_CHAT'"), nullable=False),
        sa.Column("current_scope_type", sa.String(length=30), server_default=sa.text("'NONE'"), nullable=False),
        sa.Column("current_scope_id_list", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "ix_conversations_status_updated", "conversations", ["status", "updated_at"]
    )

    op.create_table(
        "conversation_scopes",
        sa.Column("conversation_scope_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("scope_version", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=True),
        sa.Column("index_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.conversation_id"]),
        sa.PrimaryKeyConstraint("conversation_scope_id"),
        sa.UniqueConstraint("conversation_id", "scope_version", name="uq_conversation_scope_version"),
    )
    op.create_index(
        "ix_conversation_scopes_conversation",
        "conversation_scopes",
        ["conversation_id", "scope_version"],
    )

    op.create_table(
        "messages",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("mode_snapshot", sa.String(length=30), nullable=False),
        sa.Column("conversation_scope_id", sa.String(length=36), nullable=True),
        sa.Column("parent_user_message_id", sa.String(length=36), nullable=True),
        sa.Column("revision_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.conversation_id"]),
        sa.ForeignKeyConstraint(
            ["conversation_scope_id"], ["conversation_scopes.conversation_scope_id"]
        ),
        sa.ForeignKeyConstraint(["parent_user_message_id"], ["messages.message_id"]),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint("conversation_id", "sequence_number", name="uq_message_conversation_sequence"),
    )
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )
    op.create_index(
        "ix_messages_conversation_status", "messages", ["conversation_id", "status"]
    )

    op.create_table(
        "ai_operations",
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_message_id", sa.String(length=36), nullable=False),
        sa.Column("assistant_message_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
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
        sa.ForeignKeyConstraint(["assistant_message_id"], ["messages.message_id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.conversation_id"]),
        sa.ForeignKeyConstraint(["task_id"], ["background_tasks.task_id"]),
        sa.ForeignKeyConstraint(["user_message_id"], ["messages.message_id"]),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ai_operation_idempotency_key"),
        sa.UniqueConstraint("client_request_id", name="uq_ai_operation_client_request_id"),
        sa.UniqueConstraint("task_id", name="uq_ai_operation_task_id"),
    )
    op.create_index(
        "ix_ai_operations_conversation_status",
        "ai_operations",
        ["conversation_id", "status"],
    )

    op.create_table(
        "answer_versions",
        sa.Column("answer_version_id", sa.String(length=36), nullable=False),
        sa.Column("assistant_message_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=80), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=True),
        sa.Column("usage_input_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_output_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_total_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["messages.message_id"]),
        sa.PrimaryKeyConstraint("answer_version_id"),
        sa.UniqueConstraint(
            "assistant_message_id", "version_number", name="uq_answer_version_message_number"
        ),
    )
    op.create_index(
        "ix_answer_versions_assistant",
        "answer_versions",
        ["assistant_message_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_answer_versions_assistant", table_name="answer_versions")
    op.drop_table("answer_versions")
    op.drop_index("ix_ai_operations_conversation_status", table_name="ai_operations")
    op.drop_table("ai_operations")
    op.drop_index("ix_messages_conversation_status", table_name="messages")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversation_scopes_conversation", table_name="conversation_scopes")
    op.drop_table("conversation_scopes")
    op.drop_index("ix_conversations_status_updated", table_name="conversations")
    op.drop_table("conversations")
