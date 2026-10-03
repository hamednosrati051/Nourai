"""Central pricing service.

Tariffs are denominated in USD (``ModelPricingRule.unit_price_usd``) and
converted to integer IRR at billing time with the ``usd_to_irr`` rate from
``currency_settings`` in effect for the request. The final USD->IRR step
always rounds up so fractional rials never undercharge. Min/max charge
caps stay in IRR. Rounding behaviour for unit quantization is stored on
the rule and applied identically in estimates and in settlement. The rule
used for a request is snapshotted onto the usage event, so later admin
changes never rewrite old charges.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from app.models.catalog import ModelPricingRule
from app.models.settings import CurrencySettings

# Billing units (spec section 6)
UNIT_FIXED_REQUEST = "fixed_request"
UNIT_INPUT_TOKEN = "input_token"
UNIT_OUTPUT_TOKEN = "output_token"
UNIT_AUDIO_SECOND = "audio_second"
UNIT_IMAGE_COUNT = "image_count"
UNIT_INPUT_MEGAPIXEL = "input_megapixel"
UNIT_OUTPUT_MEGAPIXEL = "output_megapixel"

BILLING_UNITS = (
    UNIT_FIXED_REQUEST,
    UNIT_INPUT_TOKEN,
    UNIT_OUTPUT_TOKEN,
    UNIT_AUDIO_SECOND,
    UNIT_IMAGE_COUNT,
    UNIT_INPUT_MEGAPIXEL,
    UNIT_OUTPUT_MEGAPIXEL,
)

ROUND_UP = "up"
ROUND_DOWN = "down"
ROUND_NEAREST = "nearest"

ROUNDING_MODES = (ROUND_UP, ROUND_DOWN, ROUND_NEAREST)

_ROUNDING_MAP = {
    ROUND_UP: ROUND_CEILING,
    ROUND_DOWN: ROUND_FLOOR,
    ROUND_NEAREST: ROUND_HALF_UP,
}


class PricingError(Exception):
    pass


class PricingRuleUnavailable(PricingError):
    pass


def snapshot_rule(rule: ModelPricingRule, usd_to_irr: int) -> dict:
    """Frozen copy of the rule stored on the usage event.

    Includes the USD price and the conversion rate in effect, so the
    resulting IRR charge is fully auditable even after the admin changes
    the rate or the tariff.
    """
    return {
        "rule_id": rule.id,
        "model_id": rule.model_id,
        "version": rule.version,
        "billing_unit": rule.billing_unit,
        "unit_size": rule.unit_size,
        "unit_price_usd": format_usd(rule.unit_price_usd),
        "usd_to_irr": usd_to_irr,
        "dimension_key": rule.dimension_key,
        "quality_key": rule.quality_key,
        "minimum_charge_irr": rule.minimum_charge_irr,
        "maximum_charge_irr": rule.maximum_charge_irr,
        "rounding_mode": rule.rounding_mode,
    }


def format_usd(value) -> str:
    """Compact USD string for API payloads (strips Numeric padding)."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return str(d.normalize())


def get_usd_to_irr(session) -> int:
    """Current USD->IRR conversion rate; fails loudly when unset."""
    settings = (
        session.query(CurrencySettings)
        .order_by(CurrencySettings.created_at)
        .first()
    )
    rate = settings.usd_to_irr if settings else 0
    if not rate or rate <= 0:
        raise PricingError(
            "USD->IRR rate is not configured (admin: settings/currency)"
        )
    return int(rate)


