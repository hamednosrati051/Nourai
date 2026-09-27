"""Conversations, messages and the message<->asset join table."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

MESSAGE_ROLES = (ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM)


class Conversation(Base):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("ai_models.id"), nullable=True
    )
    # Soft delete: user hides it, admin can still see it.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_conversations_user_created", "user_id", "created_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_asset_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("assets.id"), nullable=True
    )
    output_asset_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("assets.id"), nullable=True
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="succeeded", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )


class MessageAsset(Base):
    """Join table so one message can carry several files.

    role: "input" (user-supplied, e.g. chat image) or "output" (model output).
    """

    __tablename__ = "message_assets"

    message_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("messages.id"), nullable=False, index=True
    )
    asset_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("assets.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index("ix_message_assets_unique", "message_id", "asset_id", unique=True),
    )
