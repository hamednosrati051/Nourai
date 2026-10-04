"""Subscription plans and user plan subscriptions.

Plans are admin-priced (price_irr, canonical IRR; toman display only in UI).
Buying a paid plan runs the normal Zibal payment flow; on successful
verification a subscription is activated — the wallet is NOT credited.
The plan price buys the quota bundle; the wallet is only topped up by
explicit top-ups and is billed when quota is exhausted (or without a plan).
Free plans are activated directly without payment.

At most one *active* subscription per user at a time (enforced in the
service layer; see services/plans.py).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CHAR

SUB_ACTIVE = "active"
SUB_EXPIRED = "expired"
SUB_CANCELLED = "cancelled"

SUBSCRIPTION_STATUSES = (SUB_ACTIVE, SUB_EXPIRED, SUB_CANCELLED)


class Plan(Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Integer IRR the user pays (canonical). Toman display only in UI.
    price_irr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Subscription length in days (also meaningful for free plans).
    period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # Persian feature bullet strings shown on the landing section.
    features_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # e.g. {"monthly_text": 50, "monthly_image": 5, "monthly_audio_minutes": 10}
    usage_limits_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Promotional wallet credit added on top of the paid amount (paid plans).
    bonus_irr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Highlighted as "پیشنهاد ما" in the UI.
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserPlanSubscription(Base):
    __tablename__ = "user_plan_subscriptions"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("plans.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default=SUB_ACTIVE, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Computed from plan.period_days at activation; counters reset on renewal.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Current-period consumption, e.g. {"text": 12, "image": 3, "audio_minutes": 7}.
    usage_counters_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_subscriptions_user_status", "user_id", "status"),
    )
