"""Add messenger_user_states table for bot conversation state (generic).

Revision ID: 0014
Revises: 0013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messenger_user_states",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("platform", sa.String(16), nullable=False, index=True),
        sa.Column("platform_user_id", sa.BigInteger, nullable=False),
        sa.Column("mode", sa.String(64), nullable=False),
        sa.Column("data", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("platform", "platform_user_id", name="uq_messenger_state_user"),
    )


def downgrade() -> None:
    op.drop_table("messenger_user_states")
