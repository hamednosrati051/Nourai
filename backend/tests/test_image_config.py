"""Tests for GET /image/config: the response must carry the flat fields the
user-facing page reads (models, allowed_mime_types, max_upload_bytes, ...),
not just the nested profile object."""
from __future__ import annotations

from app.extensions import db
from app.models import AiModel
from tests.conftest import user_headers


def _make_image_model(app):
    with app.app_context():
        m = AiModel(
            slug="img-model", display_name="Img", capability="image",
            provider_key="img", provider_model_name="img-model",
            provider_type="openai_compat", is_active=True, pricing_type="token",
        )
        db.session.add(m)
        db.session.commit()
        return m.id


def test_image_config_flat_shape(client, app, user):
    _make_image_model(app)
    headers = user_headers(client, user)
    resp = client.get("/api/v1/image/config", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    # Flat contract consumed by the frontend ImageConfig type.
    assert isinstance(data["models"], list) and len(data["models"]) == 1
    assert isinstance(data["allowed_mime_types"], list)
    assert "image/jpeg" in data["allowed_mime_types"]
    assert data["max_upload_bytes"] > 0
    assert data["max_input_pixels"] > 0
    assert data["max_input_width"] > 0
    assert data["max_input_height"] > 0
    # sizes/qualities are currently unpopulated but must be arrays, not missing.
    assert isinstance(data["sizes"], list)
    assert isinstance(data["qualities"], list)
