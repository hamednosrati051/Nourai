"""USD-denominated tariffs: conversion math, snapshots, and rate handling."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.billing.pricing import (
    PricingError,
    PricingService,
    snapshot_rule,
)
from app.extensions import db
from app.models import AiModel, ModelPricingRule
from app.models.settings import CurrencySettings


def _make_rule(app, usd="0.10", unit_size=100):
    with app.app_context():
        m = AiModel(
            slug="usd-test", display_name="USD", capability="text",
            provider_key="t", provider_model_name="t",
            provider_type="openai_compat", is_active=True, pricing_type="token",
        )
        db.session.add(m)
        db.session.flush()
        rule = ModelPricingRule(
            model_id=m.id, version=1, billing_unit="input_token",
            unit_size=unit_size, unit_price_usd=Decimal(usd),
            rounding_mode="up", is_active=True,
        )
        db.session.add(rule)
        db.session.commit()
        return rule.id


def test_calculate_converts_usd_to_irr(app):
    rule_id = _make_rule(app, usd="0.10", unit_size=100)  # $0.10 / 100 tokens
    with app.app_context():
        pricing = PricingService(db.session)
        rule = db.session.get(ModelPricingRule, rule_id)
        amount, breakdown = pricing.calculate(rule, 250)
        # ceil(250/100) = 3 units x $0.10 = $0.30 x 2,660,000 = 798,000 IRR
        assert amount == 798000
        assert breakdown["unit_price_usd"] == "0.1"
        assert breakdown["usd_to_irr"] == 2660000
        assert breakdown["amount_irr"] == 798000


def test_calculate_rounds_up_fractional_irr(app):
    rule_id = _make_rule(app, usd="0.00000037", unit_size=1000)
    with app.app_context():
        pricing = PricingService(db.session)
        rule = db.session.get(ModelPricingRule, rule_id)
        amount, _ = pricing.calculate(rule, 1000)
        # $0.00000037 x 2,660,000 = 0.9842 IRR -> ceil -> 1
        assert amount == 1


def test_snapshot_freezes_usd_price_and_rate(app):
    rule_id = _make_rule(app)
    with app.app_context():
        pricing = PricingService(db.session)
        rule = db.session.get(ModelPricingRule, rule_id)
        snap = snapshot_rule(rule, pricing.usd_to_irr)
        assert snap["unit_price_usd"] == "0.1"
        assert snap["usd_to_irr"] == 2660000
        assert "unit_price_irr" not in snap


def test_missing_rate_raises_loudly(app):
    with app.app_context():
        db.session.query(CurrencySettings).delete()
        db.session.commit()
        with pytest.raises(PricingError):
            PricingService(db.session)


def test_zero_rate_raises_loudly(app):
    with app.app_context():
        db.session.query(CurrencySettings).update({"usd_to_irr": 0})
        db.session.commit()
        with pytest.raises(PricingError):
            PricingService(db.session)
