"""User service: lookup, disable/enable (with session revocation) and the
admin activity timeline aggregation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func

from app.auth.otp import mask_mobile
from app.models import AuditLog, Payment, UsageEvent, User, WalletTransaction
from app.models.wallet import WalletAccount
from app.services.audit import audit

log = logging.getLogger(__name__)


def get_user_by_id(session, user_id: str) -> User | None:
    return session.get(User, user_id)


def get_user_by_mobile(session, mobile_normalized: str) -> User | None:
    return session.query(User).filter_by(mobile_normalized=mobile_normalized).one_or_none()


def set_user_active(
    session,
    *,
    user: User,
    active: bool,
    reason: str,
    admin_id: str,
    ip_hash: str | None = None,
) -> User:
    """Enable/disable a user. Disabling revokes all active sessions
    immediately; history (payments, usage, assets) is never deleted."""
    user.is_active = active
    user.session_invalidated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    audit(
        session,
        actor_type="admin",
        actor_id=admin_id,
        action="user.disabled" if not active else "user.enabled",
        target_type="user",
        target_id=user.id,
        metadata={"reason": reason, "mobile": mask_mobile(user.mobile_normalized)},
        ip_hash=ip_hash,
    )
    log.info("user %s set active=%s by admin %s", user.id, active, admin_id)
    return user


def user_summary(session, user: User) -> dict:
    wallet = session.query(WalletAccount).filter_by(user_id=user.id).one_or_none()
    return {
        "id": user.id,
        "mobile_masked": mask_mobile(user.mobile_normalized),
        "is_active": user.is_active,
        "mobile_verified_at": _iso(user.mobile_verified_at),
        "last_login_at": _iso(user.last_login_at),
        "balance_irr": wallet.balance_irr if wallet else 0,
        "total_spent_irr": _total_spent_irr(session, user.id),
        "created_at": _iso(user.created_at),
    }


def _total_spent_irr(session, user_id: str) -> int:
    """Total consumption in IRR: sum of final charged amounts.

    UsageEvent.charged_amount_irr holds the final settled charge per AI
    usage (0 for failed requests). Summing wallet transactions would
    overcount: reserves are pre-run estimates that get released or
    adjusted on settle, so only the usage records carry the true charge.
    """
    total = (
        session.query(func.coalesce(func.sum(UsageEvent.charged_amount_irr), 0))
        .filter(UsageEvent.user_id == user_id)
        .scalar()
    )
    return int(total or 0)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def activity_timeline(session, user_id: str, limit: int = 100) -> list[dict]:
    """Aggregate logins, AI requests, payments and wallet changes for the
    admin user-detail page. Only the requested user's data is included."""
    events: list[dict] = []

    for entry in (
        session.query(AuditLog)
        .filter(AuditLog.actor_type == "user", AuditLog.actor_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    ):
        events.append({
            "kind": "audit",
            "action": entry.action,
            "at": _iso(entry.created_at),
            "detail": entry.metadata_json,
        })

    for payment in (
        session.query(Payment)
        .filter_by(user_id=user_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .all()
    ):
        events.append({
            "kind": "payment",
            "action": f"payment.{payment.status}",
            "at": _iso(payment.created_at),
            "detail": {"amount_irr": payment.amount_irr, "gateway": payment.gateway},
        })

    for usage in (
        session.query(UsageEvent)
        .filter_by(user_id=user_id)
        .order_by(UsageEvent.created_at.desc())
        .limit(limit)
        .all()
    ):
        events.append({
            "kind": "usage",
            "action": f"usage.{usage.status}",
            "at": _iso(usage.created_at),
            "detail": {
                "model_id": usage.model_id,
                "charged_amount_irr": usage.charged_amount_irr,
            },
        })

    wallet_ids = [w.id for w in session.query(WalletAccount).filter_by(user_id=user_id).all()]
    if wallet_ids:
        for tx in (
            session.query(WalletTransaction)
            .filter(WalletTransaction.wallet_id.in_(wallet_ids))
            .order_by(WalletTransaction.created_at.desc())
            .limit(limit)
            .all()
        ):
            events.append({
                "kind": "wallet",
                "action": f"wallet.{tx.type}",
                "at": _iso(tx.created_at),
                "detail": {"amount_irr": tx.amount_irr, "balance_after_irr": tx.balance_after_irr},
            })

    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return events[:limit]
