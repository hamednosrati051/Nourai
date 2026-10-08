"""Add messenger_users table for bot account linking (generic across platforms).

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
        "messenger_users",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        # 'bale' | 'eitaa' | 'telegram' — one table for all bot platforms.
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("platform_user_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("platform_username", sa.String(128), nullable=True),
        sa.Column("platform_first_name", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_user_id", name="uq_messenger_platform_user"),
    )
    op.create_index("ix_messenger_platform_user", "messenger_users", ["platform", "platform_user_id"])


def downgrade() -> None:
    op.drop_index("ix_messenger_platform_user", table_name="messenger_users")
    op.drop_table("messenger_users")
