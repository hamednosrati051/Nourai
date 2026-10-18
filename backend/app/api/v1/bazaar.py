"""CafeBazaar in-app purchase verification.

Flow (server-side verification):
1. The Android app initiates a purchase via Bazaar Billing for a SKU.
2. Bazaar returns a purchase receipt (purchase_data JSON + signature).
3. The app POSTs the receipt to /api/v1/bazaar/verify.
4. We verify the RSA signature with BAZAAR_RSA_PUBLIC_KEY.
5. We create a Payment (gateway='bazaar') and credit the wallet or
   activate the subscription based on the SKU — idempotently.

SKU mapping (must match the Bazaar panel):
  charge_50k   -> 500,000 IRR wallet credit
  charge_100k  -> 1,000,000 IRR wallet credit
  charge_200k  -> 2,000,000 IRR wallet credit
  charge_300k  -> 3,000,000 IRR wallet credit
  plan_basic   -> subscription (price 1,990,000)
  plan_economy -> subscription (price 3,990,000)
  plan_light   -> subscription (price 990,000)
  plan_image   -> subscription (price 5,990,000)
"""
from __future__ import annotations

import base64
import json
import logging
import uuid

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    client_ip,
    error_response,
    ip_hash,
    login_required,
    success_response,
    utcnow,
    validation_error,
)
from app.billing.ledger import DuplicateIdempotencyKey, deposit, get_wallet_for_update
from app.config import config
from app.extensions import db
from app.models import Payment, Plan
from app.models.payment import PAY_FAILED, PAY_PAID
from app.services.audit import audit
from app.services.plans import activate_subscription

log = logging.getLogger(__name__)

bp = Blueprint("bazaar", __name__)

# SKU -> wallet credit in IRR (None = subscription, resolved by price)
SKU_WALLET_CREDIT: dict[str, int | None] = {
    "charge_50k": 500_000,
    "charge_100k": 1_000_000,
    "charge_200k": 2_000_000,
    "charge_300k": 3_000_000,
    "plan_basic": None,
    "plan_economy": None,
    "plan_light": None,
    "plan_image": None,
}

# SKU -> plan price in IRR (for subscription SKUs)
SKU_PLAN_PRICE: dict[str, int] = {
    "plan_basic": 1_990_000,
    "plan_economy": 3_990_000,
    "plan_light": 990_000,
    "plan_image": 5_990_000,
}


class BazaarVerifySchema(BaseModel):
    # JSON string from Bazaar: {"orderId":..., "packageName":..., "productId":...,
    #   "purchaseToken":..., "purchaseState":0, ...}
    purchase_data: str
    # Base64 signature of purchase_data, signed with Bazaar's private key
    signature: str


