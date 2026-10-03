"""Backfill gallery moderation queue for previously generated images.

New images are queued automatically by the worker on job success; this
fills the pending queue for images generated before that existed.

Revision ID: 0004
Revises: 0003
"""
from datetime import datetime
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: only generated images without a gallery entry get one.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT a.id, a.user_id FROM assets AS a "
            "LEFT JOIN gallery_entries AS g ON g.asset_id = a.id "
            "WHERE a.kind = 'generated_image' AND g.id IS NULL"
        )
    ).fetchall()
    now = datetime.utcnow()
    for asset_id, user_id in rows:
        conn.execute(
            sa.text(
                "INSERT INTO gallery_entries "
                "(id, asset_id, user_id, status, created_at, updated_at) "
                "VALUES (:id, :asset_id, :user_id, 'pending', :now, :now)"
            ).bindparams(
                id=str(uuid.uuid4()), asset_id=asset_id, user_id=user_id, now=now
            )
        )


def downgrade() -> None:
    # Remove only never-reviewed pending entries (admin decisions stay).
    op.execute(
        sa.text(
            "DELETE FROM gallery_entries "
            "WHERE status = 'pending' AND reviewed_at IS NULL"
        )
    )
