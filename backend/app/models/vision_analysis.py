"""Vision analysis history."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class VisionAnalysis(Base):
    __tablename__ = "vision_analyses"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)
    usage_event_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("usage_events.id"), nullable=True
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
