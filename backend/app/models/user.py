"""User and OTP challenge models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    mobile_normalized: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    mobile_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Bumped when the user is disabled (or sessions are revoked); JWTs issued
    # before this instant are rejected.
    session_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    mobile_normalized: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="login", nullable=False)
    # SHA-256 hex of the code. The raw code is NEVER stored.
    code_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_otp_challenges_mobile_created", "mobile_normalized", "created_at"),
    )
