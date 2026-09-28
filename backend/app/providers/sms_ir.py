"""SMS.ir OTP adapter (production).

Sends the OTP through the account's approved pattern via the official
``POST /v1/send/verify`` endpoint ("ارسال VERIFY").

Reference: https://sms.ir/rest-api/ (official docs, read 2026-09-28).

- Auth: ``x-api-key`` header, key created in the sms.ir panel
  (developers -> API keys). For tests use a Sandbox-type key.
- Body: {"mobile": "9xxxxxxxxx", "templateId": <int>,
         "parameters": [{"name": "<pattern param>", "value": "<code>"}]}
- Success: {"status": 1, "message": "...", "data": {"messageId": N, "cost": X}}

NOTE: "likeToLike" (POST /v1/send/likeToLike) is a DIFFERENT method — it
sends a distinct text per recipient. OTP login must use VERIFY (pattern).
"""
from __future__ import annotations

import logging
import time

import httpx

from app.auth.otp import mask_mobile
from app.config import config
from app.providers.base import ProviderError, SendOtpResult, SmsProvider

log = logging.getLogger(__name__)

_SEND_PATH = "/send/verify"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (1, 3)

# sms.ir send status codes -> our error codes (docs section "کدهای وضعیت ارسال").
_STATUS_ERROR_MAP = {
    0: "PROVIDER_ERROR",
    10: "SMSIR_INVALID_KEY",
    11: "SMSIR_INACTIVE_KEY",
    12: "SMSIR_IP_RESTRICTED",
    13: "SMSIR_ACCOUNT_DISABLED",
    14: "SMSIR_ACCOUNT_SUSPENDED",
    20: "RATE_LIMITED",
    102: "SMSIR_INSUFFICIENT_CREDIT",
    104: "SMSIR_INVALID_MOBILE",
    113: "SMSIR_TEMPLATE_NOT_FOUND",
    114: "SMSIR_PARAM_TOO_LONG",
    115: "SMSIR_BLACKLISTED",
    116: "SMSIR_PARAM_NAME_EMPTY",
    117: "SMSIR_TEXT_NOT_APPROVED",
    119: "SMSIR_PLAN_UPGRADE_REQUIRED",
    123: "SMSIR_LINE_NOT_ACTIVATED",
}


class SmsIrNotConfigured(ProviderError):
    def __init__(self, detail: str = ""):
        super().__init__(
            code="PROVIDER_ERROR",
            message=f"sms.ir not configured: {detail}".strip(),
        )


class SmsIrProvider(SmsProvider):
    """Production SMS.ir provider (VERIFY / pattern method)."""

    def __init__(
        self,
        api_base_url: str | None = None,
        api_key=None,
        template_id: str | None = None,
        param_name: str | None = None,
    ):
        self.api_base_url = (api_base_url or config.smsir_api_base_url).rstrip("/")
        self.api_key = api_key or config.smsir_api_key
        self.template_id = template_id or config.smsir_template_id
        self.param_name = param_name or config.smsir_param_name

    def _check_configured(self) -> int:
        if not self.api_base_url:
            raise SmsIrNotConfigured("SMSIR_API_BASE_URL is empty")
        if not self.api_key:
            raise SmsIrNotConfigured("SMSIR_API_KEY is empty")
        if not self.template_id:
            raise SmsIrNotConfigured("SMSIR_TEMPLATE_ID is empty")
        try:
            template_id = int(self.template_id)
        except (TypeError, ValueError):
            raise SmsIrNotConfigured("SMSIR_TEMPLATE_ID must be an integer")
        if not self.param_name:
            raise SmsIrNotConfigured("SMSIR_PARAM_NAME is empty")
        return template_id

    def _build_request(self, mobile: str, code: str) -> tuple[str, dict, dict]:
        """Build (url, headers, json_body) for POST /v1/send/verify."""
        template_id = self._check_configured()
        # Nourai normalises to 09xxxxxxxxx; the docs example uses 9xxxxxxxxx.
        digits = mobile[1:] if mobile.startswith("0") else mobile
        url = f"{self.api_base_url}{_SEND_PATH}"
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "mobile": digits,
            "templateId": template_id,
            "parameters": [{"name": self.param_name, "value": code}],
        }
        return url, headers, body

    def _post(self, url: str, headers: dict, body: dict) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.post(url, headers=headers, json=body)
                # Retry only transient failures; never resend blindly.
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
        """Map the SMS.ir VERIFY response to SendOtpResult."""
        if response.status_code == 401:
            return SendOtpResult(ok=False, error_code="SMSIR_INVALID_KEY",
                                 error_message="authentication failed (HTTP 401)")
        if response.status_code == 429:
            return SendOtpResult(ok=False, error_code="RATE_LIMITED",
                                 error_message="sms.ir rate limit (HTTP 429)")
        try:
            payload = response.json()
        except ValueError:
            return SendOtpResult(ok=False, error_code="PROVIDER_ERROR",
                                 error_message=f"non-JSON response (HTTP {response.status_code})")
        status = payload.get("status")
        data = payload.get("data") or {}
        if response.status_code == 200 and status == 1:
            return SendOtpResult(
                ok=True,
                provider_message_id=str(data.get("messageId")) if data.get("messageId") is not None else None,
            )
        error_code = _STATUS_ERROR_MAP.get(status, "PROVIDER_ERROR")
        return SendOtpResult(ok=False, error_code=error_code,
                             error_message=str(payload.get("message") or "")[:200])

    def send_otp(self, mobile: str, code: str) -> SendOtpResult:
        masked = mask_mobile(mobile)
        log.info("sending OTP via sms.ir to %s", masked)
        try:
            url, headers, body = self._build_request(mobile, code)
            response = self._post(url, headers, body)
            result = self._normalise_response(response)
        except SmsIrNotConfigured:
            raise
        except ProviderError as exc:
            log.warning("sms.ir send failed for %s: %s", masked, exc)
            return SendOtpResult(ok=False, error_code=exc.code, error_message="send failed")
        # Never log the code, the API key or the raw response.
        log.info("sms.ir send to %s ok=%s err=%s", masked, result.ok, result.error_code)
        return result
