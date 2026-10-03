"""Image job worker: provider call -> output asset -> billing settlement.

Only the *processed* derivative of the user's upload is sent to the
provider; the original stays private. Retrying a finished job never
charges twice (idempotency keys on every ledger write).
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal, ROUND_CEILING

from app.ai.adapters import get_image_provider
from app.billing.pricing import PricingService
from app.extensions import db
from app.models import AiModel, Asset, CurrencySettings, GenerationJob, UsageEvent
from app.models.catalog import CAP_EDIT_IMAGE, CAP_GENERATE_IMAGE, CAP_IMAGE, IMAGE_CAPABILITIES
from app.models.gallery import GALLERY_PENDING, GalleryEntry
from app.models.jobs import (
    ASSET_GENERATED_IMAGE,
    ASSET_INPUT_IMAGE_PROCESSED,
    JOB_FAILED,
    JOB_PROCESSING,
    JOB_SUCCEEDED,
    MODE_IMAGE_TO_IMAGE,
    MODE_TEXT_TO_IMAGE,
)
from app.services.storage import asset_key, storage
from app.services.plans import PlanLimitService
from app.tasks import (
    aborted_during_processing,
    get_flask_app,
    release_job_billing,
    settle_job_billing,
)
from app.tasks.celery_app import celery

log = logging.getLogger(__name__)

_SAFE_ERROR = "تولید تصویر ناموفق بود. لطفاً دوباره تلاش کنید."


def _apply_cost_protection(
    session, tariff_amount_irr: int, provider_cost_cents: int | None
) -> tuple[int, dict]:
    """Apply provider cost-plus-margin protection.

    Converts the provider-reported cost (USD cents) to IRR with the admin
    USD rate. When that cost exceeds our tariff, the user is charged
    cost * (1 + margin) instead. Returns (final_amount_irr, protection_info).

    Falls back to the tariff when the provider cost is unknown or the USD
    rate is not configured, so billing is never worse than before.
    """
    info: dict = {"applied": False}
    if not provider_cost_cents:
        return tariff_amount_irr, info
    settings = (
        session.query(CurrencySettings)
        .order_by(CurrencySettings.created_at)
        .first()
    )
    if settings is None or not settings.usd_to_irr:
        log.warning("image cost protection skipped: USD rate not configured")
        return tariff_amount_irr, info
    cost_irr = (
        Decimal(provider_cost_cents) / Decimal(100) * Decimal(settings.usd_to_irr)
    )
    info.update(
        {
            "provider_cost_cents": provider_cost_cents,
            "usd_to_irr": settings.usd_to_irr,
            "provider_cost_irr": int(cost_irr),
        }
    )
    if cost_irr > tariff_amount_irr:
        margin_pct = float(settings.image_cost_margin_pct or 0)
        final = int(
            (cost_irr * (Decimal(1) + Decimal(str(margin_pct)) / Decimal(100)))
            .to_integral_value(rounding=ROUND_CEILING)
        )
        info.update(
            {
                "applied": True,
                "margin_pct": margin_pct,
                "tariff_irr": tariff_amount_irr,
            }
        )
        log.info(
            "image cost protection applied: tariff=%s cost_irr=%s margin=%s%% final=%s",
            tariff_amount_irr,
            int(cost_irr),
            margin_pct,
            final,
        )
        return final, info
    return tariff_amount_irr, info


@celery.task(bind=True, name="nourai.image.process", max_retries=2)
def process_image_job(self, job_id: str) -> dict:
    app = get_flask_app()
    with app.app_context():
        session = db.session
        job = session.get(GenerationJob, job_id)
        if job is None:
            log.error("image job %s not found", job_id)
            return {"ok": False, "error": "not_found"}
        if job.status not in ("queued", "processing"):
            # Already finished (e.g. redelivered task): do not recharge.
            log.info("image job %s already %s; skipping", job_id, job.status)
            return {"ok": True, "already": job.status}

        usage = (
            session.query(UsageEvent)
            .filter_by(job_id=job.id)
            .order_by(UsageEvent.created_at.desc())
            .first()
        )

        from app.api.deps import utcnow

        job.status = JOB_PROCESSING
        job.started_at = utcnow()
        session.commit()

        try:
            result_asset = _run_provider(session, job)
        except Exception as exc:  # noqa: BLE001 - provider/storage failure
            log.exception("image job %s failed", job_id)
            job.status = JOB_FAILED
            job.error_code = "PROVIDER_ERROR"
            job.error_message = _SAFE_ERROR
            job.finished_at = utcnow()
            if usage is not None:
                release_job_billing(session, job=job, usage=usage, reason="provider failed")
            session.commit()
            return {"ok": False, "error": "PROVIDER_ERROR"}

        # The job may have been cancelled (admin) while the provider call
        # was in flight: release the hold instead of settling.
        if aborted_during_processing(session, job):
            return {"ok": False, "error": "CANCELLED"}

        # --- settle billing on actual consumption -------------------------
        pricing = PricingService(session)
        params = job.parameters_json or {}
        image_count = int(params.get("image_count") or 1)
        output_mp = Decimal(result_asset.width * result_asset.height) / Decimal(1_000_000)
        estimate = pricing.estimate_image(
            job.model_id,
            image_count=image_count,
            output_megapixels=output_mp,
            dimension_key=params.get("dimension_key"),
            quality_key=params.get("quality_key"),
        )
        final_amount = estimate["total_irr"]
        # --- provider cost protection ----------------------------------
        # If the provider's actual cost exceeds our tariff, charge
        # cost * (1 + margin) instead so we never lose money.
        provider_cost_cents = (result_asset.processing_metadata_json or {}).get(
            "provider_cost_cents"
        )
        final_amount, protection = _apply_cost_protection(
            session, final_amount, provider_cost_cents
        )
        if usage is not None:
            usage.final_output_tokens = None
            usage.image_count = image_count
            usage.output_pixels = result_asset.width * result_asset.height
            snapshots = estimate["pricing_snapshots"]
            if protection.get("applied"):
                snapshots = list(snapshots) + [{"cost_protection": protection}]
            usage.pricing_snapshot_json = snapshots
            settle_job_billing(session, job=job, usage=usage, final_amount_irr=final_amount)

        job.status = JOB_SUCCEEDED
        job.finished_at = utcnow()
        job.result_text = None
        PlanLimitService(session).increment(job.user_id, "image")
        _enqueue_gallery(session, result_asset, job.user_id)
        session.commit()
        log.info("image job %s succeeded asset=%s", job_id, result_asset.id)
        return {"ok": True, "asset_id": result_asset.id}


def _enqueue_gallery(session, asset, user_id: str) -> None:
    """Queue a generated image for gallery moderation (idempotent).

    Without this, the admin gallery's pending queue would stay empty
    forever: entries were only created when an admin approved/rejected.
    """
    existing = session.query(GalleryEntry).filter_by(asset_id=asset.id).one_or_none()
    if existing is None:
        session.add(
            GalleryEntry(asset_id=asset.id, user_id=user_id, status=GALLERY_PENDING)
        )


def _provider_options(params: dict) -> dict:
    """Options forwarded to the image provider.

    NOTE: job width/height are internal processing-profile targets, NOT an
    output-size request — they must not reach the provider. Some providers
    (e.g. AvalAI's qwen image models) reject the ``size`` parameter
    outright, so forwarding dimensions breaks generation.
    """
    return {
        "quality": params.get("quality"),
    }


def _run_provider(session, job: GenerationJob) -> Asset:
    from app.api.deps import utcnow

    # Model-driven image backend: the provider comes from the job's model
    # row (provider_type + form-stored credentials).
    params = job.parameters_json or {}
    model = session.get(AiModel, params.get("model_id") or job.model_id)
    if (
        model is None
        or model.capability not in IMAGE_CAPABILITIES
        or not model.is_active
        or (model.provider_type or "").lower() == "hardcoded"
    ):
        # Mode-aware fallback: edit jobs prefer the edit_image model,
        # generation jobs the generate_image model, then a legacy
        # "does both" image model.
        want = CAP_EDIT_IMAGE if job.mode == MODE_IMAGE_TO_IMAGE else CAP_GENERATE_IMAGE
        model = None
        for capability in (want, CAP_IMAGE):
            model = (
                session.query(AiModel)
                .filter_by(capability=capability, is_active=True)
                .filter(AiModel.provider_type != "hardcoded")
                .order_by(AiModel.created_at)
                .first()
            )
            if model is not None:
                break
    if model is None:
        raise RuntimeError("no active image model")
    provider = get_image_provider(model.provider_key, model)
    provider_model_name = model.provider_model_name
    options = _provider_options(params)
    if job.mode == MODE_IMAGE_TO_IMAGE:
        processed = (
            session.query(Asset)
            .filter_by(id=job.source_asset_id, kind=ASSET_INPUT_IMAGE_PROCESSED)
            .one()
        )
        # Only the processed derivative leaves our infrastructure.
        result = provider.edit(
            provider_model_name,
            job.prompt_text or "",
            processed.storage_key,
            options,
        )
    elif job.mode == MODE_TEXT_TO_IMAGE:
        result = provider.generate(provider_model_name, job.prompt_text or "", options)
    else:
        raise ValueError(f"unknown image job mode: {job.mode}")

    if not result.ok or not result.image_bytes:
        raise RuntimeError(result.error_code or "provider failed")

    key = asset_key(job.user_id, ASSET_GENERATED_IMAGE, "jpg")
    storage.put_bytes(key, result.image_bytes, result.mime_type)

    asset = Asset(
        user_id=job.user_id,
        job_id=job.id,
        kind=ASSET_GENERATED_IMAGE,
        storage_key=key,
        mime_type=result.mime_type,
        size_bytes=len(result.image_bytes),
        sha256=hashlib.sha256(result.image_bytes).hexdigest(),
        width=result.width,
        height=result.height,
        processing_metadata_json={
            "provider_request_id": result.provider_request_id,
            "provider_cost_cents": result.provider_cost_cents,
        },
    )
    session.add(asset)
    session.flush()
    return asset
