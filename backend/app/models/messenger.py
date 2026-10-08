"""Messenger bot account linking model (generic across platforms)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Platform identifiers for the messenger_users.platform column.
PLATFORM_BALE = "bale"
PLATFORM_EITAA = "eitaa"
PLATFORM_TELEGRAM = "telegram"


class MessengerUser(Base):
    """Links a messenger-platform user (Bale/Eitaa/Telegram) to a Nourai account."""

    __tablename__ = "messenger_users"

    platform: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    platform_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    platform_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_messenger_platform_user"),
    )


class MessengerUserState(Base):
    """Temporary conversation state for a messenger-platform user (generic).

    Replaces in-memory dicts so state survives API restarts. Each platform+user
    has at most one active state (e.g. "awaiting_tts_text").
    """

    __tablename__ = "messenger_user_states"

    platform: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    platform_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_messenger_state_user"),
    )


class SupportMessage(Base):
    """Support ticket message from a messenger-platform user."""

    __tablename__ = "support_messages"

    platform: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    platform_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    admin_reply: Mapped[str | None] = mapped_column(String(2000), nullable=True)
