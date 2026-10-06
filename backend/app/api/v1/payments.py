"""Wallet top-up via the Zibal gateway.

Flow: create -> redirect -> callback -> server-side verify -> idempotent
credit. The callback only *starts* verification; money moves only after a
direct verify call whose track_id AND amount match the internal record.
Repeated callbacks/verifies can never credit twice.

Money-safety rule: the wallet is credited ONLY when Zibal's verify
explicitly confirms the payment (result 100/201). If money was deducted
from the user's card but the gateway reports an error, we never credit —
Zibal/Shaparak auto-reverses such payments (usually within 72h). The
POST /payments/<id>/recheck endpoint lets the user re-verify a pending
payment later (e.g. after a network failure during the first verify).
"""
from __future__ import annotations

import logging
import uuid

from flask import Blueprint, g, redirect, request
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    client_ip,
    error_response,
    ip_hash,
    login_required,
    paginate_query,
    paginated_response,
    pagination_params,
    success_response,
    utcnow,
    validation_error,
)
from app.billing.ledger import DuplicateIdempotencyKey, deposit, get_wallet_for_update
from app.config import config
from app.extensions import db
from app.models import Payment, Plan
from app.services.plans import activate_subscription
from app.models.payment import PAY_CREATED, PAY_FAILED, PAY_PAID, PAY_PENDING
from app.providers import get_payment_gateway
from app.providers.base import PaymentVerify, ProviderError
from app.providers.zibal import ZibalNotConfigured
from app.services.audit import audit

log = logging.getLogger(__name__)

bp = Blueprint("payments", __name__)


class PaymentCreateSchema(BaseModel):
    amount_irr: int | None = None


def _payment_payload(payment: Payment) -> dict:
    payload = {
        "id": payment.id,
        "gateway": payment.gateway,
        "amount_irr": payment.amount_irr,
        "plan_id": payment.plan_id,
        "status": payment.status,
        "track_id": payment.track_id,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
    }
    # Pending payments carry the gateway URL so the UI can offer
    # "continue payment" / "recheck" actions.
    if payment.status == PAY_PENDING and payment.track_id:
        gateway_url = f"https://gateway.zibal.ir/start/{payment.track_id}"
        payload["payment_url"] = gateway_url
        payload["redirect_url"] = gateway_url
    return payload


@bp.post("/payments")
@login_required
def create_payment():
    try:
        data = PaymentCreateSchema(**(request.get_json(silent=True) or {}))
    except ValidationError:
        return validation_error()

    # Pure wallet top-up. Plan purchases are NOT done here: the wallet is
    # topped up first, then POST /api/v1/plans/{id}/purchase deducts the
    # plan price from the balance.
    amount = data.amount_irr
    if not isinstance(amount, int) or not (config.payment_min_irr <= amount <= config.payment_max_irr):
        return validation_error()

    # Idempotency: the frontend sends a fresh UUID per user intent via the
    # Idempotency-Key header (double-clicks / retries reuse it). Without a
    # header we mint a unique key so a legitimate retry after a failure
    # always creates a NEW payment with a fresh Zibal track_id — the old
    # static payreq-{user}-{amount} key permanently blocked retries of the
    # same amount.
    idempotency_key = request.headers.get("Idempotency-Key") or f"payreq-{uuid.uuid4().hex}"
    existing = db.session.query(Payment).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing is not None:
        if existing.user_id != g.current_user_id:
            return error_response("FORBIDDEN", status=403)
        # Only PENDING payments are reused. A FAILED payment must not block
        # a retry: fall through and create a fresh payment below.
        if existing.status != PAY_FAILED:
            return success_response(_payment_payload(existing))

    payment = Payment(
        user_id=g.current_user_id,
        gateway="zibal",
        amount_irr=amount,
        plan_id=None,
        status=PAY_CREATED,
        idempotency_key=idempotency_key,
    )
    db.session.add(payment)
    try:
        db.session.commit()
    except IntegrityError:
        # Lost a race with a concurrent request using the same idempotency
        # key (e.g. double-click): return the winner's payment instead of 500.
        db.session.rollback()
        winner = db.session.query(Payment).filter_by(idempotency_key=idempotency_key).one_or_none()
        if winner is not None and winner.user_id == g.current_user_id:
            log.info("idempotency race resolved for key %s", idempotency_key)
            return success_response(_payment_payload(winner))
        raise

    try:
        gateway = get_payment_gateway()
        start = gateway.create_payment(
            amount,
            config.zibal_callback_url,
            {"payment_id": payment.id, "user_id": g.current_user_id},
        )
    except ZibalNotConfigured as exc:
        payment.status = PAY_FAILED
        payment.failure_code = "GATEWAY_NOT_CONFIGURED"
        payment.failure_message = "payment provider is not configured"
        db.session.commit()
        log.error("zibal not configured: %s", exc)
        return error_response("PROVIDER_ERROR", status=502)
    except (ProviderError, ValueError, RuntimeError) as exc:
        payment.status = PAY_FAILED
        payment.failure_code = "GATEWAY_ERROR"
        db.session.commit()
        log.warning("payment create failed: %s", exc)
        return error_response("PROVIDER_ERROR", status=502)

    payment.track_id = start.track_id
    payment.status = PAY_PENDING
    db.session.commit()
    audit(
        db.session, actor_type="user", actor_id=g.current_user_id,
        action="payment.created", target_type="payment", target_id=payment.id,
        metadata={"amount_irr": amount}, ip_hash=ip_hash(client_ip()),
    )
    db.session.commit()
    payload = _payment_payload(payment)
    payload["payment_url"] = start.payment_url
    # Frontend expects `redirect_url` (see types/api.ts Payment).
    payload["redirect_url"] = start.payment_url
    return success_response(payload, status=201)


