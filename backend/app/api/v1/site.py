"""Public site info: contact page data."""
from __future__ import annotations

from flask import Blueprint

from app.api.deps import success_response
from app.models import SiteSettings, AiModel, ModelPricingRule, CurrencySettings
from app.extensions import db

bp = Blueprint("site", __name__)


def _get_settings() -> SiteSettings:
    settings = db.session.query(SiteSettings).first()
    if settings is None:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.flush()
    return settings


@bp.get("/site/contact")
def get_contact():
    """Public contact info for the contact page."""
    return success_response(_get_settings().to_dict())


@bp.get("/site/pricing")
def get_pricing():
    """Public pricing info: active models with tariffs and USD rate."""
    from datetime import datetime, timezone
    # Get USD to IRR rate
    currency = db.session.query(CurrencySettings).first()
    usd_to_irr = currency.usd_to_irr if currency else 0

    # Get active models with their pricing rules
    models = db.session.query(AiModel).filter(AiModel.is_active == True).all()
    now = datetime.now(timezone.utc)
    
    result = []
    for model in models:
        # Get active pricing rules, filtered by effective dates,
        # selecting highest version per billing unit
        rules_query = db.session.query(ModelPricingRule).filter(
            ModelPricingRule.model_id == model.id,
            ModelPricingRule.is_active == True,
            (ModelPricingRule.effective_from == None) | (ModelPricingRule.effective_from <= now),
            (ModelPricingRule.effective_to == None) | (ModelPricingRule.effective_to >= now),
        ).order_by(ModelPricingRule.billing_unit, ModelPricingRule.version.desc()).all()
        
        seen_units = set()
        pricing = []
        for rule in rules_query:
            if rule.billing_unit not in seen_units:
                seen_units.add(rule.billing_unit)
                pricing.append({
                    "billing_unit": rule.billing_unit,
                    "unit_price_usd": float(rule.unit_price_usd) if rule.unit_price_usd else 0,
                    "unit_size": rule.unit_size,
                })
        
        result.append({
            "capability": model.capability,
            "pricing": pricing,
        })

    return success_response({
        "usd_to_irr": usd_to_irr,
        "models": result,
    })
