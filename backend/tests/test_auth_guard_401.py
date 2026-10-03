"""Auth guard regression: missing/invalid user token must yield 401, never 500.

Covers the NameError where ``app/api/deps.py::_load_token`` called
``log.warning`` without a module logger defined, turning every
unauthenticated /api/v1/me request into a 500.
"""
from __future__ import annotations


def test_me_without_cookie_is_401_not_500(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401, resp.get_data(as_text=True)


def test_me_with_garbage_cookie_is_401_not_500(client):
    client.set_cookie("nourai_at", "not-a-real-token")
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401, resp.get_data(as_text=True)
