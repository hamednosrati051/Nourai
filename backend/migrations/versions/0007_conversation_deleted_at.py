"""Add conversations.deleted_at (soft delete).

The Conversation.deleted_at column was added to the model in 11a23a9
("fix(chat): show assistant replies + soft-delete conversations") without
a migration, so databases migrated before this revision lack the column.

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "deleted_at")