class PricingService:
    def __init__(self, session):
        self.session = session
        # Conversion rate is pinned per service instance so an estimate and
        # its settlement use the same rate even if the admin changes it
        # mid-request.
        self.usd_to_irr = get_usd_to_irr(session)

    # -- rule lookup ------------------------------------------------------
    def get_active_rule(
        self,
        model_id: str,
        billing_unit: str,
        dimension_key: str | None = None,
        quality_key: str | None = None,
        at: datetime | None = None,
    ) -> ModelPricingRule:
        at = at or datetime.now()
        query = (
            self.session.query(ModelPricingRule)
            .filter(
                ModelPricingRule.model_id == model_id,
                ModelPricingRule.billing_unit == billing_unit,
                ModelPricingRule.is_active.is_(True),
            )
            .filter(
                (ModelPricingRule.effective_from.is_(None))
                | (ModelPricingRule.effective_from <= at)
            )
            .filter(
                (ModelPricingRule.effective_to.is_(None))
                | (ModelPricingRule.effective_to > at)
            )
        )
        if dimension_key is None:
            query = query.filter(ModelPricingRule.dimension_key.is_(None))
        else:
            query = query.filter(ModelPricingRule.dimension_key == dimension_key)
        if quality_key is None:
            query = query.filter(ModelPricingRule.quality_key.is_(None))
        else:
            query = query.filter(ModelPricingRule.quality_key == quality_key)

        rule = query.order_by(ModelPricingRule.version.desc()).first()
        if rule is None:
            raise PricingRuleUnavailable(
                f"no active pricing rule for model={model_id} unit={billing_unit}"
            )
        return rule

    # -- calculation ------------------------------------------------------
    def calculate(self, rule: ModelPricingRule, quantity: int | Decimal) -> tuple[int, dict]:
        """Price ``quantity`` (in the rule's unit) -> (amount_irr, breakdown).

        ``unit_size`` is how much quantity makes one priced unit
        (e.g. 1000 tokens, 1 second, 1 image). The tariff is in USD;
        the final conversion to IRR always rounds up.
        """
        if quantity < 0:
            raise PricingError("quantity must be non-negative")
        unit_size = rule.unit_size or 1
        rounding = _ROUNDING_MAP.get(rule.rounding_mode, ROUND_CEILING)

        units = (Decimal(quantity) / Decimal(unit_size)).quantize(
            Decimal("1"), rounding=rounding
        )
        amount_usd = units * Decimal(rule.unit_price_usd)
        amount = int(
            (amount_usd * Decimal(self.usd_to_irr)).quantize(
                Decimal("1"), rounding=ROUND_CEILING
            )
        )

        if rule.minimum_charge_irr is not None and amount < rule.minimum_charge_irr and quantity > 0:
            amount = int(rule.minimum_charge_irr)
        if rule.maximum_charge_irr is not None and amount > rule.maximum_charge_irr:
            amount = int(rule.maximum_charge_irr)

        breakdown = {
            "billing_unit": rule.billing_unit,
            "quantity": str(quantity),
            "unit_size": unit_size,
            "units_charged": int(units),
            "unit_price_usd": format_usd(rule.unit_price_usd),
            "usd_to_irr": self.usd_to_irr,
            "rounding_mode": rule.rounding_mode,
            "amount_irr": amount,
            "rule_version": rule.version,
        }
        return amount, breakdown

    # -- high-level estimates ----------------------------------------------
    def estimate_text(
        self,
        model_id: str,
        input_tokens: int,
        max_output_tokens: int,
    ) -> dict:
        """Estimate for a chat/text request (reserve uses max output tokens)."""
        lines = []
        total = 0
        snapshots = []
        for unit, qty in (
            (UNIT_INPUT_TOKEN, input_tokens),
            (UNIT_OUTPUT_TOKEN, max_output_tokens),
        ):
            try:
                rule = self.get_active_rule(model_id, unit)
            except PricingRuleUnavailable:
                continue  # model may price text as fixed_request only
            amount, breakdown = self.calculate(rule, qty)
            total += amount
            lines.append(breakdown)
            snapshots.append(snapshot_rule(rule, self.usd_to_irr))
        if not lines:
            rule = self.get_active_rule(model_id, UNIT_FIXED_REQUEST)
            amount, breakdown = self.calculate(rule, 1)
            total += amount
            lines.append(breakdown)
            snapshots.append(snapshot_rule(rule, self.usd_to_irr))
        return {
            "total_irr": total,
            "lines": lines,
            "pricing_snapshots": snapshots,
        }

    def estimate_audio(
        self,
        model_id: str,
        audio_seconds: int,
        text_model_id: str | None = None,
        est_input_tokens: int = 0,
        est_output_tokens: int = 0,
    ) -> dict:
        lines, snapshots, total = [], [], 0
        for unit, qty in (
            (UNIT_AUDIO_SECOND, audio_seconds),
            (UNIT_FIXED_REQUEST, 1),
        ):
            try:
                rule = self.get_active_rule(model_id, unit)
            except PricingRuleUnavailable:
                continue
            amount, breakdown = self.calculate(rule, qty)
            total += amount
            lines.append(breakdown)
            snapshots.append(snapshot_rule(rule, self.usd_to_irr))
        if text_model_id and (est_input_tokens or est_output_tokens):
            sub = self.estimate_text(text_model_id, est_input_tokens, est_output_tokens)
            total += sub["total_irr"]
            lines.extend(sub["lines"])
            snapshots.extend(sub["pricing_snapshots"])
        return {"total_irr": total, "lines": lines, "pricing_snapshots": snapshots}

    def estimate_image(
        self,
        model_id: str,
        image_count: int = 1,
        input_megapixels: Decimal | float | int = 0,
        output_megapixels: Decimal | float | int = 0,
        dimension_key: str | None = None,
        quality_key: str | None = None,
    ) -> dict:
        lines, snapshots, total = [], [], 0
        candidates = [
            (UNIT_FIXED_REQUEST, 1),
            (UNIT_IMAGE_COUNT, image_count),
            (UNIT_INPUT_MEGAPIXEL, input_megapixels),
            (UNIT_OUTPUT_MEGAPIXEL, output_megapixels),
        ]
        for unit, qty in candidates:
            if not qty:
                continue
            try:
                rule = self.get_active_rule(
                    model_id, unit,
                    dimension_key=dimension_key, quality_key=quality_key,
                )
            except PricingRuleUnavailable:
                # Fall back to a dimension/quality-agnostic rule for this unit.
                try:
                    rule = self.get_active_rule(model_id, unit)
                except PricingRuleUnavailable:
                    continue
            amount, breakdown = self.calculate(rule, qty)
            total += amount
            lines.append(breakdown)
            snapshots.append(snapshot_rule(rule, self.usd_to_irr))
        if not lines:
            raise PricingRuleUnavailable(
                f"no usable pricing rule for image model={model_id}"
            )
        return {"total_irr": total, "lines": lines, "pricing_snapshots": snapshots}
