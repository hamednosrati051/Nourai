"""Initial schema: all Nourai tables with indexes.

Revision ID: 0001
Revises: None
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Microsecond-precision naive-UTC datetimes (DATETIME(6) on MySQL).
DT = mysql.DATETIME(fsp=6)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("mobile_normalized", sa.String(16), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mobile_verified_at", DT, nullable=True),
        sa.Column("last_login_at", DT, nullable=True),
        sa.Column("session_invalidated_at", DT, nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
    )

    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("mobile_normalized", sa.String(16), nullable=False, index=True),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="login"),
        sa.Column("code_hash", sa.CHAR(64), nullable=False),
        sa.Column("expires_at", DT, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("consumed_at", DT, nullable=True),
        sa.Column("request_ip_hash", sa.String(64), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_otp_challenges_mobile_created", "mobile_normalized", "created_at"),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", DT, nullable=True),
        sa.Column("session_invalidated_at", DT, nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
    )

    op.create_table(
        "wallet_accounts",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, unique=True, index=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="IRR"),
        sa.Column("balance_irr", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("wallet_id", sa.CHAR(36), sa.ForeignKey("wallet_accounts.id"),
                  nullable=False, index=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("amount_irr", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_irr", sa.BigInteger(), nullable=False),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.CHAR(36), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.CHAR(36),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_wallet_tx_wallet_created", "wallet_id", "created_at"),
        sa.Index("ix_wallet_tx_reference", "reference_type", "reference_id"),
    )

    op.create_table(
        "plans",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("price_irr", sa.BigInteger(), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("features_json", sa.JSON(), nullable=False),
        sa.Column("usage_limits_json", sa.JSON(), nullable=True),
        sa.Column("bonus_irr", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
    )

    op.create_table(
        "user_plan_subscriptions",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("plan_id", sa.CHAR(36), sa.ForeignKey("plans.id"),
                  nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="active", index=True),
        sa.Column("started_at", DT, nullable=False),
        sa.Column("expires_at", DT, nullable=False),
        sa.Column("usage_counters_json", sa.JSON(), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_subscriptions_user_status", "user_id", "status"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("gateway", sa.String(32), nullable=False, server_default="zibal"),
        sa.Column("amount_irr", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.CHAR(36), sa.ForeignKey("plans.id"),
                  nullable=True, index=True),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="created", index=True),
        sa.Column("track_id", sa.String(128), nullable=True, unique=True),
        sa.Column("gateway_reference", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("paid_at", DT, nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_payments_user_created", "user_id", "created_at"),
    )

    op.create_table(
        "ai_models",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("capability", sa.String(32), nullable=False, index=True),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("provider_model_name", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true(), index=True),
        sa.Column("pricing_type", sa.String(32), nullable=False),
        sa.Column("tokenizer_encoding", sa.String(64), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
    )

    op.create_table(
        "model_pricing_rules",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("model_id", sa.CHAR(36), sa.ForeignKey("ai_models.id"),
                  nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("billing_unit", sa.String(32), nullable=False),
        sa.Column("unit_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_irr", sa.BigInteger(), nullable=False),
        sa.Column("dimension_key", sa.String(64), nullable=True),
        sa.Column("quality_key", sa.String(64), nullable=True),
        sa.Column("minimum_charge_irr", sa.BigInteger(), nullable=True),
        sa.Column("maximum_charge_irr", sa.BigInteger(), nullable=True),
        sa.Column("rounding_mode", sa.String(16), nullable=False, server_default="up"),
        sa.Column("effective_from", DT, nullable=True),
        sa.Column("effective_to", DT, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_admin_id", sa.CHAR(36),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_pricing_model_active", "model_id", "is_active", "effective_from"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("model_id", sa.CHAR(36), sa.ForeignKey("ai_models.id"), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_conversations_user_created", "user_id", "created_at"),
    )

    # NOTE: assets.job_id -> generation_jobs.id is added after generation_jobs
    # is created (see end of upgrade()); the two tables reference each other.
    op.create_table(
        "assets",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("job_id", sa.CHAR(36), nullable=True, index=True),
        sa.Column("kind", sa.String(32), nullable=False, index=True),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("derived_from_asset_id", sa.CHAR(36),
                  sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("processing_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_assets_user_created", "user_id", "created_at"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("conversation_id", sa.CHAR(36), sa.ForeignKey("conversations.id"),
                  nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("input_asset_id", sa.CHAR(36), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("output_asset_id", sa.CHAR(36), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="succeeded"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    op.create_table(
        "message_assets",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("message_id", sa.CHAR(36), sa.ForeignKey("messages.id"),
                  nullable=False, index=True),
        sa.Column("asset_id", sa.CHAR(36), sa.ForeignKey("assets.id"),
                  nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_message_assets_unique", "message_id", "asset_id", unique=True),
    )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("capability", sa.String(32), nullable=False, index=True),
        sa.Column("model_id", sa.CHAR(36), sa.ForeignKey("ai_models.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="queued", index=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(32), nullable=True),
        sa.Column("source_asset_id", sa.CHAR(36), sa.ForeignKey("assets.id"), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("processing_profile_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", DT, nullable=True),
        sa.Column("finished_at", DT, nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_jobs_user_created", "user_id", "created_at"),
        sa.Index("ix_jobs_status_created", "status", "created_at"),
    )

    op.create_table(
        "gallery_entries",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("asset_id", sa.CHAR(36), sa.ForeignKey("assets.id"),
                  nullable=False, unique=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_admin_id", sa.CHAR(36),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("reviewed_at", DT, nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        # Fast retrieval of the latest approved images for the public gallery.
        sa.Index("ix_gallery_status_reviewed", "status", "reviewed_at"),
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("job_id", sa.CHAR(36), sa.ForeignKey("generation_jobs.id"),
                  nullable=True, index=True),
        sa.Column("model_id", sa.CHAR(36), sa.ForeignKey("ai_models.id"),
                  nullable=True, index=True),
        sa.Column("provider_key", sa.String(64), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True, index=True),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="succeeded", index=True),
        sa.Column("est_input_tokens", sa.Integer(), nullable=True),
        sa.Column("final_input_tokens", sa.Integer(), nullable=True),
        sa.Column("est_output_tokens", sa.Integer(), nullable=True),
        sa.Column("final_output_tokens", sa.Integer(), nullable=True),
        sa.Column("audio_seconds", sa.Integer(), nullable=True),
        sa.Column("image_count", sa.Integer(), nullable=True),
        sa.Column("input_pixels", sa.BigInteger(), nullable=True),
        sa.Column("output_pixels", sa.BigInteger(), nullable=True),
        sa.Column("tokenizer_encoding", sa.String(64), nullable=True),
        sa.Column("token_count_source", sa.String(32), nullable=True),
        sa.Column("pricing_rule_id", sa.CHAR(36),
                  sa.ForeignKey("model_pricing_rules.id"), nullable=True),
        sa.Column("pricing_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("estimated_amount_irr", sa.BigInteger(), nullable=True),
        sa.Column("reserved_amount_irr", sa.BigInteger(), nullable=True),
        sa.Column("charged_amount_irr", sa.BigInteger(), nullable=True),
        sa.Column("provider_cost_raw", sa.String(64), nullable=True),
        sa.Column("provider_cost_currency", sa.String(16), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_usage_user_created", "user_id", "created_at"),
        sa.Index("ix_usage_model_created", "model_id", "created_at"),
    )

    op.create_table(
        "image_processing_profiles",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("model_id", sa.CHAR(36), sa.ForeignKey("ai_models.id"),
                  nullable=True, index=True),
        sa.Column("max_upload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("max_input_pixels", sa.BigInteger(), nullable=False),
        sa.Column("allowed_mime_types_json", sa.JSON(), nullable=False),
        sa.Column("target_width", sa.Integer(), nullable=False),
        sa.Column("target_height", sa.Integer(), nullable=False),
        sa.Column("resize_mode", sa.String(16), nullable=False, server_default="fit"),
        sa.Column("allow_upscale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("output_format", sa.String(16), nullable=False, server_default="jpeg"),
        sa.Column("output_quality", sa.Integer(), nullable=False, server_default="85"),
        sa.Column("strip_metadata", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_admin_id", sa.CHAR(36),
                  sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_img_profile_model_active", "model_id", "is_active"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.CHAR(36), nullable=True),
        sa.Column("action", sa.String(128), nullable=False, index=True),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.Index("ix_audit_actor", "actor_type", "actor_id"),
        sa.Index("ix_audit_created", "created_at"),
        sa.Index("ix_audit_target", "target_type", "target_id"),
    )

    # Deferred FK: assets.job_id -> generation_jobs.id (cycle broken).
    op.create_foreign_key(
        "fk_assets_job_id", "assets", "generation_jobs", ["job_id"], ["id"]
    )


def downgrade() -> None:
    for table in (
        "audit_logs",
        "image_processing_profiles",
        "usage_events",
        "gallery_entries",
        "generation_jobs",
        "message_assets",
        "messages",
        "assets",
        "conversations",
        "model_pricing_rules",
        "ai_models",
        "payments",
        "user_plan_subscriptions",
        "plans",
        "wallet_transactions",
        "wallet_accounts",
        "admin_users",
        "otp_challenges",
        "users",
    ):
        op.drop_table(table)
