"""Pricing in USD: unit_price_irr -> unit_price_usd.

Tariffs are now denominated in USD and converted to IRR at billing time
with the currency_settings.usd_to_irr rate in effect for each request.
Existing IRR prices are converted once at the 2026-10-03 admin-confirmed
rate of 2,660,000 IRR per USD, which is also seeded into currency_settings
wherever it was never configured (0 = not configured).

Revision ID: 0006
Revises: 0005
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Admin-confirmed USD->IRR rate (2026-10-03): 266,000 toman = 2,660,000 IRR.
USD_TO_IRR = Decimal("2660000")


def upgrade() -> None:
    op.add_column(
        "model_pricing_rules",
        sa.Column("unit_price_usd", sa.Numeric(20, 8), nullable=True),
    )
    # One-time conversion of the stored IRR tariffs to USD.
    op.execute(
        sa.text(
            "UPDATE model_pricing_rules "
            "SET unit_price_usd = unit_price_irr / :rate "
            "WHERE unit_price_irr IS NOT NULL"
        ).bindparams(rate=USD_TO_IRR)
    )
    op.alter_column("model_pricing_rules", "unit_price_usd", nullable=False)
    op.drop_column("model_pricing_rules", "unit_price_irr")

    # Seed the conversion rate wherever it was never configured.
    op.execute(
        sa.text(
            "UPDATE currency_settings SET usd_to_irr = :rate WHERE usd_to_irr = 0"
        ).bindparams(rate=int(USD_TO_IRR))
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    op.execute(
        sa.text(
            "INSERT INTO currency_settings "
            "(id, usd_to_irr, image_cost_margin_pct, created_at, updated_at) "
            "SELECT :id, :rate, 30.0, :now, :now "
            "WHERE NOT EXISTS (SELECT 1 FROM currency_settings)"
        ).bindparams(id=str(uuid4()), rate=int(USD_TO_IRR), now=now)
    )


def downgrade() -> None:
    op.add_column(
        "model_pricing_rules",
        sa.Column("unit_price_irr", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE model_pricing_rules "
            "SET unit_price_irr = FLOOR(unit_price_usd * :rate) "
            "WHERE unit_price_usd IS NOT NULL"
        ).bindparams(rate=USD_TO_IRR)
    )
    op.alter_column("model_pricing_rules", "unit_price_irr", nullable=False)
    op.drop_column("model_pricing_rules", "unit_price_usd")
