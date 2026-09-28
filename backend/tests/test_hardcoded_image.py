"""Image generation is hardcoded: provider settings come from code + env,
never from AiModel rows; image models cannot be defined via the admin
model form; only the tariff (pricing rules) stays configurable, anchored
on the system image model row."""
from __future__ import annotations

import pytest

from app.ai.adapters import (
    IMAGE_GEN_BASE_URL,
    IMAGE_GEN_MODEL,
    AsyncGenerationImageProvider,
    get_hardcoded_image_provider,
)
from app.api.v1.image import SYSTEM_IMAGE_MODEL_SLUG, ensure_system_image_model
from app.extensions import db
from app.models import AiModel, ModelPricingRule
from tests.conftest import admin_headers


def _legacy_image_model():
    m = AiModel(
        slug="legacy-img", display_name="Legacy", capability="image",
        provider_key="legacy", provider_model_name="google/nano-banana-2",
        provider_type="async_generation", is_active=True, pricing_type="image",
    )
    db.session.add(m)
    db.session.flush()
    rule = ModelPricingRule(
        model_id=m.id, version=1, billing_unit="image_count",
        unit_size=1, unit_price_irr=420000, is_active=True,
    )
    db.session.add(rule)
    db.session.commit()
    return m.id, rule.id


def test_hardcoded_provider_settings(app):
    assert IMAGE_GEN_BASE_URL == "https://platform-api.metisai.ir"
    assert IMAGE_GEN_MODEL == "google/nano-banana-2"
    # Without a token the provider refuses to build (token is never hardcoded).
    with pytest.raises(ValueError, match="IMAGE_API_KEY"):
        get_hardcoded_image_provider()


def test_hardcoded_provider_builds_with_env_token(app, monkeypatch):
    # The config field is captured at import, so patch the object directly.
    from app.config import config
    monkeypatch.setattr(config, "image_api_key", "test-token")
    provider = get_hardcoded_image_provider()
    assert isinstance(provider, AsyncGenerationImageProvider)
    assert provider.base_url == IMAGE_GEN_BASE_URL
    assert provider.api_key == "test-token"


def test_ensure_system_image_model_adopts_legacy(app):
    with app.app_context():
        legacy_id, rule_id = _legacy_image_model()
        model = ensure_system_image_model()
        assert model.slug == SYSTEM_IMAGE_MODEL_SLUG
        assert model.capability == "image"
        assert model.is_active is True
        # Legacy row deactivated; its active pricing rule moved to the system row.
        legacy = db.session.get(AiModel, legacy_id)
        assert legacy.is_active is False
        rule = db.session.get(ModelPricingRule, rule_id)
        assert rule.model_id == model.id
        assert rule.unit_price_irr == 420000
        # Idempotent: second call changes nothing.
        again = ensure_system_image_model()
        assert again.id == model.id


def test_admin_cannot_create_image_model(client, app, admin):
    with app.app_context():
        headers = admin_headers(client, admin)
    resp = client.post(
        "/api/v1/admin/models",
        json={
            "display_name": "Sneaky",
            "capability": "image",
            "provider_model_name": "x/y",
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.get_json()
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
