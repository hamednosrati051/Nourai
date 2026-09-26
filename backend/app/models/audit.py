"""Audit log model."""
from __future__ import annotations

from sqlalchemy import CHAR, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

ACTOR_USER = "user"
ACTOR_ADMIN = "admin"
ACTOR_SYSTEM = "system"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Sanitised metadata: never secrets, OTP codes, raw passwords or tokens.
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_audit_actor", "actor_type", "actor_id"),
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_target", "target_type", "target_id"),
    )
