"""Async generation jobs and the assets they consume/produce."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JOB_QUEUED = "queued"
JOB_PROCESSING = "processing"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"

JOB_STATUSES = (JOB_QUEUED, JOB_PROCESSING, JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED)

MODE_TEXT_TO_IMAGE = "text_to_image"
MODE_IMAGE_TO_IMAGE = "image_to_image"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    capability: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("ai_models.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default=JOB_QUEUED, nullable=False, index=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # text_to_image | image_to_image for image jobs, null otherwise.
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_asset_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("assets.id"), nullable=True
    )
    # Validated request parameters (requested dimensions, quality, ...).
    parameters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Snapshot of the active image-processing profile at job creation time.
    processing_profile_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Safe, user-facing error text only. Technical details go to logs.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_jobs_user_created", "user_id", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )


ASSET_INPUT_AUDIO = "input_audio"
ASSET_OUTPUT_AUDIO = "output_audio"
ASSET_CHAT_INPUT_IMAGE = "chat_input_image"
ASSET_INPUT_IMAGE_ORIGINAL = "input_image_original"
ASSET_INPUT_IMAGE_PROCESSED = "input_image_processed"
ASSET_GENERATED_IMAGE = "generated_image"

ASSET_KINDS = (
    ASSET_INPUT_AUDIO,
    ASSET_OUTPUT_AUDIO,
    ASSET_CHAT_INPUT_IMAGE,
    ASSET_INPUT_IMAGE_ORIGINAL,
    ASSET_INPUT_IMAGE_PROCESSED,
    ASSET_GENERATED_IMAGE,
)


class Asset(Base):
    __tablename__ = "assets"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("generation_jobs.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Object-storage key only; binary data never lives in the DB.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    derived_from_asset_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("assets.id"), nullable=True
    )
    # before/after dimensions, resize mode, encoder, quality... no secrets.
    processing_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_assets_user_created", "user_id", "created_at"),
    )
