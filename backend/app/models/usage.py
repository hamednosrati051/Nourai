"""Per-request usage events: the auditable link between AI calls and billing."""
from __future__ import annotations

from sqlalchemy import CHAR, BigInteger, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("generation_jobs.id"), nullable=True, index=True
    )
    model_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("ai_models.id"), nullable=True, index=True
    )
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="succeeded", nullable=False, index=True)

    # Estimated (pre-run) vs final (post-run) consumption.
    est_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    est_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_pixels: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_pixels: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    tokenizer_encoding: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "tiktoken" | "provider"
    token_count_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    pricing_rule_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("model_pricing_rules.id"), nullable=True
    )
    # Frozen copy of the rule (id, version, unit, price...) used for this event.
    pricing_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    estimated_amount_irr: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reserved_amount_irr: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    charged_amount_irr: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    provider_cost_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_cost_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # No secrets.
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_usage_user_created", "user_id", "created_at"),
        Index("ix_usage_model_created", "model_id", "created_at"),
    )
