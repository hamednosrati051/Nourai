"""Add missing updated_at to contract_chat_sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    # Add updated_at if missing (0019 may not have created it properly)
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'contract_chat_sessions' "
        "AND COLUMN_NAME = 'updated_at'"
    ))
    if result.scalar() == 0:
        op.add_column(
            "contract_chat_sessions",
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
        )


def downgrade():
    op.drop_column("contract_chat_sessions", "updated_at")