@bp.get("/payments")
@login_required
def list_payments():
    page, page_size = pagination_params()
    query = (
        db.session.query(Payment)
        .filter_by(user_id=g.current_user_id)
        .order_by(Payment.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([_payment_payload(p) for p in items], page, page_size, meta["total"])


@bp.get("/payments/<payment_id>")
@login_required
def get_payment(payment_id: str):
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return error_response("NOT_FOUND", status=404)
    if payment.user_id != g.current_user_id:
        return error_response("FORBIDDEN", status=403)
    return success_response(_payment_payload(payment))


def _settle_paid_payment(payment: Payment, verification: PaymentVerify) -> bool:
    """Credit a verified-paid payment exactly once, inside a row-locked
    transaction. Returns True when the payment ends up PAID."""
    try:
        locked = (
            db.session.query(Payment)
            .filter_by(id=payment.id)
            .with_for_update()
            .one()
        )
        if locked.status == PAY_PAID:
            db.session.commit()
            return True
        wallet = get_wallet_for_update(db.session, locked.user_id)
        plan = db.session.get(Plan, locked.plan_id) if locked.plan_id else None
        if plan is None:
            # Pure wallet top-up: credit the paid amount.
            try:
                deposit(
                    db.session,
                    wallet=wallet,
                    amount_irr=locked.amount_irr,
                    idempotency_key=f"payment:{locked.id}:deposit",
                    reference_type="payment",
                    reference_id=locked.id,
                    description="wallet top-up via zibal",
                )
            except DuplicateIdempotencyKey:
                log.info("payment %s already credited; skipping duplicate", locked.id)
        else:
            # Plan purchase: the price buys the quota bundle — the wallet is
            # NOT credited. Only the subscription is activated.
            activate_subscription(db.session, locked.user_id, plan)
        locked.status = PAY_PAID
        locked.paid_at = utcnow()
        locked.gateway_reference = verification.gateway_reference
        audit(
            db.session, actor_type="system", actor_id=None,
            action="payment.paid", target_type="payment", target_id=locked.id,
            metadata={"amount_irr": locked.amount_irr}, ip_hash=ip_hash(client_ip()),
        )
        db.session.commit()
        return True
    except Exception:  # noqa: BLE001
        db.session.rollback()
        log.exception("payment credit failed for %s", payment.id)
        return False


def _verify_with_gateway(payment: Payment) -> PaymentVerify | None:
    """Server-side verify against Zibal. Returns None on transport failure
    (caller must NOT mark the payment failed in that case — the outcome is
    unknown and the user can retry via the recheck endpoint)."""
    try:
        gateway = get_payment_gateway()
        return gateway.verify_payment(payment.track_id, payment.amount_irr)
    except ZibalNotConfigured:
        log.error("zibal verify called before gateway mapping is configured")
        return None
    except Exception:  # noqa: BLE001
        log.exception("zibal verify transport failure")
        return None


def _verify_confirms_paid(payment: Payment, verification: PaymentVerify | None) -> bool:
    """True only when Zibal explicitly confirms this exact payment."""
    return bool(
        verification is not None
        and verification.ok
        and verification.paid
        and verification.track_id == payment.track_id
    )


@bp.post("/payments/<payment_id>/recheck")
@login_required
def recheck_payment(payment_id: str):
    """Re-verify a pending payment with Zibal (e.g. the first verify failed
    on a network error, or the callback never arrived). Credits the wallet
    only when Zibal explicitly confirms the payment."""
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return error_response("NOT_FOUND", status=404)
    if payment.user_id != g.current_user_id:
        return error_response("FORBIDDEN", status=403)
    if payment.status == PAY_PAID:
        return success_response(_payment_payload(payment))
    if payment.status != PAY_PENDING or not payment.track_id:
        return error_response("INVALID_STATE", status=409)

    verification = _verify_with_gateway(payment)
    if verification is None:
        # Outcome unknown — keep it pending so the user can retry.
        return error_response("PROVIDER_ERROR", status=502)
    if _verify_confirms_paid(payment, verification):
        ok = _settle_paid_payment(payment, verification)
        db.session.refresh(payment)
        if ok:
            return success_response(_payment_payload(payment))
        return error_response("PROVIDER_ERROR", status=502)
    # Zibal says not paid: mark failed. If money was deducted from the
    # user's card, Zibal/Shaparak auto-reverses it (usually within 72h).
    payment.status = PAY_FAILED
    payment.failure_code = verification.error_code or "VERIFY_FAILED"
    db.session.commit()
    audit(
        db.session, actor_type="system", actor_id=None,
        action="payment.verify_failed", target_type="payment", target_id=payment.id,
        metadata={"failure_code": payment.failure_code, "via": "recheck"},
        ip_hash=ip_hash(client_ip()),
    )
    db.session.commit()
    return success_response(_payment_payload(payment))


@bp.get("/payments/callback/zibal")
def zibal_callback():
    """Zibal redirects the user's browser here. This only triggers a
    server-side verify; the query params themselves are never trusted.

    NOTE: exact callback parameter names come from the official Zibal docs
    (see providers/zibal.py TODO). We accept common variants and always
    re-verify directly with the gateway.
    """
    track_id = (
        request.args.get("track_id")
        or request.args.get("trackId")
        or request.args.get("TrackId")
        or request.args.get("fake_track_id")  # dev/test fake gateway only
    )
    frontend = config.frontend_origin.rstrip("/")

    def _redirect(status: str, payment_id: str | None = None):
        url = f"{frontend}/dashboard/wallet?payment={status}"
        if payment_id:
            url += f"&id={payment_id}"
        return redirect(url, code=302)

    if not track_id:
        return _redirect("failed")

    payment = db.session.query(Payment).filter_by(track_id=track_id).one_or_none()
    if payment is None:
        log.warning("zibal callback for unknown track_id")
        return _redirect("failed")

    # Idempotent: a repeated callback for an already-paid payment is a no-op.
    if payment.status == PAY_PAID:
        return _redirect("success", payment.id)

    verification = _verify_with_gateway(payment)
    if verification is None:
        # Transport failure: the outcome is UNKNOWN (money may have moved).
        # Keep the payment pending so the user can recheck; tell the UI the
        # result is uncertain rather than a hard failure.
        return _redirect("unknown", payment.id)

    if not _verify_confirms_paid(payment, verification):
        payment.status = PAY_FAILED
        payment.failure_code = verification.error_code or "VERIFY_FAILED"
        db.session.commit()
        audit(
            db.session, actor_type="system", actor_id=None,
            action="payment.verify_failed", target_type="payment", target_id=payment.id,
            metadata={"failure_code": payment.failure_code}, ip_hash=ip_hash(client_ip()),
        )
        db.session.commit()
        return _redirect("failed", payment.id)

    # --- credit exactly once, inside a row-locked transaction ---------------
    if _settle_paid_payment(payment, verification):
        return _redirect("success", payment.id)
    return _redirect("failed", payment.id)
