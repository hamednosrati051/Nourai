"""Admin-configurable image processing profiles.

A profile is snapshotted onto each image job at creation time, so later admin
changes never rewrite the billing or the result of older jobs. Profile values
may never exceed the hard security ceilings from the environment.
"""
from __future__ import annotations

from sqlalchemy import CHAR, BigInteger, Boolean, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

RESIZE_FIT = "fit"
RESIZE_FILL = "fill"
RESIZE_STRETCH = "stretch"

RESIZE_MODES = (RESIZE_FIT, RESIZE_FILL, RESIZE_STRETCH)


class ImageProcessingProfile(Base):
    __tablename__ = "image_processing_profiles"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Null => global default profile.
    model_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("ai_models.id"), nullable=True, index=True
    )
    max_upload_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_input_pixels: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allowed_mime_types_json: Mapped[list] = mapped_column(JSON, nullable=False)
    target_width: Mapped[int] = mapped_column(Integer, nullable=False)
    target_height: Mapped[int] = mapped_column(Integer, nullable=False)
    resize_mode: Mapped[str] = mapped_column(String(16), default=RESIZE_FIT, nullable=False)
    allow_upscale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "jpeg" | "png" | "webp"
    output_format: Mapped[str] = mapped_column(String(16), default="jpeg", nullable=False)
    output_quality: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    strip_metadata: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by_admin_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("admin_users.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_img_profile_model_active", "model_id", "is_active"),
    )

    def snapshot(self) -> dict:
        return {
            "profile_id": self.id,
            "version": self.version,
            "max_upload_bytes": self.max_upload_bytes,
            "max_input_pixels": self.max_input_pixels,
            "allowed_mime_types": list(self.allowed_mime_types_json or []),
            "target_width": self.target_width,
            "target_height": self.target_height,
            "resize_mode": self.resize_mode,
            "allow_upscale": self.allow_upscale,
            "output_format": self.output_format,
            "output_quality": self.output_quality,
            "strip_metadata": self.strip_metadata,
        }


class CurrencySettings(Base):
    """Singleton row: USD->IRR rate and image cost-protection margin.

    The image worker converts the provider-reported generation cost
    (USD cents) to IRR with ``usd_to_irr`` and, when that cost exceeds the
    admin tariff, charges cost * (1 + image_cost_margin_pct / 100) instead.
    ``usd_to_irr = 0`` means "not configured" -> tariff-only billing.
    """

    __tablename__ = "currency_settings"

    usd_to_irr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    image_cost_margin_pct: Mapped[float] = mapped_column(
        Float, default=30.0, nullable=False
    )

    def snapshot(self) -> dict:
        return {
            "usd_to_irr": self.usd_to_irr,
            "image_cost_margin_pct": self.image_cost_margin_pct,
        }
