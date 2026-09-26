"""Payment model (Zibal gateway in MVP)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PAY_CREATED = "created"
PAY_PENDING = "pending"
PAY_PAID = "paid"
PAY_FAILED = "failed"
PAY_CANCELLED = "cancelled"
PAY_REFUNDED = "refunded"

PAYMENT_STATUSES = (
    PAY_CREATED,
    PAY_PENDING,
    PAY_PAID,
    PAY_FAILED,
    PAY_CANCELLED,
    PAY_REFUNDED,
)


class Payment(Base):
    __tablename__ = "payments"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    gateway: Mapped[str] = mapped_column(String(32), default="zibal", nullable=False)
    # Integer IRR (canonical). Conversion to the gateway's expected unit lives
    # in the gateway adapter, never here.
    amount_irr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Optional top-up plan: when set, amount_irr is forced to the plan's
    # price_irr (the client's amount is ignored) and the wallet is credited
    # price_irr + bonus_irr on successful verification.
    plan_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("plans.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default=PAY_CREATED, nullable=False, index=True)
    # Zibal track id, unique when present.
    track_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    # Final gateway reference number (refNumber), nullable.
    gateway_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_payments_user_created", "user_id", "created_at"),
    )
