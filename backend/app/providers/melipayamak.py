"""Melipayamak (ملی پیامک) OTP adapter (production).

Sends the OTP through the account's approved pattern via the REST
``POST /api/SendSMS/BaseServiceNumber`` endpoint.

Reference: https://www.melipayamak.com/api/sendbybasenumber/ (official docs)
and the official melipayamak-python sample library.

- Auth: panel ``username`` + ``password`` as form fields on every request.
  (Some accounts must use an API key instead — the API answers -110.)
- Body (form-encoded): ``username``, ``password``, ``text`` (pattern
  variables in order; for OTP just the code), ``to`` (one mobile number),
  ``bodyId`` (the approved pattern code from the panel).
- Success: HTTP 200 with JSON ``{"Value": "<recId>", "RetStatus": 1,
  "StrRetStatus": "Ok"}`` — ``RetStatus == 1`` means accepted.
- Known error values: -110 (use ApiKey instead of password), -109 (API IP
  not whitelisted), -108 (IP blocked after failed attempts).
"""
from __future__ import annotations

import logging
import time

import httpx

from app.auth.otp import mask_mobile
from app.config import config
from app.providers.base import ProviderError, SendOtpResult, SmsProvider

log = logging.getLogger(__name__)

_SEND_PATH = "/api/SendSMS/BaseServiceNumber"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (1, 3)

# Melipayamak RetStatus / return values -> our error codes.
_ERROR_MAP = {
    -110: "MELIPAYAMAK_USE_APIKEY",
    -109: "MELIPAYAMAK_IP_NOT_ALLOWED",
    -108: "MELIPAYAMAK_IP_BLOCKED",
    12: "MELIPAYAMAK_PROFILE_INCOMPLETE",
}


class MelipayamakNotConfigured(ProviderError):
    def __init__(self, detail: str = ""):
        super().__init__(
            code="PROVIDER_ERROR",
            message=f"melipayamak not configured: {detail}".strip(),
        )


class MelipayamakProvider(SmsProvider):
    """Production Melipayamak provider (pattern / BaseServiceNumber)."""

    def __init__(
        self,
        api_base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        body_id: str | None = None,
    ):
        self.api_base_url = (api_base_url or config.melipayamak_api_base_url).rstrip("/")
        self.username = username or config.melipayamak_username
        self.password = password or config.melipayamak_password
        self.body_id = body_id or config.melipayamak_body_id

    def _check_configured(self) -> None:
        if not self.api_base_url:
            raise MelipayamakNotConfigured("MELIPAYAMAK_API_BASE_URL is empty")
        if not self.username:
            raise MelipayamakNotConfigured("MELIPAYAMAK_USERNAME is empty")
        if not self.password:
            raise MelipayamakNotConfigured("MELIPAYAMAK_PASSWORD is empty")
        if not self.body_id:
            raise MelipayamakNotConfigured("MELIPAYAMAK_BODY_ID is empty")

    def _build_request(self, mobile: str, code: str) -> tuple[str, dict]:
        """Build (url, form_body) for POST /api/SendSMS/BaseServiceNumber."""
        self._check_configured()
        url = f"{self.api_base_url}{_SEND_PATH}"
        body = {
            "username": self.username,
            "password": self.password,
            "text": code,
            "to": mobile,
            "bodyId": self.body_id,
        }
        return url, body

    def _post(self, url: str, body: dict) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.post(url, data=body)
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
        raise ProviderError("PROVIDER_ERROR", f"sms gateway unreachable: {last_exc}")

    def _normalise_response(self, response: httpx.Response) -> SendOtpResult:
        """Map the BaseServiceNumber JSON response to SendOtpResult."""
        try:
            payload = response.json()
        except ValueError:
            return SendOtpResult(
                ok=False, error_code="PROVIDER_ERROR",
                error_message=f"non-JSON response (HTTP {response.status_code})",
            )
        # Success shape: {"Value": "<recId>", "RetStatus": 1, "StrRetStatus": "Ok"}
        try:
            ret_status = int(payload.get("RetStatus"))
        except (TypeError, ValueError):
            ret_status = None
        if response.status_code == 200 and ret_status == 1:
            value = payload.get("Value")
            return SendOtpResult(
                ok=True,
                provider_message_id=str(value) if value is not None else None,
            )
        error_code = _ERROR_MAP.get(ret_status, "PROVIDER_ERROR")
        return SendOtpResult(
            ok=False, error_code=error_code,
            error_message=str(payload.get("StrRetStatus") or "")[:200],
        )

    def send_otp(self, mobile: str, code: str) -> SendOtpResult:
        masked = mask_mobile(mobile)
        log.info("sending OTP via melipayamak to %s", masked)
        try:
            url, body = self._build_request(mobile, code)
            response = self._post(url, body)
            result = self._normalise_response(response)
        except MelipayamakNotConfigured:
            raise
        except ProviderError as exc:
            log.warning("melipayamak send failed for %s: %s", masked, exc)
            return SendOtpResult(ok=False, error_code=exc.code, error_message="send failed")
        # Never log the code, the password or the raw response.
        log.info("melipayamak send to %s ok=%s err=%s", masked, result.ok, result.error_code)
        return result
