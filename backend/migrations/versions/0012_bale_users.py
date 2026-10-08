"""Add bale_users table for Bale bot account linking.

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bale_users",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("bale_user_id", sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("bale_username", sa.String(128), nullable=True),
        sa.Column("bale_first_name", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("bale_users")
