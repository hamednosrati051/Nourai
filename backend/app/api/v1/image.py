"""Image generation: config, cost estimate, async jobs.

Uploads are validated (real MIME, size, pixel and dimension ceilings) and a
sanitised derivative is produced per the active admin profile *before* the
job is queued. The original and the derivative are two linked private
assets; only the derivative ever goes to the provider.
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError

from app.ai.image_pipeline import (
    HardCeilings,
    ImageValidationError,
    validate_and_process,
)
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
    utcnow,
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
from app.models import AiModel, Asset, GenerationJob, ImageProcessingProfile, UsageEvent
from app.models.catalog import CAP_IMAGE
from app.models.jobs import (
    ASSET_GENERATED_IMAGE,
    ASSET_INPUT_IMAGE_ORIGINAL,
    ASSET_INPUT_IMAGE_PROCESSED,
    JOB_QUEUED,
    MODE_IMAGE_TO_IMAGE,
    MODE_TEXT_TO_IMAGE,
)
from app.services.audit import audit
from app.services.plans import PlanLimitExceeded, PlanLimitService
from app.services.storage import asset_key, storage

log = logging.getLogger(__name__)

bp = Blueprint("image", __name__)


def get_active_profile(model_id: str | None = None) -> ImageProcessingProfile | None:
    """Model-specific active profile, else the global default."""
    if model_id:
        profile = (
            db.session.query(ImageProcessingProfile)
            .filter_by(model_id=model_id, is_active=True)
            .order_by(ImageProcessingProfile.version.desc())
            .first()
        )
        if profile:
            return profile
    return (
        db.session.query(ImageProcessingProfile)
        .filter_by(model_id=None, is_active=True)
        .order_by(ImageProcessingProfile.version.desc())
        .first()
    )


def _profile_payload(profile: ImageProcessingProfile | None) -> dict | None:
    if profile is None:
        return None
    return {
        "id": profile.id,
        "name": profile.name,
        "max_upload_bytes": profile.max_upload_bytes,
        "max_input_pixels": profile.max_input_pixels,
        "allowed_mime_types": profile.allowed_mime_types_json,
        "target_width": profile.target_width,
        "target_height": profile.target_height,
        "resize_mode": profile.resize_mode,
        "allow_upscale": profile.allow_upscale,
        "output_format": profile.output_format,
        "output_quality": profile.output_quality,
        "version": profile.version,
        "hard_ceilings": {
            "max_bytes": config.image_upload_hard_max_bytes,
            "max_pixels": config.image_input_hard_max_pixels,
            "max_width": config.image_input_hard_max_width,
            "max_height": config.image_input_hard_max_height,
        },
    }


def _resolve_image_model(model_id: str | None) -> AiModel | None:
    if model_id:
        model = db.session.get(AiModel, model_id)
        if model and model.capability == CAP_IMAGE and model.is_active:
            return model
        return None
    return (
        db.session.query(AiModel)
        .filter_by(capability=CAP_IMAGE, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )


def _job_payload(job: GenerationJob) -> dict:
    output_asset = (
        db.session.query(Asset)
        .filter_by(job_id=job.id, kind=ASSET_GENERATED_IMAGE)
        .order_by(Asset.created_at.desc())
        .first()
    )
    params = job.parameters_json or {}
    return {
        "id": job.id,
        "mode": job.mode,
        "status": job.status,
        "prompt_text": job.prompt_text,
        "parameters": params,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "output_asset_id": output_asset.id if output_asset else None,
        "output_width": output_asset.width if output_asset else params.get("width"),
        "output_height": output_asset.height if output_asset else params.get("height"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@bp.get("/image/config")
@login_required
def image_config():
    model_id = request.args.get("model_id")
    profile = get_active_profile(model_id)
    return success_response({
        "profile": _profile_payload(profile),
        "models": [
            {"id": m.id, "slug": m.slug, "display_name": m.display_name}
            for m in db.session.query(AiModel)
            .filter_by(capability=CAP_IMAGE, is_active=True)
            .order_by(AiModel.display_name)
            .all()
        ],
    })


class ImageEstimateSchema(BaseModel):
    prompt: str
    mode: str = MODE_TEXT_TO_IMAGE
    model_id: str | None = None
    width: int | None = None
    height: int | None = None
    input_width: int | None = None
    input_height: int | None = None
    dimension_key: str | None = None
    quality_key: str | None = None


@bp.post("/image/estimate")
@login_required
def image_estimate():
    """Cost breakdown without reserving any balance. The server recomputes
    everything when the job is actually created; the client number is never
    trusted."""
    try:
        data = ImageEstimateSchema(**(request.get_json(silent=True) or {}))
    except ValidationError:
        return validation_error()
    if data.mode not in (MODE_TEXT_TO_IMAGE, MODE_IMAGE_TO_IMAGE):
        return validation_error()

    model = _resolve_image_model(data.model_id)
    if model is None:
        return error_response("MODEL_UNAVAILABLE", status=404)
    profile = get_active_profile(model.id)

    width = data.width or (profile.target_width if profile else 1024)
    height = data.height or (profile.target_height if profile else 1024)
    output_mp = Decimal(width * height) / Decimal(1_000_000)
    input_mp = Decimal(0)
    if data.mode == MODE_IMAGE_TO_IMAGE and data.input_width and data.input_height:
        input_mp = Decimal(data.input_width * data.input_height) / Decimal(1_000_000)

    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_image(
            model.id, image_count=1,
            input_megapixels=input_mp, output_megapixels=output_mp,
            dimension_key=data.dimension_key, quality_key=data.quality_key,
        )
    except PricingRuleUnavailable:
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)

    return success_response({
        "total_irr": estimate["total_irr"],
        "lines": estimate["lines"],
        "output_width": width,
        "output_height": height,
        "input_megapixels": str(input_mp),
        "output_megapixels": str(output_mp),
    })


@bp.post("/image/jobs")
@login_required
def create_image_job():
    if rate_limited(f"ai:req:{g.current_user_id}", config.rate_limit_ai_request,
                    config.rate_limit_ai_request_window):
        return error_response("RATE_LIMITED", status=429)

    try:
        PlanLimitService(db.session).check(g.current_user_id, "image")
    except PlanLimitExceeded:
        return error_response("PLAN_LIMIT_EXCEEDED", status=403)

    form = request.form
    prompt = (form.get("prompt") or "").strip()
    mode = form.get("mode") or MODE_TEXT_TO_IMAGE
    if not prompt or mode not in (MODE_TEXT_TO_IMAGE, MODE_IMAGE_TO_IMAGE):
        return validation_error()

    model = _resolve_image_model(form.get("model_id") or None)
    if model is None:
        return error_response("MODEL_UNAVAILABLE", status=404)
    profile = get_active_profile(model.id)
    if profile is None:
        return error_response("MODEL_UNAVAILABLE", "پروفایل پردازش تصویر تنظیم نشده است.", 500)
    profile_snapshot = profile.snapshot()

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    width = _as_int(form.get("width"), profile.target_width)
    height = _as_int(form.get("height"), profile.target_height)

    original_asset = processed_asset = None
    input_mp = Decimal(0)
    upload = request.files.get("file")

    if mode == MODE_IMAGE_TO_IMAGE:
        if upload is None:
            return validation_error()
        raw = upload.read()
        if not raw:
            return validation_error()
        try:
            processed = validate_and_process(raw, profile_snapshot, HardCeilings())
        except ImageValidationError as exc:
            return error_response(exc.code, status=413 if exc.code == "FILE_TOO_LARGE" else 422)

        # Store original (private) + processed derivative (private, linked).
        original_asset = _store_asset(
            ASSET_INPUT_IMAGE_ORIGINAL, raw, _sniff_mime_simple(raw),
            {"note": "original upload, never sent to provider"},
        )
        processed_asset = _store_asset(
            ASSET_INPUT_IMAGE_PROCESSED, processed.data, processed.mime_type,
            processed.metadata, derived_from=original_asset.id,
            width=processed.width, height=processed.height,
        )
        input_mp = Decimal(processed.width * processed.height) / Decimal(1_000_000)

    output_mp = Decimal(width * height) / Decimal(1_000_000)
    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_image(
            model.id, image_count=1,
            input_megapixels=input_mp, output_megapixels=output_mp,
            dimension_key=form.get("dimension_key") or None,
            quality_key=form.get("quality_key") or None,
        )
    except PricingRuleUnavailable:
        db.session.rollback()
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)
    estimated_irr = estimate["total_irr"]

    job = GenerationJob(
        user_id=g.current_user_id,
        capability="image",
        model_id=model.id,
        status=JOB_QUEUED,
        prompt_text=prompt[:4000],
        mode=mode,
        source_asset_id=processed_asset.id if processed_asset else None,
        parameters_json={
            "width": width, "height": height,
            "dimension_key": form.get("dimension_key") or None,
            "quality_key": form.get("quality_key") or None,
            "input_megapixels": str(input_mp),
            "output_megapixels": str(output_mp),
            "image_count": 1,
        },
        processing_profile_snapshot_json=profile_snapshot,
    )
    db.session.add(job)
    db.session.flush()

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"image:{job.id}:reserve",
            reference_type="job", reference_id=job.id,
            description="reserve image generation",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass

    for asset in (original_asset, processed_asset):
        if asset is not None:
            asset.job_id = job.id
    usage = UsageEvent(
        user_id=g.current_user_id, job_id=job.id, model_id=model.id,
        provider_key=model.provider_key, status="processing",
        image_count=1, input_pixels=int(input_mp * 1_000_000) if input_mp else 0,
        pricing_snapshot_json=estimate["pricing_snapshots"],
        estimated_amount_irr=estimated_irr, reserved_amount_irr=estimated_irr,
        metadata_json={"idempotency_key": idempotency_key},
    )
    db.session.add(usage)
    db.session.commit()

    audit(db.session, actor_type="user", actor_id=g.current_user_id,
          action="image.job_created", target_type="job", target_id=job.id,
          metadata={"mode": mode}, ip_hash=ip_hash(client_ip()))
    db.session.commit()

    from app.tasks.image_tasks import process_image_job
    process_image_job.delay(job.id)

    return success_response(_job_payload(job), status=201)


@bp.get("/image/jobs")
@login_required
def list_image_jobs():
    page, page_size = pagination_params()
    query = (
        db.session.query(GenerationJob)
        .filter_by(user_id=g.current_user_id, capability="image")
        .order_by(GenerationJob.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([_job_payload(j) for j in items], page, page_size, meta["total"])


@bp.get("/image/jobs/<job_id>")
@login_required
def get_image_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None or job.user_id != g.current_user_id or job.capability != "image":
        return error_response("NOT_FOUND", status=404)
    return success_response(_job_payload(job))


# -- helpers ---------------------------------------------------------------
def _as_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sniff_mime_simple(raw: bytes) -> str:
    if raw[:2] == b"\xff\xd8":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _store_asset(kind: str, data: bytes, mime: str, metadata: dict,
                 derived_from: str | None = None,
                 width: int | None = None, height: int | None = None) -> Asset:
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "bin")
    key = asset_key(g.current_user_id, kind, ext)
    try:
        storage.put_bytes(key, data, mime)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        raise RuntimeError(f"storage upload failed: {exc}") from exc
    asset = Asset(
        user_id=g.current_user_id, kind=kind, storage_key=key, mime_type=mime,
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        width=width, height=height, derived_from_asset_id=derived_from,
        processing_metadata_json=metadata,
    )
    db.session.add(asset)
    db.session.flush()
    return asset
