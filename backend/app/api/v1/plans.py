"""Public subscription plans.

GET /api/v1/plans                — active plans, sort_order ascending
POST /api/v1/plans/{id}/activate — free plans only (no payment);
                                   paid plans answer PAYMENT_REQUIRED
POST /api/v1/plans/{id}/purchase — paid plans: buy with wallet credit
                                   (top up the wallet first); 402 when
                                   the balance is insufficient
GET /api/v1/me/plan              — current active plan + limits + period usage

Prices are admin-editable; this endpoint always reflects the current
catalog. Responses include both IRR (canonical) and the toman equivalent.
"""
from __future__ import annotations

from flask import Blueprint, g, request

from app.api.deps import error_response, login_required, success_response
from app.billing.ledger import (
    DuplicateIdempotencyKey,
    InsufficientBalance,
    get_wallet_for_update,
    plan_purchase,
)
from app.extensions import db
from app.models import Plan
from app.services.plans import (
    activate_subscription,
    get_active_subscription,
    plan_to_public_dict,
    subscription_to_dict,
)

bp = Blueprint("plans", __name__)


@bp.get("/plans")
def list_plans():
    plans = (
        db.session.query(Plan)
        .filter(Plan.is_active.is_(True))
        .order_by(Plan.sort_order.asc(), Plan.created_at.asc())
        .all()
    )
    return success_response([plan_to_public_dict(p) for p in plans])


@bp.post("/plans/<plan_id>/activate")
@login_required
def activate_plan(plan_id: str):
    plan = db.session.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        return error_response("NOT_FOUND", "پلن یافت نشد.", 404)
    if not plan.is_free:
        # Paid plans are bought with wallet credit (top up first).
        return error_response(
            "PAYMENT_REQUIRED",
            "این اشتراک پولی است؛ ابتدا کیف پول را شارژ کنید سپس خرید کنید.",
            402,
        )
    sub = activate_subscription(db.session, g.current_user_id, plan)
    db.session.commit()
    return success_response(
        {"subscription": subscription_to_dict(db.session, sub)}, status=201
    )


@bp.post("/plans/<plan_id>/purchase")
@login_required
def purchase_plan(plan_id: str):
    """Buy a paid plan with wallet credit.

    The wallet must be topped up first (via /payments); the plan price is
    deducted from the balance and the subscription is activated. Buying a
    new plan replaces any currently active one.
    """
    plan = db.session.get(Plan, plan_id)
    if plan is None or not plan.is_active:
        return error_response("NOT_FOUND", "پلن یافت نشد.", 404)
    if plan.is_free:
        return error_response(
            "VALIDATION_ERROR",
            "پلن رایگان نیازی به خرید ندارد؛ از فعال‌سازی مستقیم استفاده کنید.",
            422,
        )
    idempotency_key = request.headers.get("Idempotency-Key") or f"planbuy-{g.current_user_id}-{plan.id}"
    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        plan_purchase(
            db.session,
            wallet=wallet,
            amount_irr=plan.price_irr,
            idempotency_key=idempotency_key,
            reference_type="plan",
            reference_id=plan.id,
            description=f"plan purchase: {plan.name}",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response(
            "INSUFFICIENT_BALANCE",
            "موجودی کیف پول کافی نیست؛ ابتدا کیف پول را شارژ کنید.",
            402,
        )
    except DuplicateIdempotencyKey:
        pass  # retried request; the deduction already happened
    sub = activate_subscription(db.session, g.current_user_id, plan)
    db.session.commit()
    return success_response(
        {"subscription": subscription_to_dict(db.session, sub)}, status=201
    )


@bp.get("/me/plan")
@login_required
def my_plan():
    sub = get_active_subscription(db.session, g.current_user_id)
    db.session.commit()  # persist lazy expiration if it happened
    if sub is None:
        return success_response({"subscription": None})
    return success_response(
        {"subscription": subscription_to_dict(db.session, sub)}
    )
