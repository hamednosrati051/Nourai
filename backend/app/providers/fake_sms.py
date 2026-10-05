"""Fake SMS provider for development and tests ONLY.

Refuses to run in production. Echoes the code back in ``dev_code`` so the
dev login page / tests can complete the OTP flow without a real gateway.
"""
from __future__ import annotations

import logging
import uuid

from app.auth.otp import mask_mobile
from app.config import config
from app.providers.base import SendOtpResult, SmsProvider

log = logging.getLogger(__name__)


class FakeSmsProvider(SmsProvider):
    def __init__(self):
        if config.is_production and not config.allow_fake_sms:
            raise RuntimeError("FakeSmsProvider must never be used in production")

    def send_otp(self, mobile: str, code: str) -> SendOtpResult:
        log.info("FAKE sms -> %s (code withheld from logs)", mask_mobile(mobile))
        return SendOtpResult(
            ok=True,
            provider_message_id=f"fake-{uuid.uuid4().hex[:12]}",
            dev_code=code,
        )
