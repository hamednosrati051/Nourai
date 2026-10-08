"""Make users.mobile_normalized nullable for bot-provisioned accounts.

Revision ID: 0013
Revises: 0012
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "mobile_normalized",
                    existing_type=sa.String(16),
                    nullable=True)


def downgrade() -> None:
    op.alter_column("users", "mobile_normalized",
                    existing_type=sa.String(16),
                    nullable=False)
