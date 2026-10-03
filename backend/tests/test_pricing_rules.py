"""Tests for the admin pricing-rule edit flow (PATCH /admin/pricing-rules/<id>).

Price changes go through POST (new version); PATCH only touches the
non-price fields in place. This locks in that contract.
"""
from __future__ import annotations

from decimal import Decimal

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
            unit_size=1000, unit_price_usd=Decimal("0.01"), rounding_mode="up",
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
        json={"unit_price_usd": "99.99", "is_active": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    with app.app_context():
        rule = db.session.get(ModelPricingRule, rule_id)
        assert rule.unit_price_usd == Decimal("0.01")  # unchanged
        assert db.session.query(ModelPricingRule).count() == 1


def test_patch_unknown_rule_404(client, admin):
    headers = admin_headers(client, admin)
    resp = client.patch(
        "/api/v1/admin/pricing-rules/00000000-0000-0000-0000-000000000000",
        json={"is_active": False},
        headers=headers,
    )
    assert resp.status_code == 404


def test_list_pricing_rules_includes_model_name(client, app, admin):
    """GET /admin/pricing-rules returns model_name for each rule."""
    model_id, rule_id = _make_rule(app)
    headers = admin_headers(client, admin)
    resp = client.get("/api/v1/admin/pricing-rules", headers=headers)
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    match = [r for r in items if r["id"] == rule_id]
    assert match, "created rule not in list"
    assert match[0]["model_name"] == "Test"
    assert match[0]["model_id"] == model_id


def test_delete_pricing_rule(client, app, admin):
    """DELETE /admin/pricing-rules/<id> removes the rule (404 on unknown)."""
    _, rule_id = _make_rule(app)
    headers = admin_headers(client, admin)
    resp = client.delete(f"/api/v1/admin/pricing-rules/{rule_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["deleted"] is True
    with app.app_context():
        assert db.session.get(ModelPricingRule, rule_id) is None
    # second delete -> 404
    resp = client.delete(f"/api/v1/admin/pricing-rules/{rule_id}", headers=headers)
    assert resp.status_code == 404


def test_delete_pricing_rule_unlinks_usage_events(client, app, admin):
    """Deleting a rule clears pricing_rule_id on usage events (snapshot kept)."""
    from app.models import UsageEvent
    model_id, rule_id = _make_rule(app)
    with app.app_context():
        ev = UsageEvent(
            user_id="u1", model_id=model_id, pricing_rule_id=rule_id,
            pricing_snapshot_json={"unit_price_usd": "0.01"},
            charged_amount_irr=10000,
        )
        db.session.add(ev)
        db.session.commit()
        ev_id = ev.id
    headers = admin_headers(client, admin)
    resp = client.delete(f"/api/v1/admin/pricing-rules/{rule_id}", headers=headers)
    assert resp.status_code == 200
    with app.app_context():
        ev = db.session.get(UsageEvent, ev_id)
        assert ev.pricing_rule_id is None
        assert ev.pricing_snapshot_json == {"unit_price_usd": "0.01"}
        assert ev.charged_amount_irr == 10000


def test_patch_null_clears_optional_fields(client, app, admin):
    """Sending null for an optional field clears it; omitted fields stay."""
    _, rule_id = _make_rule(app)
    headers = admin_headers(client, admin)
    # set values first
    client.patch(f"/api/v1/admin/pricing-rules/{rule_id}", headers=headers, json={
        "minimum_charge_irr": 5000, "effective_from": "2026-09-01T00:00"})
    # now clear them with explicit nulls; omit maximum_charge_irr entirely
    resp = client.patch(f"/api/v1/admin/pricing-rules/{rule_id}", headers=headers, json={
        "minimum_charge_irr": None, "effective_from": None})
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["minimum_charge_irr"] is None
    assert body["effective_from"] is None
    with app.app_context():
        rule = db.session.get(ModelPricingRule, rule_id)
        assert rule.minimum_charge_irr is None
        assert rule.effective_from is None
