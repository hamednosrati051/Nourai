"""Zibal payment gateway adapter.

Implements create -> redirect -> callback -> server-side verify.
The exact endpoint paths, request/response fields, response codes and the
amount unit expected by Zibal MUST come from the official Zibal API docs for
the version in use — they are marked TODO below and must be filled in with
the project owner's merchant information. Nothing is guessed here.

Key safety properties (implemented regardless of the mapping):
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

# TODO(Zibal integration): fill in from the official Zibal docs —
# request endpoints, field names, response codes and the amount unit.
_CREATE_PATH_TODO = "/TODO-from-official-docs"
_VERIFY_PATH_TODO = "/TODO-from-official-docs"
_REQUEST_TIMEOUT_SECONDS = 15
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (1, 3)


class ZibalNotConfigured(ProviderError):
    def __init__(self):
        super().__init__(
            code="PROVIDER_ERROR",
            message="Zibal request mapping is not configured (see TODO in providers/zibal.py)",
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
        """Convert canonical IRR to the amount unit Zibal expects.

        TODO(Zibal integration): confirm the expected unit (e.g. toman vs
        rial) in the official docs and implement the conversion here via
        app.billing.currency. Never convert inline elsewhere.
        """
        raise ZibalNotConfigured()

    # -- request building (TODO per official docs) -------------------------
    def _build_create_request(self, amount_irr: int, callback_url: str, metadata: dict):
        raise ZibalNotConfigured()

    def _build_verify_request(self, track_id: str):
        raise ZibalNotConfigured()

    def _normalise_create_response(self, response: httpx.Response) -> PaymentStart:
        raise ZibalNotConfigured()

    def _normalise_verify_response(self, response: httpx.Response, amount_irr: int) -> PaymentVerify:
        raise ZibalNotConfigured()

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
        # The caller (payments API) additionally matches result.track_id and
        # the amount against the internal payment row before crediting.
        log.info("zibal verify track_id=%s paid=%s", track_id, result.paid)
        return result

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def new_idempotency_key() -> str:
        return f"pay-{uuid.uuid4().hex}"
