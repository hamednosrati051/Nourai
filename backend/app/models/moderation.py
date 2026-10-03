"""Prompt moderation: admin-managed blocklist + global kill switch.

Admins curate blocked phrases (any language) from the panel; image job
creation rejects prompts containing an active phrase *before* any wallet
hold or provider call. Matching details live in app.services.prompt_filter.
"""
from __future__ import annotations

from sqlalchemy import CHAR, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PromptBlocklist(Base):
    __tablename__ = "prompt_blocklist"

    phrase: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_admin_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("admin_users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModerationSettings(Base):
    """Singleton: global on/off switch for prompt filtering."""

    __tablename__ = "moderation_settings"

    prompt_filter_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
