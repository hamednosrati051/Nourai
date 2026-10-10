"""Bale channel publish queue (admin-approved)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

BALE_QUEUE_PENDING = "pending"
BALE_QUEUE_APPROVED = "approved"
BALE_QUEUE_REJECTED = "rejected"
BALE_QUEUE_PUBLISHED = "published"

BALE_QUEUE_STATUSES = (
    BALE_QUEUE_PENDING,
    BALE_QUEUE_APPROVED,
    BALE_QUEUE_REJECTED,
    BALE_QUEUE_PUBLISHED,
)

CONTENT_TYPE_GALLERY = "gallery"
CONTENT_TYPE_BLOG = "blog"


class BalePublishQueue(Base):
    __tablename__ = "bale_publish_queue"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=BALE_QUEUE_PENDING, nullable=False, index=True
    )
    # Caption/text to send with the post
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_admin_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("admin_users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Bale message ID after publishing (for reference)
    bale_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
