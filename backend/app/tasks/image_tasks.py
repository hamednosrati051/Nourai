"""Image job worker: provider call -> output asset -> billing settlement.

Only the *processed* derivative of the user's upload is sent to the
provider; the original stays private. Retrying a finished job never
charges twice (idempotency keys on every ledger write).
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal

from app.ai.adapters import IMAGE_GEN_MODEL, get_hardcoded_image_provider
from app.billing.pricing import PricingService
from app.extensions import db
from app.models import Asset, GenerationJob, UsageEvent
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
from app.tasks import get_flask_app, release_job_billing, settle_job_billing
from app.tasks.celery_app import celery

log = logging.getLogger(__name__)

_SAFE_ERROR = "تولید تصویر ناموفق بود. لطفاً دوباره تلاش کنید."


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
        if usage is not None:
            usage.final_output_tokens = None
            usage.image_count = image_count
            usage.output_pixels = result_asset.width * result_asset.height
            usage.pricing_snapshot_json = estimate["pricing_snapshots"]
            settle_job_billing(session, job=job, usage=usage, final_amount_irr=final_amount)

        job.status = JOB_SUCCEEDED
        job.finished_at = utcnow()
        job.result_text = None
        PlanLimitService(session).increment(job.user_id, "image")
        session.commit()
        log.info("image job %s succeeded asset=%s", job_id, result_asset.id)
        return {"ok": True, "asset_id": result_asset.id}


def _run_provider(session, job: GenerationJob) -> Asset:
    from app.api.deps import utcnow

    # Hardcoded image backend: no model row is consulted. job.model_id is
    # the system row, used only as the billing anchor.
    provider = get_hardcoded_image_provider()
    params = job.parameters_json or {}
    options = {
        "width": params.get("width"),
        "height": params.get("height"),
        "quality": params.get("quality"),
    }
    if job.mode == MODE_IMAGE_TO_IMAGE:
        processed = (
            session.query(Asset)
            .filter_by(id=job.source_asset_id, kind=ASSET_INPUT_IMAGE_PROCESSED)
            .one()
        )
        # Only the processed derivative leaves our infrastructure.
        result = provider.edit(
            IMAGE_GEN_MODEL,
            job.prompt_text or "",
            processed.storage_key,
            options,
        )
    elif job.mode == MODE_TEXT_TO_IMAGE:
        result = provider.generate(IMAGE_GEN_MODEL, job.prompt_text or "", options)
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
        processing_metadata_json={"provider_request_id": result.provider_request_id},
    )
    session.add(asset)
    session.flush()
    return asset
