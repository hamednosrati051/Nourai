"""Tests for the Melipayamak (ملی پیامک) pattern provider (mocked HTTP, no real SMS)."""
from __future__ import annotations

import httpx
import pytest

from app.providers.melipayamak import MelipayamakNotConfigured, MelipayamakProvider


def _provider(**over):
    kw = {
        "api_base_url": "https://rest.payamak-panel.com",
        "username": "testuser",
        "password": "testpass",
        "body_id": "12345",
    }
    kw.update(over)
    return MelipayamakProvider(**kw)


def _ok_response():
    return httpx.Response(
        200,
        json={"Value": "932487592873459234", "RetStatus": 1, "StrRetStatus": "Ok"},
    )


def test_build_request_shape():
    url, body = _provider()._build_request("09123456789", "48210")
    assert url == "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"
    assert body == {
        "username": "testuser",
        "password": "testpass",
        "text": "48210",
        "to": "09123456789",
        "bodyId": "12345",
    }


def test_missing_config_raises():
    with pytest.raises(MelipayamakNotConfigured):
        _provider(username="")._build_request("09123456789", "1")
    with pytest.raises(MelipayamakNotConfigured):
        _provider(password="")._build_request("09123456789", "1")
    with pytest.raises(MelipayamakNotConfigured):
        _provider(body_id="")._build_request("09123456789", "1")


def test_normalise_success():
    result = _provider()._normalise_response(_ok_response())
    assert result.ok is True
    assert result.provider_message_id == "932487592873459234"


def test_normalise_error_codes():
    p = _provider()
    r = p._normalise_response(httpx.Response(
        200, json={"Value": "-110", "RetStatus": -110, "StrRetStatus": "error"}))
    assert r.ok is False and r.error_code == "MELIPAYAMAK_USE_APIKEY"
    r = p._normalise_response(httpx.Response(
        200, json={"Value": "-109", "RetStatus": -109, "StrRetStatus": "error"}))
    assert r.ok is False and r.error_code == "MELIPAYAMAK_IP_NOT_ALLOWED"


def test_normalise_non_json():
    p = _provider()
    r = p._normalise_response(httpx.Response(200, content=b"not json"))
    assert r.ok is False and r.error_code == "PROVIDER_ERROR"
