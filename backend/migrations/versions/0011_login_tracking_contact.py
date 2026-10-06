"""Add last login IP/UA to users; eitaa/bale to site_settings.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_ip", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("last_login_user_agent", sa.String(512), nullable=True))
    op.add_column("site_settings", sa.Column("contact_eitaa", sa.String(128), nullable=True))
    op.add_column("site_settings", sa.Column("contact_bale", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("site_settings", "contact_bale")
    op.drop_column("site_settings", "contact_eitaa")
    op.drop_column("users", "last_login_user_agent")
    op.drop_column("users", "last_login_ip")