def _verify_rsa_signature(purchase_data: str, signature_b64: str) -> bool:
    """Verify Bazaar's RSA signature over purchase_data.

    Uses BAZAAR_RSA_PUBLIC_KEY from config (X.509 DER, base64).
    Returns False on any error (missing key, bad signature, bad input).
    """
    public_key_b64 = config.bazaar_rsa_public_key
    if not public_key_b64:
        log.error("BAZAAR_RSA_PUBLIC_KEY not configured")
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key_der = base64.b64decode(public_key_b64)
        public_key = serialization.load_der_public_key(key_der)
        signature = base64.b64decode(signature_b64)
        public_key.verify(
            signature,
            purchase_data.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
        return True
    except Exception:  # noqa: BLE001
        log.warning("bazaar signature verification failed", exc_info=True)
        return False


@bp.post("/bazaar/verify")
@login_required
def verify_bazaar_purchase():
    try:
        data = BazaarVerifySchema(**(request.get_json(silent=True) or {}))
    except ValidationError:
        return validation_error()

    # 1. Parse purchase_data
    try:
        purchase = json.loads(data.purchase_data)
    except (json.JSONDecodeError, TypeError):
        return validation_error()
    sku = purchase.get("productId")
    purchase_token = purchase.get("purchaseToken")
    purchase_state = purchase.get("purchaseState")
    if not sku or not purchase_token:
        return validation_error()

    # Bazaar purchaseState: 0 = purchased, 1 = canceled, 2 = refunded
    if purchase_state != 0:
        return error_response("purchase not completed", status=422)

    # 2. SKU must be known
    if sku not in SKU_WALLET_CREDIT:
        log.warning("unknown bazaar sku: %s", sku)
        return error_response("unknown product", status=422)

    # 3. Verify RSA signature
    if not _verify_rsa_signature(data.purchase_data, data.signature):
        return error_response("invalid signature", status=422)

    # 4. Idempotency: same purchase_token must never credit twice.
    # We use the purchase_token as the idempotency key.
    idempotency_key = f"bazaar:{purchase_token}"
    existing = (
        db.session.query(Payment).filter_by(idempotency_key=idempotency_key).one_or_none()
    )
    if existing is not None:
        if existing.user_id != g.current_user_id:
            return error_response("forbidden", status=403)
        return success_response(
            {"payment_id": existing.id, "status": existing.status, "already_processed": True}
        )

    # 5. Resolve what the SKU buys
    wallet_credit = SKU_WALLET_CREDIT[sku]
    plan = None
    amount_irr = wallet_credit or 0
    if wallet_credit is None:
        # Subscription SKU: find the active plan by price
        plan_price = SKU_PLAN_PRICE[sku]
        plan = (
            db.session.query(Plan)
            .filter_by(price_irr=plan_price, is_active=True)
            .order_by(Plan.sort_order)
            .first()
        )
        if plan is None:
            log.error("no active plan found for bazaar sku %s (price %s)", sku, plan_price)
            return error_response("plan not available", status=422)
        amount_irr = plan_price

    # 6. Create the payment record + credit, atomically
    try:
        payment = Payment(
            id=str(uuid.uuid4()),
            user_id=g.current_user_id,
            gateway="bazaar",
            amount_irr=amount_irr,
            plan_id=plan.id if plan else None,
            status=PAY_PAID,
            idempotency_key=idempotency_key,
            gateway_reference=purchase.get("orderId"),
            paid_at=utcnow(),
        )
        db.session.add(payment)
        db.session.flush()

        wallet = get_wallet_for_update(db.session, g.current_user_id)
        if plan is None:
            try:
                deposit(
                    db.session,
                    wallet=wallet,
                    amount_irr=amount_irr,
                    idempotency_key=f"bazaar:{purchase_token}:deposit",
                    reference_type="payment",
                    reference_id=payment.id,
                    description=f"wallet top-up via bazaar ({sku})",
                )
            except DuplicateIdempotencyKey:
                log.info("bazaar purchase %s already credited", purchase_token)
        else:
            activate_subscription(db.session, g.current_user_id, plan)

        audit(
            db.session, actor_type="system", actor_id=None,
            action="payment.paid", target_type="payment", target_id=payment.id,
            metadata={"gateway": "bazaar", "sku": sku, "amount_irr": amount_irr},
            ip_hash=ip_hash(client_ip()),
        )
        db.session.commit()
    except IntegrityError:
        # Race: another request with the same purchase_token won.
        db.session.rollback()
        existing = (
            db.session.query(Payment).filter_by(idempotency_key=idempotency_key).one_or_none()
        )
        if existing is not None:
            return success_response(
                {"payment_id": existing.id, "status": existing.status, "already_processed": True}
            )
        log.exception("bazaar payment integrity error")
        return error_response("processing failed", status=500)
    except Exception:  # noqa: BLE001
        db.session.rollback()
        log.exception("bazaar verify failed")
        return error_response("processing failed", status=500)

    return success_response(
        {
            "payment_id": payment.id,
            "status": PAY_PAID,
            "sku": sku,
            "amount_irr": amount_irr,
            "already_processed": False,
        }
    )
