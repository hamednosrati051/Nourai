"""Public subscription plans.

GET /api/v1/plans                — active plans, sort_order ascending
POST /api/v1/plans/{id}/activate — free plans only (no payment);
                                   paid plans answer PAYMENT_REQUIRED
GET /api/v1/me/plan              — current active plan + limits + period usage

Prices are admin-editable; this endpoint always reflects the current
catalog. Responses include both IRR (canonical) and the toman equivalent.
"""
from __future__ import annotations

from flask import Blueprint, g

from app.api.deps import error_response, login_required, success_response
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
        # Paid plans go through POST /api/v1/payments with plan_id.
        return error_response(
            "PAYMENT_REQUIRED",
            "این پلن پولی است؛ لطفاً از طریق درگاه پرداخت خرید کنید.",
            402,
        )
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
