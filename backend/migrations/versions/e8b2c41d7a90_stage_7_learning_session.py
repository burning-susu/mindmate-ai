"""Persist a minimal evidence-backed learning session, question, and feedback."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8b2c41d7a90"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CITATION_PURGE_TRIGGER = """
CREATE TRIGGER trg_citations_file_purge
BEFORE DELETE ON files
FOR EACH ROW
BEGIN
    UPDATE citations
    SET file_id = NULL,
        chunk_id = NULL,
        excerpt = NULL,
        excerpt_sha256 = NULL,
        source_status = 'SOURCE_DELETED',
        source_deleted_at = CURRENT_TIMESTAMP
    WHERE file_id = OLD.file_id;
END;
"""


def upgrade() -> None:
    op.create_table(
        "learning_sessions",
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=80), nullable=False),
        sa.Column("goal_type", sa.String(length=40), server_default=sa.text("'CUSTOM'"), nullable=False),
        sa.Column("goal_text", sa.String(length=200), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("target_question_count", sa.Integer(), nullable=False),
        sa.Column("initial_difficulty", sa.String(length=20), server_default=sa.text("'BASIC'"), nullable=False),
        sa.Column("current_difficulty", sa.String(length=20), server_default=sa.text("'BASIC'"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("end_reason", sa.String(length=40), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_detail", sa.String(length=500), nullable=True),
        sa.Column("completed_question_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("current_knowledge_point_id", sa.String(length=36), nullable=True),
        sa.Column("current_question_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=50), server_default=sa.text("'mock'"), nullable=False),
        sa.Column("live_model_called", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("learning_session_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_learning_session_idempotency_key"),
        sa.UniqueConstraint("client_request_id", name="uq_learning_session_client_request_id"),
    )
    op.create_index(
        "ix_learning_sessions_status", "learning_sessions", ["status", "updated_at"]
    )
    op.create_table(
        "learning_scopes",
        sa.Column("learning_scope_id", sa.String(length=36), nullable=False),
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=36), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=True),
        sa.Column("source_set_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.learning_session_id"]
        ),
        sa.PrimaryKeyConstraint("learning_scope_id"),
        sa.UniqueConstraint("learning_session_id", name="uq_learning_scope_session"),
    )
    op.create_table(
        "learning_scope_files",
        sa.Column("learning_scope_file_id", sa.String(length=36), nullable=False),
        sa.Column("learning_scope_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parse_revision_id", sa.String(length=36), nullable=True),
        sa.Column("index_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["learning_scope_id"], ["learning_scopes.learning_scope_id"]),
        sa.PrimaryKeyConstraint("learning_scope_file_id"),
        sa.UniqueConstraint("learning_scope_id", "file_id", name="uq_learning_scope_file"),
    )
    op.create_table(
        "knowledge_points",
        sa.Column("knowledge_point_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_title", sa.String(length=80), nullable=False),
        sa.Column("normalized_title", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("scope_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("source_set_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("knowledge_point_id"),
    )
    op.create_table(
        "knowledge_point_evidence",
        sa.Column("knowledge_point_evidence_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_point_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.knowledge_point_id"]),
        sa.PrimaryKeyConstraint("knowledge_point_evidence_id"),
    )
    op.create_table(
        "learning_plans",
        sa.Column("learning_plan_id", sa.String(length=36), nullable=False),
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("target_question_count", sa.Integer(), nullable=False),
        sa.Column("question_type_mix_json", sa.JSON(), nullable=False),
        sa.Column("source_set_hash", sa.String(length=64), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.learning_session_id"]
        ),
        sa.PrimaryKeyConstraint("learning_plan_id"),
        sa.UniqueConstraint(
            "learning_session_id", "plan_version", name="uq_learning_plan_version"
        ),
    )
    op.create_table(
        "learning_plan_items",
        sa.Column("learning_plan_item_id", sa.String(length=36), nullable=False),
        sa.Column("learning_plan_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_point_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("target_question_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.knowledge_point_id"]),
        sa.ForeignKeyConstraint(["learning_plan_id"], ["learning_plans.learning_plan_id"]),
        sa.PrimaryKeyConstraint("learning_plan_item_id"),
        sa.UniqueConstraint(
            "learning_plan_id", "sequence_number", name="uq_learning_plan_item_sequence"
        ),
    )
    op.create_table(
        "learning_questions",
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_point_id", sa.String(length=36), nullable=False),
        sa.Column("question_type", sa.String(length=30), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("answer_key_json", sa.JSON(), nullable=False),
        sa.Column("acceptable_points_json", sa.JSON(), nullable=True),
        sa.Column("grading_rule_json", sa.JSON(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("generated_request_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_template_version", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.knowledge_point_id"]),
        sa.ForeignKeyConstraint(
            ["learning_session_id"], ["learning_sessions.learning_session_id"]
        ),
        sa.PrimaryKeyConstraint("question_id"),
        sa.UniqueConstraint(
            "learning_session_id", "sequence_number", name="uq_learning_question_sequence"
        ),
    )
    op.create_table(
        "question_evidence",
        sa.Column("question_evidence_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=36), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_role", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["learning_questions.question_id"]),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshots.source_snapshot_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("question_evidence_id"),
    )
    op.create_table(
        "learning_attempts",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("learning_session_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("answer_content", sa.Text(), nullable=True),
        sa.Column("selected_option", sa.String(length=32), nullable=False),
        sa.Column("hint_level_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["learning_session_id"], ["learning_sessions.learning_session_id"]),
        sa.ForeignKeyConstraint(["question_id"], ["learning_questions.question_id"]),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("question_id", "attempt_number", name="uq_learning_attempt_number"),
        sa.UniqueConstraint(
            "question_id", "client_request_id", name="uq_learning_attempt_client_request"
        ),
        sa.UniqueConstraint(
            "question_id", "idempotency_key", name="uq_learning_attempt_idempotency"
        ),
    )
    op.create_table(
        "learning_feedbacks",
        sa.Column("feedback_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("strengths", sa.String(length=200), nullable=True),
        sa.Column("missing_points", sa.String(length=200), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("learning_signal", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["learning_attempts.attempt_id"]),
        sa.PrimaryKeyConstraint("feedback_id"),
        sa.UniqueConstraint("attempt_id", name="uq_learning_feedback_attempt"),
    )
    op.execute("DROP TRIGGER IF EXISTS trg_citations_file_purge")
    with op.batch_alter_table("citations") as batch:
        batch.alter_column(
            "answer_version_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.add_column(sa.Column("learning_feedback_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_citations_learning_feedback",
            "learning_feedbacks",
            ["learning_feedback_id"],
            ["feedback_id"],
            ondelete="CASCADE",
        )
        batch.create_check_constraint(
            "ck_citation_single_owner",
            "(answer_version_id IS NOT NULL AND learning_feedback_id IS NULL) OR "
            "(answer_version_id IS NULL AND learning_feedback_id IS NOT NULL)",
        )
        batch.create_unique_constraint(
            "uq_citation_feedback_number", ["learning_feedback_id", "display_number"]
        )
    op.execute(_CITATION_PURGE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_citations_file_purge")
    with op.batch_alter_table("citations") as batch:
        batch.drop_constraint("uq_citation_feedback_number", type_="unique")
        batch.drop_constraint("ck_citation_single_owner", type_="check")
        batch.drop_constraint("fk_citations_learning_feedback", type_="foreignkey")
        batch.drop_column("learning_feedback_id")
        batch.alter_column(
            "answer_version_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
    op.execute(_CITATION_PURGE_TRIGGER)
    op.drop_table("learning_feedbacks")
    op.drop_table("learning_attempts")
    op.drop_table("question_evidence")
    op.drop_table("learning_questions")
    op.drop_table("learning_plan_items")
    op.drop_table("learning_plans")
    op.drop_table("knowledge_point_evidence")
    op.drop_table("knowledge_points")
    op.drop_table("learning_scope_files")
    op.drop_table("learning_scopes")
    op.drop_index("ix_learning_sessions_status", table_name="learning_sessions")
    op.drop_table("learning_sessions")
