"""Provider factories: choose the configured implementation.

Fake providers are rejected in production (they raise on construction).
"""
from __future__ import annotations

from app.config import config
from app.providers.base import PaymentGateway, SmsProvider
from app.providers.fake_payment import FakePaymentGateway
from app.providers.fake_sms import FakeSmsProvider
from app.providers.sms_ir import SmsIrProvider
from app.providers.zibal import ZibalPaymentGateway


def get_sms_provider() -> SmsProvider:
    name = (config.sms_provider or "fake").lower()
    if name == "smsir":
        return SmsIrProvider()
    if name == "fake":
        return FakeSmsProvider()
    raise ValueError(f"unknown SMS_PROVIDER: {name}")


def get_payment_gateway() -> PaymentGateway:
    name = (config.payment_provider or "fake").lower()
    if name == "zibal":
        return ZibalPaymentGateway()
    if name == "fake":
        return FakePaymentGateway()
    raise ValueError(f"unknown PAYMENT_PROVIDER: {name}")
