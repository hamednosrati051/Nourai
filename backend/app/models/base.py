"""Declarative base: UUID (CHAR(36)) primary keys, naive-UTC timestamps."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CHAR, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-naive UTC now with microsecond precision."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_uuid() -> str:
    return str(uuid4())


class Base(db.Model):
    __abstract__ = True

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
