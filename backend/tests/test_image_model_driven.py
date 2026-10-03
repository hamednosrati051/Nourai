"""Model-driven image providers: selector + job creation with model_id."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.adapters import (
    AsyncGenerationImageProvider,
    FakeImageProvider,
    OpenAICompatImageProvider,
    get_image_provider,
)
from decimal import Decimal

from app.extensions import db
from app.models import AiModel, ModelPricingRule, WalletAccount
from app.models.catalog import CAP_IMAGE
from tests.conftest import user_headers
from unittest.mock import patch


def _model(provider_type, base_url=None, api_key=None):
    cfg = {}
    if base_url or api_key:
        cfg["__provider__"] = {"base_url": base_url, "api_key": api_key}
    return SimpleNamespace(provider_type=provider_type, config_json=cfg)


def test_get_image_provider_fake():
    assert isinstance(get_image_provider("k", _model("fake")), FakeImageProvider)


def test_get_image_provider_openai_compat():
    p = get_image_provider("k", _model("openai_compat", "https://x/v1", "tok"))
    assert isinstance(p, OpenAICompatImageProvider)


def test_get_image_provider_async_generation():
    p = get_image_provider("k", _model("async_generation", "https://x", "tok"))
    assert isinstance(p, AsyncGenerationImageProvider)


def test_get_image_provider_unknown():
    with pytest.raises(ValueError):
        get_image_provider("k", _model("nope"))


def _make_image_model(app, slug="img-metis", provider_type="async_generation"):
    with app.app_context():
        m = AiModel(
            slug=slug, display_name="Img", capability=CAP_IMAGE,
            provider_key="metis", provider_model_name="google/nano-banana-2",
            provider_type=provider_type, is_active=True, pricing_type="image",
        )
        db.session.add(m)
        db.session.flush()
        rule = ModelPricingRule(
            model_id=m.id, version=1, billing_unit="image_count",
            unit_size=1, unit_price_usd=Decimal("0.0075188"), rounding_mode="up", is_active=True,
        )
        db.session.add(rule)
        db.session.commit()
        return m.id


def _fund_wallet(app, user_id):
    with app.app_context():
        db.session.add(WalletAccount(user_id=user_id, currency="IRR", balance_irr=500000, version=0))
        db.session.commit()


def test_create_image_job_with_model_id(client, app, user):
    model_id = _make_image_model(app)
    _fund_wallet(app, user)
    headers = user_headers(client, user)
    with patch("app.tasks.image_tasks.process_image_job"):
        resp = client.post(
            "/api/v1/image/jobs",
            json={"prompt": "a cat", "type": "text_to_image", "model_id": model_id},
            headers={**headers, "Idempotency-Key": "img-1"},
        )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["model_id"] == model_id


def test_create_image_job_no_model_available(client, app, user):
    _fund_wallet(app, user)
    headers = user_headers(client, user)
    resp = client.post(
        "/api/v1/image/jobs",
        json={"prompt": "a cat", "type": "text_to_image"},
        headers={**headers, "Idempotency-Key": "img-2"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "MODEL_UNAVAILABLE"
