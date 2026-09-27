"""Tests for the admin pricing-rule edit flow (PATCH /admin/pricing-rules/<id>).

Price changes go through POST (new version); PATCH only touches the
non-price fields in place. This locks in that contract.
"""
from __future__ import annotations

from app.extensions import db
from app.models import AiModel, ModelPricingRule
from tests.conftest import admin_headers


def _make_rule(app):
    with app.app_context():
        m = AiModel(
            slug="test-model", display_name="Test", capability="text",
            provider_key="test", provider_model_name="test-model",
            provider_type="openai_compat", is_active=True, pricing_type="token",
        )
        db.session.add(m)
        db.session.flush()
        rule = ModelPricingRule(
            model_id=m.id, version=1, billing_unit="input_token",
            unit_size=1000, unit_price_irr=10000, rounding_mode="up",
            is_active=True,
        )
        db.session.add(rule)
        db.session.commit()
        return m.id, rule.id


def test_patch_updates_non_price_fields_in_place(client, app, admin):
    _, rule_id = _make_rule(app)
    headers = admin_headers(client, admin)
    resp = client.patch(
        f"/api/v1/admin/pricing-rules/{rule_id}",
        json={
            "is_active": False,
            "minimum_charge_irr": 5000,
            "maximum_charge_irr": 50000,
            "effective_from": "2026-09-01T00:00",
            "effective_to": "2026-12-01T00:00",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()["data"]
    assert body["is_active"] is False
    assert body["minimum_charge_irr"] == 5000
    assert body["maximum_charge_irr"] == 50000
    # Same version: PATCH never creates a new version.
    assert body["version"] == 1
    with app.app_context():
        assert db.session.query(ModelPricingRule).count() == 1


def test_patch_does_not_change_price(client, app, admin):
    """Sending a price in PATCH must not rewrite history (silently ignored)."""
    _, rule_id = _make_rule(app)
    headers = admin_headers(client, admin)
    resp = client.patch(
        f"/api/v1/admin/pricing-rules/{rule_id}",
        json={"unit_price_irr": 99999, "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    with app.app_context():
        rule = db.session.get(ModelPricingRule, rule_id)
        assert rule.unit_price_irr == 10000  # unchanged
        assert db.session.query(ModelPricingRule).count() == 1


def test_patch_unknown_rule_404(client, admin):
    headers = admin_headers(client, admin)
    resp = client.patch(
        "/api/v1/admin/pricing-rules/00000000-0000-0000-0000-000000000000",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 404
