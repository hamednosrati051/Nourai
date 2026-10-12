"""Add updated_at to contract chat tables."""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    # Add updated_at to both tables (Base class requires it)
    for table in ["contract_chat_sessions", "contract_chat_messages"]:
        try:
            op.add_column(
                table,
                sa.Column("updated_at", sa.DateTime, nullable=False,
                          server_default=sa.text("CURRENT_TIMESTAMP")),
            )
        except Exception:
            # Column may already exist
            pass


def downgrade():
    for table in ["contract_chat_messages", "contract_chat_sessions"]:
        try:
            op.drop_column(table, "updated_at")
        except Exception:
            pass
