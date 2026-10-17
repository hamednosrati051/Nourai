"""Add default_max_output_tokens to ai_models (per-model cap, admin-configurable)."""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_models",
        sa.Column("default_max_output_tokens", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_models", "default_max_output_tokens")
