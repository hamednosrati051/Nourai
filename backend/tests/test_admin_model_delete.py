"""DELETE /admin/models/<id>: unreferenced models delete, referenced ones 409."""
from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import AiModel, GenerationJob, ModelPricingRule
from tests.conftest import admin_headers


def _make_model(app, slug="del-test"):
    with app.app_context():
        m = AiModel(
            slug=slug, display_name="Del Test", capability="text",
            provider_key="t", provider_model_name="t",
            provider_type="openai_compat", is_active=False, pricing_type="token",
        )
        db.session.add(m)
        db.session.commit()
        return m.id


def test_delete_unreferenced_model(client, app, admin):
    model_id = _make_model(app)
    headers = admin_headers(client, admin)
    resp = client.delete(f"/api/v1/admin/models/{model_id}", headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(AiModel, model_id) is None


def test_delete_model_in_use_blocked(client, app, admin, user):
    model_id = _make_model(app)
    with app.app_context():
        db.session.add(GenerationJob(user_id=user, capability="text", model_id=model_id))
        db.session.add(ModelPricingRule(
            model_id=model_id, version=1, billing_unit="input_token",
            unit_size=1000, unit_price_usd=Decimal("0.00037594"), rounding_mode="up", is_active=True,
        ))
        db.session.commit()
    headers = admin_headers(client, admin)
    resp = client.delete(f"/api/v1/admin/models/{model_id}", headers=headers)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "MODEL_IN_USE"


def test_delete_missing_model_404(client, app, admin):
    headers = admin_headers(client, admin)
    resp = client.delete("/api/v1/admin/models/does-not-exist", headers=headers)
    assert resp.status_code == 404
