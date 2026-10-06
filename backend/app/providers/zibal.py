"""Zibal payment gateway adapter.

Implements create -> redirect -> callback -> server-side verify against the
official Zibal IPG API (https://help.zibal.ir/IPG/API/).

API mapping (from the official docs):
- Create:  POST {base_url}/request
            body: {"merchant", "amount" (rial), "callbackUrl",
                   "description", "orderId", "mobile" (optional)}
            ok:   {"result": 100, "trackId": <int>, ...}
            pay:  https://gateway.zibal.ir/start/{trackId}
- Verify:  POST {base_url}/verify
            body: {"merchant", "trackId"}
            ok:   {"result": 100, ...}            (paid)
                  {"result": 201, ...}            (already verified -> paid)
- Callback: Zibal redirects the browser with GET params
            ?success=1&trackId=...&orderId=...&status=...

Key safety properties:
- the callback only *starts* verification; success is recorded only after a
  direct server-side verify with matching track_id AND amount;
- verify is idempotent: repeated callbacks/verifies never create a second
  deposit (the ledger's idempotency key enforces this);
- raw gateway responses and secrets never reach the frontend or the logs.
"""
from __future__ import annotations

import logging
import time
import uuid

import httpx

from app.config import config
from app.providers.base import PaymentGateway, PaymentStart, PaymentVerify, ProviderError

log = logging.getLogger(__name__)

_CREATE_PATH = "/request"
_VERIFY_PATH = "/verify"
# Payment page host (per docs; the start path lives on the gateway host,
# not necessarily on a custom api base path).
_START_URL_TEMPLATE = "https://gateway.zibal.ir/start/{track_id}"
_REQUEST_TIMEOUT_SECONDS = 15
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (1, 3)

# Zibal result codes (per official docs).
_RESULT_OK = 100
_RESULT_ALREADY_VERIFIED = 201


class ZibalNotConfigured(ProviderError):
    def __init__(self):
        super().__init__(
            code="PROVIDER_ERROR",
            message="Zibal merchant / api base url is not configured",
        )


class ZibalPaymentGateway(PaymentGateway):
    def __init__(
        self,
        api_base_url: str | None = None,
        merchant: str | None = None,
        callback_url: str | None = None,
    ):
        self.api_base_url = (api_base_url or config.zibal_api_base_url).rstrip("/")
        self.merchant = merchant or config.zibal_merchant
        self.callback_url = callback_url or config.zibal_callback_url

    # -- amount unit ------------------------------------------------------
    def to_gateway_amount(self, amount_irr: int) -> int:
        """Zibal expects the amount in rial; our canonical unit is IRR
        (rial), so no conversion is needed."""
        if not isinstance(amount_irr, int) or amount_irr <= 0:
            raise ValueError("amount_irr must be a positive integer")
        return amount_irr

    # -- request building ---------------------------------------------------
    def _build_create_request(self, amount_irr: int, callback_url: str, metadata: dict):
        url = f"{self.api_base_url}{_CREATE_PATH}"
        body = {
            "merchant": self.merchant,
            "amount": self.to_gateway_amount(amount_irr),
            "callbackUrl": callback_url,
            "description": f"Noura wallet top-up ({metadata.get('payment_id', '')})",
            "orderId": str(metadata.get("payment_id") or metadata.get("user_id") or ""),
        }
        return url, body

    def _build_verify_request(self, track_id: str):
        url = f"{self.api_base_url}{_VERIFY_PATH}"
        body = {"merchant": self.merchant, "trackId": int(track_id)}
        return url, body

    def _normalise_create_response(self, response: httpx.Response) -> PaymentStart:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("PROVIDER_ERROR", f"zibal bad response: {exc}") from exc
        result = data.get("result")
        track_id = data.get("trackId")
        if response.status_code != 200 or result != _RESULT_OK or not track_id:
            raise ProviderError(
                "PROVIDER_ERROR",
                f"zibal request failed: result={result} message={data.get('message')}",
            )
        track_id = str(track_id)
        return PaymentStart(
            track_id=track_id,
            payment_url=_START_URL_TEMPLATE.format(track_id=track_id),
            raw={"result": result},
        )

    def _normalise_verify_response(self, response: httpx.Response, amount_irr: int) -> PaymentVerify:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("PROVIDER_ERROR", f"zibal bad response: {exc}") from exc
        result = data.get("result")
        track_id = data.get("trackId")
        paid = result in (_RESULT_OK, _RESULT_ALREADY_VERIFIED)
        gateway_amount = data.get("amount")
        try:
            gateway_amount = int(gateway_amount) if gateway_amount is not None else None
        except (TypeError, ValueError):
            gateway_amount = None
        # Amount must match what we asked for; a mismatch is treated as unpaid.
        if paid and gateway_amount is not None and gateway_amount != amount_irr:
            log.warning(
                "zibal verify amount mismatch: expected %s got %s",
                amount_irr, gateway_amount,
            )
            paid = False
        return PaymentVerify(
            ok=response.status_code == 200,
            paid=paid,
            track_id=str(track_id) if track_id is not None else None,
            gateway_reference=str(data.get("refNumber") or "") or None,
            amount_in_gateway_unit=gateway_amount,
            error_code=str(result) if not paid else None,
            error_message=str(data.get("message") or "") or None,
        )

    # -- transport ----------------------------------------------------------
    def _post(self, url: str, body: dict) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.post(url, json=body)
                if response.status_code >= 500 and attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
                    continue
                return response
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
                    continue
                break
        raise ProviderError("PROVIDER_ERROR", f"zibal unreachable: {last_exc}")

    # -- public API ----------------------------------------------------------
    def create_payment(self, amount_irr: int, callback_url: str, metadata: dict) -> PaymentStart:
        if not isinstance(amount_irr, int) or amount_irr <= 0:
            raise ValueError("amount_irr must be a positive integer")
        if not (self.api_base_url and self.merchant):
            raise ZibalNotConfigured()
        url, body = self._build_create_request(amount_irr, callback_url, metadata)
        response = self._post(url, body)
        result = self._normalise_create_response(response)
        log.info("zibal payment created track_id=%s", result.track_id)
        return result

    def verify_payment(self, track_id: str, amount_irr: int) -> PaymentVerify:
        if not track_id:
            raise ValueError("track_id is required")
        if not (self.api_base_url and self.merchant):
            raise ZibalNotConfigured()
        url, body = self._build_verify_request(track_id)
        response = self._post(url, body)
        result = self._normalise_verify_response(response, amount_irr)
        # Zibal's verify response may not echo the trackId; fall back to the
        # track_id we verified so the caller's track_id match check works.
        if result.track_id is None:
            result.track_id = str(track_id)
        # The caller (payments API) additionally matches result.track_id and
        # the amount against the internal payment row before crediting.
        log.info("zibal verify track_id=%s paid=%s", track_id, result.paid)
        return result

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def new_idempotency_key() -> str:
        return f"pay-{uuid.uuid4().hex}"
