"""Add provider_type to ai_models; backfill from env per capability.

Revision ID: 0002
Revises: 0001
"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _env_provider(capability: str) -> str:
    if capability == "text":
        return (os.getenv("AI_TEXT_PROVIDER") or "fake").lower()
    if capability in ("speech_to_text", "text_to_speech"):
        return (os.getenv("AI_AUDIO_PROVIDER") or "fake").lower()
    if capability == "image":
        return (os.getenv("AI_IMAGE_PROVIDER") or "fake").lower()
    return "fake"


def upgrade() -> None:
    op.add_column(
        "ai_models",
        sa.Column("provider_type", sa.String(32), nullable=False, server_default="openai_compat"),
    )
    # Preserve each existing model's effective adapter: backfill from the env
    # that used to select it globally.
    conn = op.get_bind()
    capabilities = [r[0] for r in conn.execute(sa.text("SELECT DISTINCT capability FROM ai_models"))]
    for cap in capabilities:
        conn.execute(
            sa.text("UPDATE ai_models SET provider_type = :pt WHERE capability = :cap"),
            {"pt": _env_provider(cap), "cap": cap},
        )


def downgrade() -> None:
    op.drop_column("ai_models", "provider_type")
