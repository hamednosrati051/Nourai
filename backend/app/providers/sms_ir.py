"""SMS.ir OTP adapter (production).

Sends the OTP through the account's approved template. The exact endpoint
path, request fields and response codes MUST be taken from the official
SMS.ir API documentation for the version in use — they are marked TODO below
and must be filled in with the project owner's account information before
going live. Nothing is guessed here.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.auth.otp import mask_mobile
from app.config import config
from app.providers.base import ProviderError, SendOtpResult, SmsProvider

log = logging.getLogger(__name__)

# TODO(SMS.ir integration): replace with the official endpoint path and field
# names from the SMS.ir API docs (version in use) + the account's approved
# template. See README "Assumptions".
# Base URL comes from SMSIR_API_BASE_URL; the path/fields below are placeholders.
_SMSIR_SEND_PATH_TODO = "/TODO-from-official-docs"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (1, 3)


class SmsIrNotConfigured(ProviderError):
    def __init__(self):
        super().__init__(
            code="PROVIDER_ERROR",
            message="SMS.ir request mapping is not configured (see TODO in providers/sms_ir.py)",
        )


class SmsIrProvider(SmsProvider):
    """Production SMS.ir provider. Raises if used before the official API
    mapping is filled in."""

    def __init__(
        self,
        api_base_url: str | None = None,
        api_key: str | None = None,
        template_id: str | None = None,
    ):
        self.api_base_url = (api_base_url or config.smsir_api_base_url).rstrip("/")
        self.api_key = api_key or config.smsir_api_key
        self.template_id = template_id or config.smsir_template_id

    def _check_configured(self) -> None:
        if not (self.api_base_url and self.api_key and self.template_id):
            raise SmsIrNotConfigured()

    def _build_request(self, mobile: str, code: str) -> tuple[str, dict, dict]:
        """Build (url, headers, json_body) for the template-send call.

        TODO(SMS.ir integration): implement exactly per the official SMS.ir
        docs — endpoint path, authentication header/scheme, template parameter
        names and the OTP parameter name. Do NOT guess.
        """
        raise SmsIrNotConfigured()

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
        """Map the SMS.ir response to SendOtpResult.

        TODO(SMS.ir integration): map the official success/error codes here.
        """
        raise SmsIrNotConfigured()

    def send_otp(self, mobile: str, code: str) -> SendOtpResult:
        masked = mask_mobile(mobile)
        log.info("sending OTP via sms.ir to %s", masked)
        try:
            self._check_configured()
            url, headers, body = self._build_request(mobile, code)
            response = self._post(url, headers, body)
            result = self._normalise_response(response)
        except SmsIrNotConfigured:
            raise
        except ProviderError as exc:
            log.warning("sms.ir send failed for %s: %s", masked, exc)
            return SendOtpResult(ok=False, error_code=exc.code, error_message="send failed")
        # Never log the code, the API key or the raw response.
        log.info("sms.ir send to %s ok=%s", masked, result.ok)
        return result
