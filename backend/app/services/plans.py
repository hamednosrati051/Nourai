"""Plan subscriptions and per-period usage quotas (soft).

One active subscription per user at a time. Usage counters reset naturally
because each (re)activation creates a fresh subscription with its own
``usage_counters_json`` and ``expires_at`` computed from ``period_days``.

Quotas are SOFT: they never block. When a kind's counter reaches the plan
limit, the request is billed from the wallet instead (or fails with
INSUFFICIENT_BALANCE like any wallet request). Buying a plan does NOT
credit the wallet — the price buys the quota bundle; the wallet is only
topped up by explicit top-ups.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models.base import utcnow
from app.models.plans import (
    Plan,
    SUB_ACTIVE,
    SUB_CANCELLED,
    SUB_EXPIRED,
    UserPlanSubscription,
)


# Maps a usage kind to the plan.usage_limits_json key and the counter key
# stored in subscription.usage_counters_json.
LIMIT_KEYS = {
    "text": "monthly_text",
    "image": "monthly_image",
    "audio": "monthly_audio_minutes",
}
COUNTER_KEYS = {
    "text": "text",
    "image": "image",
    "audio": "audio_minutes",
}


def over_quota_kinds(session, sub: UserPlanSubscription) -> list[str]:
    """Usage kinds whose period counter reached the plan limit (soft signal).

    Never blocks — callers use it for notices; billing falls back to the
    wallet for these kinds.
    """
    plan = session.get(Plan, sub.plan_id)
    if plan is None:
        return []
    limits = plan.usage_limits_json or {}
    counters = sub.usage_counters_json or {}
    over = []
    for kind, limit_key in LIMIT_KEYS.items():
        limit = limits.get(limit_key)
        if limit is not None and counters.get(COUNTER_KEYS[kind], 0) >= limit:
            over.append(kind)
    return over


def get_active_subscription(session, user_id: str) -> UserPlanSubscription | None:
    """Return the user's active subscription, lazily expiring stale ones.

    An expired subscription is marked ``expired`` and flushed; the caller
    commits as part of its own transaction.
    """
    sub = session.execute(
        select(UserPlanSubscription).where(
            UserPlanSubscription.user_id == user_id,
            UserPlanSubscription.status == SUB_ACTIVE,
        )
    ).scalar_one_or_none()
    if sub is None:
        return None
    if sub.expires_at <= utcnow():
        sub.status = SUB_EXPIRED
        session.flush()
        return None
    return sub


def activate_subscription(
    session, user_id: str, plan: Plan
) -> UserPlanSubscription:
    """Activate *plan* for *user_id*, replacing any currently active one."""
    existing = session.execute(
        select(UserPlanSubscription).where(
            UserPlanSubscription.user_id == user_id,
            UserPlanSubscription.status == SUB_ACTIVE,
        )
    ).scalars().all()
    for old in existing:
        old.status = SUB_CANCELLED
    now = utcnow()
    sub = UserPlanSubscription(
        user_id=user_id,
        plan_id=plan.id,
        status=SUB_ACTIVE,
        started_at=now,
        expires_at=now + timedelta(days=plan.period_days),
        usage_counters_json={},
    )
    session.add(sub)
    session.flush()
    return sub


def _fa_digits(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


_LIMIT_LABELS = {
    "monthly_text": "پیام متنی در ماه",
    "monthly_image": "تصویر در ماه",
    "monthly_audio_minutes": "دقیقه خدمات صوتی در ماه",
}


def plan_to_public_dict(plan: Plan) -> dict:
    from app.billing.currency import irr_to_toman

    limits = plan.usage_limits_json or {}
    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "price_irr": plan.price_irr,
        "price_toman": irr_to_toman(plan.price_irr),
        "bonus_irr": plan.bonus_irr,
        "bonus_toman": irr_to_toman(plan.bonus_irr),
        "period_days": plan.period_days,
        "features": list(plan.features_json or []),
        "usage_limits": plan.usage_limits_json,
        "limits": [
            f"{_fa_digits(v)} {_LIMIT_LABELS[k]}"
            for k, v in limits.items() if k in _LIMIT_LABELS
        ],
        "is_free": plan.is_free,
        "is_featured": plan.is_featured,
        "sort_order": plan.sort_order,
    }


def subscription_to_dict(session, sub: UserPlanSubscription) -> dict:
    plan = session.get(Plan, sub.plan_id)
    return {
        "id": sub.id,
        "plan_id": sub.plan_id,
        "plan": plan_to_public_dict(plan) if plan else None,
        "status": sub.status,
        "started_at": sub.started_at.isoformat() + "Z",
        "expires_at": sub.expires_at.isoformat() + "Z",
        "usage_counters": sub.usage_counters_json or {},
        "over_quota": over_quota_kinds(session, sub),
    }


class PlanLimitService:
    """Track per-period AI usage against the user's active plan (soft).

    Users without an active subscription (or a plan without limits) are
    unlimited. ``quota_available`` decides whether a request is covered by
    the plan quota (no wallet charge); ``increment`` records successful
    consumption afterwards. Quotas never block — over-quota usage is
    billed from the wallet like any pay-as-you-go request.
    """

    def __init__(self, session) -> None:
        self.session = session

    def quota_available(self, user_id: str, kind: str, amount: int = 1) -> bool:
        """True if the active plan covers *amount* more units of *kind*."""
        sub = get_active_subscription(self.session, user_id)
        if sub is None:
            return False
        plan = self.session.get(Plan, sub.plan_id)
        if plan is None:
            return False
        limits = plan.usage_limits_json or {}
        limit = limits.get(LIMIT_KEYS[kind])
        if limit is None:
            return False
        counters = sub.usage_counters_json or {}
        return counters.get(COUNTER_KEYS[kind], 0) + amount <= limit

    def increment(self, user_id: str, kind: str, amount: int = 1) -> None:
        sub = get_active_subscription(self.session, user_id)
        if sub is None:
            return
        counters = dict(sub.usage_counters_json or {})
        key = COUNTER_KEYS[kind]
        counters[key] = counters.get(key, 0) + amount
        sub.usage_counters_json = counters
        self.session.flush()
