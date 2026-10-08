"""Bale bot account linking model."""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BaleUser(Base):
    """Links a Bale messenger user to a Nourai site account."""

    __tablename__ = "bale_users"

    bale_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    bale_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bale_first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
