"""Add max_prompt_chars to ai_models (per-model input cap, admin-configurable)."""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ai_models",
        sa.Column("max_prompt_chars", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("ai_models", "max_prompt_chars")
