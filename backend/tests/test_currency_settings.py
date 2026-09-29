"""Currency settings admin API + image cost-plus-margin protection."""
from __future__ import annotations

from app.extensions import db
from app.models import CurrencySettings
from app.tasks.image_tasks import _apply_cost_protection
from tests.conftest import admin_headers


def _put(client, aheaders, payload):
    return client.put(
        "/api/v1/admin/settings/currency", headers=aheaders, json=payload
    )


def test_currency_settings_get_put(app, client, admin):
    aheaders = admin_headers(client, admin)

    r = client.get("/api/v1/admin/settings/currency", headers=aheaders)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["usd_to_irr"] == 0
    assert data["image_cost_margin_pct"] == 30.0

    r = _put(client, aheaders, {"usd_to_irr": 1_000_000, "image_cost_margin_pct": 25})
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json()["data"]
    assert data["usd_to_irr"] == 1_000_000
    assert data["image_cost_margin_pct"] == 25

    # Validation.
    r = _put(client, aheaders, {"usd_to_irr": -1, "image_cost_margin_pct": 30})
    assert r.status_code == 422
    r = _put(client, aheaders, {"usd_to_irr": 1_000_000, "image_cost_margin_pct": 101})
    assert r.status_code == 422


def _set_rate(session, usd_to_irr, margin_pct=30.0):
    s = (
        session.query(CurrencySettings)
        .order_by(CurrencySettings.created_at)
        .first()
    )
    if s is None:
        s = CurrencySettings()
        session.add(s)
    s.usd_to_irr = usd_to_irr
    s.image_cost_margin_pct = margin_pct
    session.flush()
    return s


def test_cost_protection_unknown_cost(app):
    with app.app_context():
        final, info = _apply_cost_protection(db.session, 420_000, None)
        assert final == 420_000
        assert info["applied"] is False


def test_cost_protection_no_rate(app):
    with app.app_context():
        _set_rate(db.session, 0)
        # 50 USD cents, but no rate configured -> tariff stands.
        final, info = _apply_cost_protection(db.session, 420_000, 5000)
        assert final == 420_000
        assert info["applied"] is False


def test_cost_protection_below_tariff(app):
    with app.app_context():
        _set_rate(db.session, 1_000_000)  # 1 USD = 1,000,000 IRR
        # 10 USD cents = 0.1 USD = 100,000 IRR < 420,000 tariff.
        final, info = _apply_cost_protection(db.session, 420_000, 10)
        assert final == 420_000
        assert info["applied"] is False
        assert info["provider_cost_irr"] == 100_000


def test_cost_protection_above_tariff(app):
    with app.app_context():
        _set_rate(db.session, 1_000_000, margin_pct=30.0)
        # 50 USD cents = 0.5 USD = 500,000 IRR > 420,000 tariff.
        final, info = _apply_cost_protection(db.session, 420_000, 50)
        assert info["applied"] is True
        assert info["provider_cost_irr"] == 500_000
        assert final == 650_000  # 500,000 * 1.3
