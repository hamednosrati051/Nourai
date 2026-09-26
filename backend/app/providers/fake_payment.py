"""Fake payment gateway for development and tests ONLY.

Refuses to run in production. Simulates the create -> callback -> verify
cycle locally so the wallet-credit flow (including idempotent double
callbacks) can be tested without a real gateway.
"""
from __future__ import annotations

import logging
import uuid

from app.config import config
from app.providers.base import PaymentGateway, PaymentStart, PaymentVerify

log = logging.getLogger(__name__)


class FakePaymentGateway(PaymentGateway):
    # track_id -> {"amount_irr": int, "paid": bool}
    _ledger: dict[str, dict] = {}

    def __init__(self):
        if config.is_production:
            raise RuntimeError("FakePaymentGateway must never be used in production")

    def create_payment(self, amount_irr: int, callback_url: str, metadata: dict) -> PaymentStart:
        track_id = f"fake-{uuid.uuid4().hex[:16]}"
        self._ledger[track_id] = {"amount_irr": amount_irr, "paid": True}
        log.info("FAKE payment created track_id=%s amount_irr=%d", track_id, amount_irr)
        return PaymentStart(
            track_id=track_id,
            payment_url=f"{callback_url}?fake_track_id={track_id}&success=1",
        )

    def verify_payment(self, track_id: str, amount_irr: int) -> PaymentVerify:
        record = self._ledger.get(track_id)
        if record is None:
            return PaymentVerify(ok=False, paid=False, track_id=track_id,
                                 error_code="NOT_FOUND", error_message="unknown track id")
        paid = bool(record["paid"]) and record["amount_irr"] == amount_irr
        return PaymentVerify(
            ok=True,
            paid=paid,
            track_id=track_id,
            gateway_reference=f"fake-ref-{track_id}",
            amount_in_gateway_unit=amount_irr,
            error_code=None if paid else "AMOUNT_MISMATCH",
        )
