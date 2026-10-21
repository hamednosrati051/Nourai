"""Add per-model history caps (max_history_messages / max_history_tokens).

NULL on existing rows: site chat and the main Bale bot fall back to the
built-in defaults (20 messages / 4000 tokens), so behavior is unchanged
until an admin sets values on a model.
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_models",
        sa.Column("max_history_messages", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_models",
        sa.Column("max_history_tokens", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_models", "max_history_tokens")
    op.drop_column("ai_models", "max_history_messages")
