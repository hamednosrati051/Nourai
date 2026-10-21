"""Add signup_source to users (site / bot / bazaar) and backfill it.

Backfill rules for existing rows: messenger-linked accounts are 'bot';
accounts with a paid Bazaar payment are 'bazaar'; everyone else is 'site'.
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("signup_source", sa.String(16), nullable=True),
    )
    op.create_index("ix_users_signup_source", "users", ["signup_source"])
    op.execute(
        "UPDATE users SET signup_source = 'bot' "
        "WHERE id IN (SELECT user_id FROM messenger_users)"
    )
    op.execute(
        "UPDATE users SET signup_source = 'bazaar' "
        "WHERE signup_source IS NULL AND id IN "
        "(SELECT user_id FROM payments WHERE gateway = 'bazaar' AND status = 'paid')"
    )
    op.execute(
        "UPDATE users SET signup_source = 'site' WHERE signup_source IS NULL"
    )


def downgrade():
    op.drop_index("ix_users_signup_source", table_name="users")
    op.drop_column("users", "signup_source")
