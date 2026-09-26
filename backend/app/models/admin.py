"""Admin user model (Argon2id password hashes)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Argon2id hash string. Never store or log the raw password.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
