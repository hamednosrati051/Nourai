"""Add source column to conversations (marks bot-originated threads)."""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("source", sa.String(32), nullable=True),
    )
    op.create_index(
        "ix_conversations_user_source", "conversations", ["user_id", "source"]
    )


def downgrade():
    op.drop_index("ix_conversations_user_source", table_name="conversations")
    op.drop_column("conversations", "source")
