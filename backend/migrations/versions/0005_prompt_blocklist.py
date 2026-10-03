"""Prompt moderation: blocklist table + global kill switch.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_blocklist",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("phrase", sa.String(255), nullable=False, unique=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by_admin_id", sa.CHAR(36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "moderation_settings",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("prompt_filter_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("moderation_settings")
    op.drop_table("prompt_blocklist")
