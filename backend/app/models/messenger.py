"""Messenger bot account linking model (generic across platforms)."""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
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
