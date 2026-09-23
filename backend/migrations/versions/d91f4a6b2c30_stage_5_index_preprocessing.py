"""Add versioned index configuration and preprocessing snapshots.

Revision ID: d91f4a6b2c30
Revises: c7d5e8a1f204
Create Date: 2026-09-23
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "d91f4a6b2c30"
down_revision: str | Sequence[str] | None = "c7d5e8a1f204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunking_configs",
        sa.Column("chunking_config_id", sa.String(length=36), nullable=False),
        sa.Column("config_version", sa.String(length=30), nullable=False),
        sa.Column("algorithm_id", sa.String(length=100), nullable=False),
        sa.Column("measurement_unit", sa.String(length=30), nullable=False),
        sa.Column("target_size", sa.Integer(), nullable=False),
        sa.Column("min_size", sa.Integer(), nullable=False),
        sa.Column("max_size", sa.Integer(), nullable=False),
        sa.Column("overlap_size", sa.Integer(), nullable=False),
        sa.Column("structure_rules_hash", sa.String(length=64), nullable=False),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("chunking_config_id"),
        sa.UniqueConstraint("config_fingerprint"),
    )
    op.create_table(
        "embedding_configs",
        sa.Column("embedding_config_id", sa.String(length=36), nullable=False),
        sa.Column("config_version", sa.String(length=30), nullable=False),
        sa.Column("provider_type", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_revision", sa.String(length=200), nullable=True),
        sa.Column("vector_dimension", sa.Integer(), nullable=False),
        sa.Column("normalization", sa.Boolean(), nullable=False),
        sa.Column("distance_metric", sa.String(length=30), nullable=False),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("embedding_config_id"),
        sa.UniqueConstraint("config_fingerprint"),
    )
    op.bulk_insert(
        sa.table(
            "chunking_configs",
            sa.column("chunking_config_id", sa.String),
            sa.column("config_version", sa.String),
            sa.column("algorithm_id", sa.String),
            sa.column("measurement_unit", sa.String),
            sa.column("target_size", sa.Integer),
            sa.column("min_size", sa.Integer),
            sa.column("max_size", sa.Integer),
            sa.column("overlap_size", sa.Integer),
            sa.column("structure_rules_hash", sa.String),
            sa.column("config_fingerprint", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "chunking_config_id": "00000000-0000-7000-8000-000000000501",
                "config_version": "char-v1",
                "algorithm_id": "structure-aware-chinese-v1",
                "measurement_unit": "UNICODE_CHARACTER",
                "target_size": 500,
                "min_size": 250,
                "max_size": 800,
                "overlap_size": 80,
                "structure_rules_hash": "514559e9565ace9203a578e8a2647aae13b8607a5f64e00f9404f1fa01eb18b4",
                "config_fingerprint": "80246478913bebcf7492ebca0338c3d3773b7c2044f6752f319716d827a93b20",
                "created_at": datetime(2026, 9, 23, tzinfo=UTC),
            }
        ],
    )
    op.bulk_insert(
        sa.table(
            "embedding_configs",
            sa.column("embedding_config_id", sa.String),
            sa.column("config_version", sa.String),
            sa.column("provider_type", sa.String),
            sa.column("model_name", sa.String),
            sa.column("model_revision", sa.String),
            sa.column("vector_dimension", sa.Integer),
            sa.column("normalization", sa.Boolean),
            sa.column("distance_metric", sa.String),
            sa.column("config_fingerprint", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "embedding_config_id": "00000000-0000-7000-8000-000000000502",
                "config_version": "bge-small-zh-v1",
                "provider_type": "LOCAL_ONNX",
                "model_name": "BAAI/bge-small-zh-v1.5",
                "model_revision": None,
                "vector_dimension": 512,
                "normalization": True,
                "distance_metric": "COSINE",
                "config_fingerprint": "04588550b36a0dcb240642e4681031e4832bfca9ce4f2e8174daded489df7c2a",
                "created_at": datetime(2026, 9, 23, tzinfo=UTC),
            }
        ],
    )
    op.create_table(
        "index_versions",
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("scope_type", sa.String(length=30), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=False),
        sa.Column("parse_revision_set_hash", sa.String(length=64), nullable=False),
        sa.Column("chunking_config_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_config_id", sa.String(length=36), nullable=False),
        sa.Column("vector_engine", sa.String(length=100), nullable=False),
        sa.Column("vector_engine_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("preprocessing_status", sa.String(length=30), nullable=False),
        sa.Column("input_count", sa.Integer(), nullable=False),
        sa.Column("prepared_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("artifact_relative_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preprocessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chunking_config_id"], ["chunking_configs.chunking_config_id"]),
        sa.ForeignKeyConstraint(["embedding_config_id"], ["embedding_configs.embedding_config_id"]),
        sa.ForeignKeyConstraint(["scope_id"], ["knowledge_bases.knowledge_base_id"]),
        sa.PrimaryKeyConstraint("index_version_id"),
    )
    op.create_index(
        "ix_index_versions_scope_status", "index_versions", ["scope_type", "scope_id", "status"]
    )
    op.create_index(
        "ix_index_versions_preprocessing_status", "index_versions", ["preprocessing_status"]
    )
    op.create_table(
        "index_version_inputs",
        sa.Column("index_version_input_id", sa.String(length=36), nullable=False),
        sa.Column("index_version_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_file_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parse_revision_id", sa.String(length=36), nullable=True),
        sa.Column("membership_added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.file_id"]),
        sa.ForeignKeyConstraint(["index_version_id"], ["index_versions.index_version_id"]),
        sa.ForeignKeyConstraint(
            ["knowledge_base_file_id"], ["knowledge_base_files.knowledge_base_file_id"]
        ),
        sa.PrimaryKeyConstraint("index_version_input_id"),
        sa.UniqueConstraint("index_version_id", "file_id", name="uq_index_version_input_file"),
    )
    op.create_index(
        "ix_index_version_inputs_status",
        "index_version_inputs",
        ["index_version_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_index_version_inputs_status", table_name="index_version_inputs")
    op.drop_table("index_version_inputs")
    op.drop_index("ix_index_versions_preprocessing_status", table_name="index_versions")
    op.drop_index("ix_index_versions_scope_status", table_name="index_versions")
    op.drop_table("index_versions")
    op.drop_table("embedding_configs")
    op.drop_table("chunking_configs")
