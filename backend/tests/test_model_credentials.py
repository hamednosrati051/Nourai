"""Tests for the model PATCH credential behavior.

Credentials are write-only: editing a model without touching the token field
must preserve existing credentials, and half-provided credentials
(base_url without api_key or vice versa) are rejected with 422.
"""
from __future__ import annotations

from app.extensions import db
from app.models import AiModel
from tests.conftest import admin_headers


def _make_model(app, with_creds: bool = True):
    with app.app_context():
        cfg = (
            {"__provider__": {"base_url": "https://api.example.com/v1", "api_key": "old-key"}}
            if with_creds
            else None
        )
        m = AiModel(
            slug="cred-model", display_name="Cred Model", capability="text",
            provider_key="cred", provider_model_name="cred-model",
            provider_type="openai_compat", is_active=True, pricing_type="token",
            config_json=cfg,
        )
        db.session.add(m)
        db.session.commit()
        return m.id


def _creds(app, model_id):
    with app.app_context():
        m = db.session.get(AiModel, model_id)
        return (m.config_json or {}).get("__provider__")


def test_patch_without_credentials_preserves_existing(client, app, admin):
    """The edit-form scenario: base_url pre-filled, api_key empty -> 422 before
    the frontend fix; the frontend now omits both, so this locks in that
    omitting credentials preserves them."""
    model_id = _make_model(app)
    headers = admin_headers(client, admin)
    resp = client.patch(
        f"/api/v1/admin/models/{model_id}",
        json={"display_name": "Renamed"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    creds = _creds(app, model_id)
    assert creds["base_url"] == "https://api.example.com/v1"
    assert creds["api_key"] == "old-key"


def test_patch_base_url_only_rejected(client, app, admin):
    model_id = _make_model(app)
    headers = admin_headers(client, admin)
    resp = client.patch(
        f"/api/v1/admin/models/{model_id}",
        json={"base_url": "https://other.example.com/v1", "api_key": ""},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
    # Existing credentials untouched.
    assert _creds(app, model_id)["api_key"] == "old-key"


def test_patch_api_key_only_rejected(client, app, admin):
    model_id = _make_model(app)
    headers = admin_headers(client, admin)
    resp = client.patch(
        f"/api/v1/admin/models/{model_id}",
        json={"api_key": "new-key"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert _creds(app, model_id)["api_key"] == "old-key"


def test_patch_both_credentials_replaces(client, app, admin):
    model_id = _make_model(app)
    headers = admin_headers(client, admin)
    resp = client.patch(
        f"/api/v1/admin/models/{model_id}",
        json={"base_url": "https://new.example.com/v1", "api_key": "new-key"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    creds = _creds(app, model_id)
    assert creds["base_url"] == "https://new.example.com/v1"
    assert creds["api_key"] == "new-key"
    # api_key is write-only: never exposed via the API.
    assert "new-key" not in resp.get_data(as_text=True)