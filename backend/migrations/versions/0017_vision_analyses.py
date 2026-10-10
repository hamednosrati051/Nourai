"""Vision analyses table."""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vision_analyses",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("prompt", sa.Text, nullable=True),
        sa.Column("result_text", sa.Text, nullable=False),
        sa.Column("usage_event_id", sa.CHAR(36), sa.ForeignKey("usage_events.id"), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("vision_analyses")
