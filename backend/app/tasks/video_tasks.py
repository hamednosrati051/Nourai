"""Video job worker: provider call -> output asset -> billing settlement.

Video rendering takes minutes; the provider adapter blocks inside this
task (create -> poll -> download). Retrying a finished job never charges
twice (idempotency keys on every ledger write).
"""
from __future__ import annotations

import hashlib
import logging

from app.ai.adapters import get_video_provider
from app.billing.pricing import PricingService
from app.extensions import db
from app.models import AiModel, Asset, GenerationJob, UsageEvent
from app.models.catalog import CAP_VIDEO_GENERATION
from app.models.jobs import (
    ASSET_GENERATED_VIDEO,
    JOB_FAILED,
    JOB_PROCESSING,
    JOB_SUCCEEDED,
)
from app.services.storage import asset_key, storage
from app.tasks import (
    aborted_during_processing,
    get_flask_app,
    release_job_billing,
    settle_job_billing,
)
from app.tasks.celery_app import celery

log = logging.getLogger(__name__)

_SAFE_ERROR = "تولید ویدیو ناموفق بود. لطفاً دوباره تلاش کنید."


@celery.task(bind=True, name="nourai.video.process", max_retries=2)
def process_video_job(self, job_id: str) -> dict:
    app = get_flask_app()
    with app.app_context():
        session = db.session
        job = session.get(GenerationJob, job_id)
        if job is None:
            log.error("video job %s not found", job_id)
            return {"ok": False, "error": "not_found"}
        if job.status not in ("queued", "processing"):
            # Already finished (e.g. redelivered task): do not recharge.
            log.info("video job %s already %s; skipping", job_id, job.status)
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
            log.exception("video job %s failed", job_id)
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
        seconds = int(params.get("seconds") or 4)
        estimate = pricing.estimate_video(job.model_id, video_seconds=seconds)
        final_amount = estimate["total_irr"]
        if usage is not None:
            usage.pricing_snapshot_json = estimate["pricing_snapshots"]
            settle_job_billing(session, job=job, usage=usage, final_amount_irr=final_amount)

        job.status = JOB_SUCCEEDED
        job.finished_at = utcnow()
        job.result_text = None
        session.commit()
        log.info("video job %s succeeded asset=%s", job_id, result_asset.id)
        return {"ok": True, "asset_id": result_asset.id}


def _run_provider(session, job: GenerationJob) -> Asset:
    params = job.parameters_json or {}
    model = session.get(AiModel, params.get("model_id") or job.model_id)
    if (
        model is None
        or model.capability != CAP_VIDEO_GENERATION
        or not model.is_active
    ):
        model = (
            session.query(AiModel)
            .filter_by(capability=CAP_VIDEO_GENERATION, is_active=True)
            .order_by(AiModel.created_at)
            .first()
        )
    if model is None:
        raise RuntimeError("no active video model")
    provider = get_video_provider(model.provider_key, model)
    options = {
        "seconds": int(params.get("seconds") or 4),
        "size": params.get("size") or "1280x720",
    }
    # Optional image-to-video
    if params.get("image_base64"):
        options["image_base64"] = params["image_base64"]
    # Resume safety: if a provider video ID was saved from a previous attempt, reuse it
    if params.get("provider_video_id"):
        options["provider_video_id"] = params["provider_video_id"]
    try:
        result = provider.generate(model.provider_model_name, job.prompt_text or "", options)
    finally:
        # Save provider video ID for retry safety (prevents duplicate video creation)
        if options.get("provider_video_id") and options["provider_video_id"] != params.get("provider_video_id"):
            params["provider_video_id"] = options["provider_video_id"]
            job.parameters_json = params
            session.commit()
    if not result.ok or not result.video_bytes:
        raise RuntimeError(result.error_code or "provider failed")

    key = asset_key(job.user_id, ASSET_GENERATED_VIDEO, "mp4")
    storage.put_bytes(key, result.video_bytes, result.mime_type or "video/mp4")

    asset = Asset(
        user_id=job.user_id,
        job_id=job.id,
        kind=ASSET_GENERATED_VIDEO,
        storage_key=key,
        mime_type=result.mime_type or "video/mp4",
        size_bytes=len(result.video_bytes),
        sha256=hashlib.sha256(result.video_bytes).hexdigest(),
        width=result.width,
        height=result.height,
        duration_seconds=result.duration_seconds,
        processing_metadata_json={
            "provider_request_id": result.provider_request_id,
            "provider_cost_cents": result.provider_cost_cents,
        },
    )
    session.add(asset)
    session.flush()
    return asset
