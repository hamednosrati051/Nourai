"""AI model catalog and versioned pricing rules."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

CAP_TEXT = "text"
CAP_STT = "speech_to_text"
CAP_TTS = "text_to_speech"
CAP_IMAGE = "image"

CAPABILITIES = (CAP_TEXT, CAP_STT, CAP_TTS, CAP_IMAGE)


class AiModel(Base):
    __tablename__ = "ai_models"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    capability: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Adapter family for this model (e.g. "openai_compat"). Selects the
    # runtime adapter; env vars remain only as fallback for callers without
    # a model row. New families can be added without touching existing rows.
    provider_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="openai_compat", server_default="openai_compat"
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    pricing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Valid tiktoken encoding name for text models; validated with
    # tiktoken.get_encoding() when the model is saved. No silent fallback.
    tokenizer_encoding: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Non-secret tunables only. Prices live in ModelPricingRule. Provider API
    # keys live in env/secret manager, never here.
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelPricingRule(Base):
    __tablename__ = "model_pricing_rules"

    model_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("ai_models.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    billing_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    # Quantity that makes up one priced unit, e.g. 1000 tokens or 1 second.
    unit_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Integer IRR per unit.
    unit_price_irr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # For size/quality-dependent tariffs.
    dimension_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    minimum_charge_irr: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    maximum_charge_irr: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # "up" | "down" | "nearest"
    rounding_mode: Mapped[str] = mapped_column(String(16), default="up", nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_by_admin_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("admin_users.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_pricing_model_active", "model_id", "is_active", "effective_from"),
    )
