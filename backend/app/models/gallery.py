"""Public gallery entries (admin-curated)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

GALLERY_PENDING = "pending"
GALLERY_APPROVED = "approved"
GALLERY_REJECTED = "rejected"

GALLERY_STATUSES = (GALLERY_PENDING, GALLERY_APPROVED, GALLERY_REJECTED)


class GalleryEntry(Base):
    __tablename__ = "gallery_entries"

    # Only assets of kind "generated_image" may enter the gallery.
    asset_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("assets.id"), unique=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default=GALLERY_PENDING, nullable=False)
    reviewed_by_admin_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("admin_users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Admin-panel only; never exposed publicly.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Fast retrieval of the latest approved images for the public gallery.
        Index("ix_gallery_status_reviewed", "status", "reviewed_at"),
    )
