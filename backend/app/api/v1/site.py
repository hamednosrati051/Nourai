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
    # Get USD to IRR rate
    currency = db.session.query(CurrencySettings).first()
    usd_to_irr = currency.usd_to_irr if currency else 0

    # Get active models with their pricing rules
    models = db.session.query(AiModel).filter(AiModel.is_active == True).all()
    
    result = []
    for model in models:
        # Get active pricing rules for this model
        rules = db.session.query(ModelPricingRule).filter(
            ModelPricingRule.model_id == model.id,
            ModelPricingRule.is_active == True
        ).all()
        
        pricing = []
        for rule in rules:
            pricing.append({
                "billing_unit": rule.billing_unit,
                "unit_price_usd": float(rule.unit_price_usd) if rule.unit_price_usd else 0,
                "unit_size": rule.unit_size,
            })
        
        result.append({
            "slug": model.slug,
            "display_name": model.display_name,
            "capability": model.capability,
            "pricing": pricing,
        })

    return success_response({
        "usd_to_irr": usd_to_irr,
        "models": result,
    })
