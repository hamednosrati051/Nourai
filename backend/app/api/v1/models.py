"""Public model catalog: only active models, with transparent pricing info."""
from __future__ import annotations

from flask import Blueprint, g

from app.api.deps import login_required, success_response
from app.billing.pricing import PricingService
from app.extensions import db
from app.models import AiModel, ModelPricingRule

bp = Blueprint("models", __name__)


@bp.get("/models")
@login_required
def list_models():
    pricing = PricingService(db.session)
    models = (
        db.session.query(AiModel)
        .filter_by(is_active=True)
        .order_by(AiModel.capability, AiModel.display_name)
        .all()
    )
    items = []
    for model in models:
        price_info = []
        for rule in (
            db.session.query(ModelPricingRule)
            .filter_by(model_id=model.id, is_active=True)
            .order_by(ModelPricingRule.version.desc())
            .all()
        ):
            price_info.append({
                "billing_unit": rule.billing_unit,
                "unit_size": rule.unit_size,
                "unit_price_irr": rule.unit_price_irr,
                "dimension_key": rule.dimension_key,
                "quality_key": rule.quality_key,
                "minimum_charge_irr": rule.minimum_charge_irr,
                "maximum_charge_irr": rule.maximum_charge_irr,
                "rounding_mode": rule.rounding_mode,
            })
        items.append({
            "id": model.id,
            "slug": model.slug,
            "display_name": model.display_name,
            "capability": model.capability,
            "pricing_type": model.pricing_type,
            "description": model.description,
            "pricing": price_info,
        })
    return success_response(items)
