"""Add site_settings table for contact page info.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_settings",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("contact_phone", sa.String(64), nullable=True),
        sa.Column("contact_email", sa.String(128), nullable=True),
        sa.Column("contact_address", sa.String(512), nullable=True),
        sa.Column("contact_telegram", sa.String(128), nullable=True),
        sa.Column("contact_instagram", sa.String(128), nullable=True),
        sa.Column("contact_description", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(6), nullable=False),
        sa.Column("updated_at", sa.DateTime(6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("site_settings")
