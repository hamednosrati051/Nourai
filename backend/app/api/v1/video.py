"""Video generation: async jobs with wallet billing.

Text-to-video only. Jobs are queued to Celery; rendering takes minutes,
so the client polls ``GET /video/jobs/<id>`` until the job is terminal.
Billing mirrors image generation: reserve on create, settle (or release)
when the worker finishes.
"""
from __future__ import annotations

import logging

from flask import Blueprint, g, request
from sqlalchemy.orm import defer

from app.api.deps import (
    client_ip,
    error_response,
    ip_hash,
    login_required,
    paginate_query,
    paginated_response,
    pagination_params,
    rate_limited,
    success_response,
    validation_error,
)
from app.billing.ledger import (
    DuplicateIdempotencyKey,
    InsufficientBalance,
    get_wallet_for_update,
    reserve,
)
from app.billing.pricing import PricingRuleUnavailable, PricingService
from app.config import config
from app.extensions import db
from app.models import AiModel, Asset, GenerationJob, UsageEvent
from app.models.catalog import CAP_VIDEO_GENERATION
from app.models.jobs import (
    ASSET_GENERATED_VIDEO,
    JOB_QUEUED,
    MODE_TEXT_TO_VIDEO,
)
from app.services.audit import audit
from app.services.prompt_filter import find_blocked_phrase

log = logging.getLogger(__name__)

bp = Blueprint("video", __name__)

# Allowed clip lengths (seconds) and output sizes.
VIDEO_DURATIONS = (4, 8, 12)
# gen4 models support max 10s (not 12)
VIDEO_DURATIONS_GEN4 = (4, 8, 10)
VIDEO_SIZES = {
    "landscape": "1280x720",
    "portrait": "720x1280",
    "square": "1024x1024",
}


