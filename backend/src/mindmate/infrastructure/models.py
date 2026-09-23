from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7


def new_id() -> str:
    return str(uuid7())


class Base(DeclarativeBase):
    pass


class AppMeta(Base):
    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)


class ContentObject(Base):
    __tablename__ = "content_objects"
    content_object_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_mime_type: Mapped[str | None] = mapped_column(String(255))
    storage_relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_state: Mapped[str] = mapped_column(String(30), default="STAGING", nullable=False)
    reference_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("parent_folder_id", "normalized_name", name="uq_folder_parent_name"),
    )
    folder_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parent_folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.folder_id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class Tag(Base):
    __tablename__ = "tags"
    tag_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class FileRecord(Base):
    __tablename__ = "files"
    file_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_object_id: Mapped[str] = mapped_column(
        ForeignKey("content_objects.content_object_id"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.folder_id"))
    status: Mapped[str] = mapped_column(String(30), default="IMPORTED", nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_revision_id: Mapped[str | None] = mapped_column(String(36))
    parse_failure_stage: Mapped[str | None] = mapped_column(String(80))
    parse_error_id: Mapped[str | None] = mapped_column(String(100))
    parse_retry_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class FileTag(Base):
    __tablename__ = "file_tags"
    __table_args__ = (UniqueConstraint("file_id", "tag_id", name="uq_file_tag"),)
    file_tag_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.file_id"), nullable=False)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.tag_id"), nullable=False)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    knowledge_base_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(50))
    color: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="EMPTY", nullable=False)
    active_index_version_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class KnowledgeBaseFile(Base):
    __tablename__ = "knowledge_base_files"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "file_id", name="uq_knowledge_base_file"),
    )
    knowledge_base_file_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.knowledge_base_id"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(ForeignKey("files.file_id"), nullable=False)
    membership_status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    index_state: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChunkingConfig(Base):
    __tablename__ = "chunking_configs"
    chunking_config_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    config_version: Mapped[str] = mapped_column(String(30), nullable=False)
    algorithm_id: Mapped[str] = mapped_column(String(100), nullable=False)
    measurement_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    target_size: Mapped[int] = mapped_column(Integer, nullable=False)
    min_size: Mapped[int] = mapped_column(Integer, nullable=False)
    max_size: Mapped[int] = mapped_column(Integer, nullable=False)
    overlap_size: Mapped[int] = mapped_column(Integer, nullable=False)
    structure_rules_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmbeddingConfig(Base):
    __tablename__ = "embedding_configs"
    embedding_config_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    config_version: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(200))
    vector_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    normalization: Mapped[bool] = mapped_column(Boolean, nullable=False)
    distance_metric: Mapped[str] = mapped_column(String(30), nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IndexVersion(Base):
    __tablename__ = "index_versions"
    __table_args__ = (
        Index("ix_index_versions_scope_status", "scope_type", "scope_id", "status"),
        Index("ix_index_versions_preprocessing_status", "preprocessing_status"),
    )
    index_version_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.knowledge_base_id"), nullable=False
    )
    parse_revision_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunking_config_id: Mapped[str] = mapped_column(
        ForeignKey("chunking_configs.chunking_config_id"), nullable=False
    )
    embedding_config_id: Mapped[str] = mapped_column(
        ForeignKey("embedding_configs.embedding_config_id"), nullable=False
    )
    vector_engine: Mapped[str] = mapped_column(String(100), nullable=False)
    vector_engine_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    preprocessing_status: Mapped[str] = mapped_column(String(30), nullable=False)
    chunking_status: Mapped[str] = mapped_column(
        String(30), default="NOT_STARTED", server_default=text("'NOT_STARTED'"), nullable=False
    )
    input_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prepared_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    artifact_relative_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    preprocessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexVersionInput(Base):
    __tablename__ = "index_version_inputs"
    __table_args__ = (
        UniqueConstraint("index_version_id", "file_id", name="uq_index_version_input_file"),
        Index("ix_index_version_inputs_status", "index_version_id", "status"),
    )
    index_version_input_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    index_version_id: Mapped[str] = mapped_column(
        ForeignKey("index_versions.index_version_id"), nullable=False
    )
    knowledge_base_file_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_base_files.knowledge_base_file_id"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(ForeignKey("files.file_id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_revision_id: Mapped[str | None] = mapped_column(String(36))
    membership_added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunk_status: Mapped[str] = mapped_column(
        String(30), default="PENDING", server_default=text("'PENDING'"), nullable=False
    )
    chunk_reason_code: Mapped[str | None] = mapped_column(String(80))
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    chunked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chunk(Base):
    """A reusable file-level chunk for one parse and chunking configuration.

    Chunks intentionally do not reference an IndexVersion. Multiple knowledge bases
    can reuse the same file-level result, while each index version keeps its own
    immutable input snapshot and later embedding/index artifacts.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "file_id",
            "parse_revision_id",
            "chunking_config_id",
            "sequence_number",
            name="uq_chunk_file_parse_config_sequence",
        ),
        Index("ix_chunks_file_parse_config", "file_id", "parse_revision_id", "chunking_config_id"),
        Index("ix_chunks_content_hash", "content_hash"),
    )
    chunk_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.file_id"), nullable=False)
    parse_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chunking_config_id: Mapped[str] = mapped_column(
        ForeignKey("chunking_configs.chunking_config_id"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[list[str] | None] = mapped_column(JSON)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    slide_number: Mapped[int | None] = mapped_column(Integer)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    source_kind: Mapped[str | None] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    length_unit: Mapped[str] = mapped_column(
        String(30), default="UNICODE_CHARACTER", server_default=text("'UNICODE_CHARACTER'"), nullable=False
    )
    length_value: Mapped[int] = mapped_column(Integer, nullable=False)
    # No tokenizer is loaded in this batch. Keep the compatibility field nullable
    # instead of pretending Unicode character counts are model tokens.
    token_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackgroundTask(Base):
    __tablename__ = "background_tasks"
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", nullable=False)
    phase: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("background_tasks.task_id"))
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkpoint_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    task_attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("background_tasks.task_id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="RUNNING", nullable=False)
    checkpoint_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskEvent(Base):
    __tablename__ = "task_events"
    task_event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("background_tasks.task_id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    setting_value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    setting_schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderProfile(Base):
    __tablename__ = "provider_profiles"
    provider_profile_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_type: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    default_chat_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    secret_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Backup(Base):
    __tablename__ = "backups"
    backup_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    archive_relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="CREATED", nullable=False)
    backup_format_version: Mapped[str] = mapped_column(String(20), default="1", nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    includes_vectors: Mapped[bool] = mapped_column(default=False, nullable=False)
    includes_parsed: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(String(500))


class BackupEntry(Base):
    __tablename__ = "backup_entries"
    backup_entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    backup_id: Mapped[str] = mapped_column(ForeignKey("backups.backup_id"), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
