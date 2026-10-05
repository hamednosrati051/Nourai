"""Add cover_image_url to blog_posts.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("blog_posts", sa.Column("cover_image_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("blog_posts", "cover_image_url")