def _resolve_video_model(model_id: str | None) -> AiModel | None:
    """Explicit model_id wins; else the first active video model."""
    if model_id:
        model = db.session.get(AiModel, model_id)
        if model and model.capability == CAP_VIDEO_GENERATION and model.is_active:
            return model
        return None
    return (
        db.session.query(AiModel)
        .filter_by(capability=CAP_VIDEO_GENERATION, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )


def _durations_for_model(model: AiModel | None) -> tuple:
    """Return allowed durations based on model type."""
    if model and model.provider_model_name:
        name = model.provider_model_name.lower()
        if "gen4" in name:
            return VIDEO_DURATIONS_GEN4
    return VIDEO_DURATIONS


def _job_payload(job: GenerationJob) -> dict:
    """Shape matching the frontend VideoJob contract."""
    output_asset = (
        db.session.query(Asset)
        .filter_by(job_id=job.id, kind=ASSET_GENERATED_VIDEO)
        .order_by(Asset.created_at.desc())
        .first()
    )
    params = job.parameters_json or {}
    result_url = None
    if output_asset is not None:
        # Stream via the backend (same-origin, cookie auth). Presigned S3
        # URLs point at localhost and don't work in browsers.
        result_url = f"/api/v1/assets/{output_asset.id}/download?stream=1"
    model = db.session.get(AiModel, job.model_id) if job.model_id else None
    usage = db.session.query(UsageEvent).filter_by(job_id=job.id).first()
    return {
        "id": job.id,
        "type": job.mode,
        "status": job.status,
        "model_id": job.model_id,
        "model_name": model.display_name if model else None,
        "prompt": job.prompt_text,
        "seconds": params.get("seconds"),
        "size": params.get("size"),
        "cost_irr": usage.charged_amount_irr if usage else None,
        "result_url": result_url,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@bp.get("/video/config")
@login_required
def video_config():
    model = _resolve_video_model(None)
    return success_response({
        "durations": list(_durations_for_model(model)),
        "sizes": [{"key": k, "label": v} for k, v in VIDEO_SIZES.items()],
        "model_available": model is not None,
    })


@bp.post("/video/jobs")
@login_required
def create_video_job():
    if rate_limited(f"ai:req:{g.current_user_id}", config.rate_limit_ai_request,
                    config.rate_limit_ai_request_window):
        return error_response("RATE_LIMITED", status=429)

    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return validation_error()

    # Prompt blocklist: reject before any wallet hold or provider call.
    if find_blocked_phrase(db.session, prompt):
        return error_response(
            "PROMPT_BLOCKED",
            "این درخواست شامل محتوای غیرمجاز است؛ لطفاً بازنویسی کنید.",
            422,
        )

    try:
        seconds = int(body.get("seconds") or 4)
    except (TypeError, ValueError):
        seconds = 4
    if seconds not in VIDEO_DURATIONS:
        return validation_error()
    size_key = (body.get("size") or "landscape").strip().lower()
    size = VIDEO_SIZES.get(size_key, VIDEO_SIZES["landscape"])

    model = _resolve_video_model(body.get("model_id"))
    if model is None:
        return error_response("MODEL_UNAVAILABLE", "مدل فعال تولید ویدیو یافت نشد.", 404)

    try:
        seconds = int(body.get("seconds") or 4)
    except (TypeError, ValueError):
        seconds = 4
    if seconds not in _durations_for_model(model):
        return validation_error()

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_video(model.id, video_seconds=seconds)
    except PricingRuleUnavailable:
        db.session.rollback()
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)
    estimated_irr = estimate["total_irr"]

    job = GenerationJob(
        user_id=g.current_user_id,
        capability=CAP_VIDEO_GENERATION,
        model_id=model.id,
        status=JOB_QUEUED,
        prompt_text=prompt[:(model.max_prompt_chars or 4000)],
        mode=MODE_TEXT_TO_VIDEO,
        parameters_json={
            "seconds": seconds,
            "size": size,
            "size_key": size_key,
            "model_id": model.id,
            # Optional image-to-video (base64)
            "image_base64": body.get("image_base64"),
        },
    )
    db.session.add(job)
    db.session.flush()

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"video:{job.id}:reserve",
            reference_type="job", reference_id=job.id,
            description="reserve video generation",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass

    usage = UsageEvent(
        user_id=g.current_user_id, job_id=job.id, model_id=model.id,
        provider_key=model.provider_key, status="processing",
        pricing_snapshot_json=estimate["pricing_snapshots"],
        estimated_amount_irr=estimated_irr,
        reserved_amount_irr=estimated_irr,
        metadata_json={"idempotency_key": idempotency_key, "video_seconds": seconds},
    )
    db.session.add(usage)
    db.session.commit()

    audit(db.session, actor_type="user", actor_id=g.current_user_id,
          action="video.job_created", target_type="job", target_id=job.id,
          metadata={"seconds": seconds, "size": size}, ip_hash=ip_hash(client_ip()))
    db.session.commit()

    from app.tasks.video_tasks import process_video_job
    process_video_job.delay(job.id)

    return success_response(_job_payload(job), status=201)


@bp.get("/video/jobs")
@login_required
def list_video_jobs():
    page, page_size = pagination_params()
    # Defer heavy TEXT/JSON columns not needed for the list view — selecting
    # them all blows MySQL's sort buffer on ORDER BY created_at (error 1038).
    # prompt_text/parameters_json are lazy-loaded per-item by _job_payload.
    query = (
        db.session.query(GenerationJob)
        .options(
            defer(GenerationJob.result_text),
            defer(GenerationJob.error_message),
            defer(GenerationJob.processing_profile_snapshot_json),
            defer(GenerationJob.provider_request_id),
            defer(GenerationJob.prompt_text),
            defer(GenerationJob.parameters_json),
        )
        .filter_by(user_id=g.current_user_id, capability=CAP_VIDEO_GENERATION)
        .order_by(GenerationJob.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([_job_payload(j) for j in items], page, page_size, meta["total"])


@bp.get("/video/jobs/<job_id>")
@login_required
def get_video_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None or job.user_id != g.current_user_id or job.capability != CAP_VIDEO_GENERATION:
        return error_response("NOT_FOUND", status=404)
    return success_response(_job_payload(job))
