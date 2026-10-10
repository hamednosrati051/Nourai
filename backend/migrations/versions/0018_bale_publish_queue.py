"""Bale publish queue table."""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bale_publish_queue",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("content_type", sa.String(16), nullable=False, index=True),
        sa.Column("content_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, index=True, server_default="pending"),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("reviewed_by_admin_id", sa.CHAR(36), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("bale_message_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("bale_publish_queue")
