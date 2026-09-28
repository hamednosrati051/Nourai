"""Tests for the SMS.ir VERIFY provider (mocked HTTP, no real SMS)."""
from __future__ import annotations

import httpx
import pytest

from app.providers.sms_ir import SmsIrNotConfigured, SmsIrProvider


def _provider(**over):
    kw = {
        "api_base_url": "https://api.sms.ir/v1",
        "api_key": "test-key",
        "template_id": "123456",
        "param_name": "Code",
    }
    kw.update(over)
    return SmsIrProvider(**kw)


def _ok_response():
    return httpx.Response(
        200,
        json={"status": 1, "message": "موفق",
              "data": {"messageId": 89545112, "cost": 1.0}},
    )


def test_build_request_verify_shape():
    url, headers, body = _provider()._build_request("09123456789", "48210")
    assert url == "https://api.sms.ir/v1/send/verify"
    assert headers["x-api-key"] == "test-key"
    assert headers["Content-Type"] == "application/json"
    # Docs example uses the mobile without the leading zero.
    assert body == {
        "mobile": "9123456789",
        "templateId": 123456,
        "parameters": [{"name": "Code", "value": "48210"}],
    }


def test_missing_config_raises():
    with pytest.raises(SmsIrNotConfigured):
        _provider(api_key="")._build_request("09123456789", "1")
    with pytest.raises(SmsIrNotConfigured):
        _provider(template_id="not-an-int")._build_request("09123456789", "1")


def test_normalise_success():
    result = _provider()._normalise_response(_ok_response())
    assert result.ok is True
    assert result.provider_message_id == "89545112"


def test_normalise_error_codes():
    p = _provider()
    r = p._normalise_response(httpx.Response(
        200, json={"status": 102, "message": "اعتبار کافی نمی‌باشد", "data": {}}))
    assert r.ok is False and r.error_code == "SMSIR_INSUFFICIENT_CREDIT"
    r = p._normalise_response(httpx.Response(
        200, json={"status": 113, "message": "قالب یافت نشد", "data": {}}))
    assert r.ok is False and r.error_code == "SMSIR_TEMPLATE_NOT_FOUND"
    r = p._normalise_response(httpx.Response(401, json={"status": 10}))
    assert r.ok is False and r.error_code == "SMSIR_INVALID_KEY"
    r = p._normalise_response(httpx.Response(429, text="slow down"))
    assert r.ok is False and r.error_code == "RATE_LIMITED"
