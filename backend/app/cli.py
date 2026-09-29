"""Flask CLI commands: create-admin (bootstrap) and seed-demo (dev only)."""
from __future__ import annotations

import logging

import click
from flask import Flask

from app.config import config

log = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    def create_admin() -> None:
        """Create the initial admin user from ADMIN_BOOTSTRAP_* env vars."""
        from app.extensions import db
        from app.models import AdminUser

        username = config.admin_bootstrap_username.strip()
        password = config.admin_bootstrap_password
        if not username or not password:
            raise click.ClickException(
                "ADMIN_BOOTSTRAP_USERNAME and ADMIN_BOOTSTRAP_PASSWORD must be set"
            )
        if len(password) < 12:
            raise click.ClickException("bootstrap password must be at least 12 characters")

        existing = db.session.query(AdminUser).filter_by(username=username).one_or_none()
        if existing:
            click.echo(f"admin '{username}' already exists; nothing to do")
            return
        admin = AdminUser(username=username, password_hash=_hash_password(password))
        db.session.add(admin)
        db.session.commit()
        # Never print the password.
        click.echo(f"admin '{username}' created")

    @app.cli.command("seed-demo")
    def seed_demo() -> None:
        """Seed demo catalog data. Development/test only."""
        from app.extensions import db
        from app.models import AiModel, ImageProcessingProfile, ModelPricingRule
        from app.models.catalog import CAP_IMAGE, CAP_STT, CAP_TEXT, CAP_TTS

        if config.is_production:
            raise click.ClickException("seed-demo is not allowed in production")

        def get_or_create_model(slug: str, **kwargs) -> AiModel:
            model = db.session.query(AiModel).filter_by(slug=slug).one_or_none()
            if model is None:
                model = AiModel(slug=slug, **kwargs)
                db.session.add(model)
                db.session.flush()
            return model

        text_model = get_or_create_model(
            "nourai-chat",
            display_name="گفت‌وگوی نورا",
            capability=CAP_TEXT,
            provider_key="fake",
            provider_type="fake",
            provider_model_name="fake-chat",
            is_active=True,
            pricing_type="token",
            tokenizer_encoding="cl100k_base",
            description="مدل گفت‌وگوی متنی",
        )
        stt_model = get_or_create_model(
            "nourai-stt",
            display_name="تبدیل گفتار به متن",
            capability=CAP_STT,
            provider_key="fake",
            provider_type="fake",
            provider_model_name="fake-stt",
            is_active=True,
            pricing_type="time",
        )
        tts_model = get_or_create_model(
            "nourai-tts",
            display_name="تبدیل متن به گفتار",
            capability=CAP_TTS,
            provider_key="fake",
            provider_type="fake",
            provider_model_name="fake-tts",
            is_active=True,
            pricing_type="time",
        )
        image_model = get_or_create_model(
            "nourai-image",
            display_name="تولید تصویر نورا",
            capability=CAP_IMAGE,
            provider_key="fake",
            provider_type="fake",
            provider_model_name="fake-image",
            is_active=True,
            pricing_type="image",
        )

        def ensure_rule(model_id: str, billing_unit: str, unit_size: int, unit_price_irr: int):
            rule = (
                db.session.query(ModelPricingRule)
                .filter_by(model_id=model_id, billing_unit=billing_unit, is_active=True)
                .first()
            )
            if rule is None:
                rule = ModelPricingRule(
                    model_id=model_id,
                    version=1,
                    billing_unit=billing_unit,
                    unit_size=unit_size,
                    unit_price_irr=unit_price_irr,
                    rounding_mode="up",
                    is_active=True,
                )
                db.session.add(rule)

        ensure_rule(text_model.id, "input_token", 1000, 500)
        ensure_rule(text_model.id, "output_token", 1000, 1500)
        ensure_rule(stt_model.id, "audio_second", 1, 200)
        ensure_rule(tts_model.id, "audio_second", 1, 300)
        ensure_rule(image_model.id, "image_count", 1, 20000)
        ensure_rule(image_model.id, "output_megapixel", 1, 5000)

        profile = (
            db.session.query(ImageProcessingProfile)
            .filter_by(model_id=None, is_active=True)
            .first()
        )
        if profile is None:
            profile = ImageProcessingProfile(
                name="پیش‌فرض سراسری",
                model_id=None,
                max_upload_bytes=min(8 * 1024 * 1024, config.image_upload_hard_max_bytes),
                max_input_pixels=min(12 * 1024 * 1024, config.image_input_hard_max_pixels),
                allowed_mime_types_json=["image/jpeg", "image/png", "image/webp"],
                target_width=1024,
                target_height=1024,
                resize_mode="fit",
                allow_upscale=False,
                output_format="jpeg",
                output_quality=85,
                strip_metadata=True,
                is_active=True,
                version=1,
            )
            db.session.add(profile)

        db.session.commit()
        click.echo("demo catalog seeded")

        # --- subscription plans (placeholder prices; admin-editable) ------------
        from app.models import Plan

        demo_plans = [
            {
                "name": "رایگان",
                "description": "شروع آشنایی با نورا",
                "price_irr": 0,
                "period_days": 30,
                "features": ["۲۰ گفت‌وگوی متنی در ماه", "۲ تولید تصویر در ماه", "دسترسی به مدل‌های پایه"],
                "usage_limits": {"monthly_text": 20, "monthly_image": 2},
                "bonus_irr": 0,
                "is_free": True,
                "is_featured": False,
                "sort_order": 1,
            },
            {
                "name": "پایه",
                "description": "مناسب استفاده سبک",
                "price_irr": 1_000_000,
                "period_days": 30,
                "features": ["اعتبار ۱۰۰ هزار تومان", "۵۰ گفت‌وگوی متنی در ماه", "۱۰ تولید تصویر در ماه"],
                "usage_limits": {"monthly_text": 50, "monthly_image": 10, "monthly_audio_minutes": 30},
                "bonus_irr": 0,
                "is_free": False,
                "is_featured": False,
                "sort_order": 2,
            },
            {
                "name": "حرفه‌ای",
                "description": "مناسب استفاده روزمره",
                "price_irr": 3_000_000,
                "period_days": 30,
                "features": ["اعتبار ۳۰۰ هزار تومان + ۳۰ هزار تومان هدیه", "۲۰۰ گفت‌وگوی متنی در ماه", "۵۰ تولید تصویر در ماه", "اولویت در صف پردازش"],
                "usage_limits": {"monthly_text": 200, "monthly_image": 50, "monthly_audio_minutes": 120},
                "bonus_irr": 300_000,
                "is_free": False,
                "is_featured": True,
                "sort_order": 3,
            },
            {
                "name": "سازمانی",
                "description": "برای استفاده سنگین و تیمی",
                "price_irr": 10_000_000,
                "period_days": 30,
                "features": ["اعتبار ۱ میلیون تومان + ۱۵۰ هزار تومان هدیه", "۱۰۰۰ گفت‌وگوی متنی در ماه", "۲۰۰ تولید تصویر در ماه", "پشتیبانی ویژه"],
                "usage_limits": {"monthly_text": 1000, "monthly_image": 200, "monthly_audio_minutes": 600},
                "bonus_irr": 1_500_000,
                "is_free": False,
                "is_featured": False,
                "sort_order": 4,
            },
        ]
        for spec in demo_plans:
            existing = db.session.query(Plan).filter_by(name=spec["name"]).one_or_none()
            if existing is None:
                db.session.add(Plan(
                    name=spec["name"],
                    description=spec["description"],
                    price_irr=spec["price_irr"],
                    period_days=spec["period_days"],
                    features_json=spec["features"],
                    usage_limits_json=spec["usage_limits"],
                    bonus_irr=spec["bonus_irr"],
                    is_free=spec["is_free"],
                    is_featured=spec["is_featured"],
                    is_active=True,
                    sort_order=spec["sort_order"],
                ))
        db.session.commit()
        click.echo("demo subscription plans seeded")

    @app.cli.command("cancel-stuck-jobs")
    @click.option("--status", "status_filter", default="queued",
                  help="Job status to cancel (default: queued).")
    def cancel_stuck_jobs(status_filter: str) -> None:
        """Cancel stuck generation jobs and release their wallet reserves.

        The worker skips any job whose status is not queued/processing,
        so already-delivered Celery tasks become harmless no-ops.
        """
        from app.extensions import db
        from app.models import GenerationJob, UsageEvent
        from app.models.jobs import JOB_CANCELLED
        from app.tasks import release_job_billing

        jobs = db.session.query(GenerationJob).filter_by(status=status_filter).all()
        if not jobs:
            click.echo(f"no jobs with status '{status_filter}'; nothing to do")
            return
        cancelled = 0
        for job in jobs:
            usage = (
                db.session.query(UsageEvent)
                .filter_by(job_id=job.id)
                .order_by(UsageEvent.created_at.desc())
                .first()
            )
            if usage is not None:
                release_job_billing(db.session, job=job, usage=usage,
                                    reason="cancelled by operator")
            job.status = JOB_CANCELLED
            db.session.commit()
            cancelled += 1
            click.echo(f"cancelled job {job.id} ({job.capability})")
        click.echo(f"done: {cancelled} job(s) cancelled, reserves released")

    @app.cli.command("sweep-stuck-jobs")
    @click.option("--minutes", default=30, show_default=True,
                  help="Fail 'processing' jobs older than this many minutes.")
    def sweep_stuck_jobs(minutes: int) -> None:
        """Fail stuck processing jobs and release their wallet reserves."""
        from app.tasks.sweep_tasks import sweep_stuck_jobs

        swept = sweep_stuck_jobs(max_age_minutes=minutes)
        click.echo(f"done: {swept} stuck job(s) failed, reserves released")
