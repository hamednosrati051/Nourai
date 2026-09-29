"""Add currency_settings singleton table (USD->IRR rate, image cost margin).

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "currency_settings",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("usd_to_irr", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("image_cost_margin_pct", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # Seed the singleton row (usd_to_irr = 0 means "not configured").
    now = datetime.utcnow()
    op.execute(
        sa.text(
            "INSERT INTO currency_settings "
            "(id, usd_to_irr, image_cost_margin_pct, created_at, updated_at) "
            "VALUES (:id, 0, 30.0, :now, :now)"
        ).bindparams(id=str(uuid.uuid4()), now=now)
    )


def downgrade() -> None:
    op.drop_table("currency_settings")
