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
from app.models import AiModel, Asset, GenerationJob, ImageProcessingProfile, ModelPricingRule, UsageEvent
from app.models.catalog import CAP_EDIT_IMAGE, CAP_GENERATE_IMAGE, CAP_IMAGE, IMAGE_CAPABILITIES
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
    global_default = (
        db.session.query(ImageProcessingProfile)
        .filter_by(model_id=None, is_active=True)
        .order_by(ImageProcessingProfile.version.desc())
        .first()
    )
    if global_default is not None:
        return global_default
    # Self-heal: a fresh database has no profiles (they used to be created
    # only by the demo seed command). Create the global default on demand.
    profile = ImageProcessingProfile(
        name="پیش‌فرض سراسری",
        model_id=None,
        max_upload_bytes=min(5 * 1024 * 1024, config.image_upload_hard_max_bytes),
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
    db.session.flush()
    return profile


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


# Slug of the system-managed image model row. Image generation is hardcoded
# (see app.ai.adapters) and never reads provider config from the catalog;
# this row exists only as a stable anchor for pricing rules, so the image
# tariff stays configurable in the admin pricing section. It is created on
# demand and must not be created through the admin model form.
SYSTEM_IMAGE_MODEL_SLUG = "nourai-image"


def _resolve_image_model(model_id: str | None, mode: str | None = None) -> AiModel | None:
    """Explicit model_id wins; else the first active non-hardcoded image
    model matching the job mode (edit_image for image_to_image,
    generate_image otherwise), falling back to a legacy "does both"
    image model."""
    if model_id:
        model = db.session.get(AiModel, model_id)
        if (
            model
            and model.capability in IMAGE_CAPABILITIES
            and model.is_active
            and (model.provider_type or "").lower() != "hardcoded"
        ):
            return model
        return None
    want = CAP_EDIT_IMAGE if mode == MODE_IMAGE_TO_IMAGE else CAP_GENERATE_IMAGE
    for capability in (want, CAP_IMAGE):
        model = (
            db.session.query(AiModel)
            .filter_by(capability=capability, is_active=True)
            .filter(AiModel.provider_type != "hardcoded")
            .order_by(AiModel.created_at)
            .first()
        )
        if model is not None:
            return model
    return None


def ensure_system_image_model() -> AiModel:
    """Get (creating if needed) the system image model used for billing.

    The row is committed before returning: callers include read-only
    endpoints (e.g. the admin model listing) that never commit themselves.

    One-time adoption: active pricing rules from legacy image model rows are
    re-pointed onto the system row, and the legacy rows are deactivated.

    Only the row's existence is ensured here; an admin deactivation is
    respected and never reverted.
    """
    model = (
        db.session.query(AiModel).filter_by(slug=SYSTEM_IMAGE_MODEL_SLUG).one_or_none()
    )
    if model is None:
        model = AiModel(
            slug=SYSTEM_IMAGE_MODEL_SLUG,
            display_name="تولید تصویر",
            capability=CAP_IMAGE,
            provider_key="image",
            provider_type="hardcoded",
            provider_model_name="google/nano-banana-2",
            is_active=True,
            pricing_type="image",
            description="مدل سیستمی تولید تصویر (تنظیمات هاردکد؛ فقط تعرفه قابل تغییر است)",
        )
        db.session.add(model)
        db.session.flush()
        legacy = (
            db.session.query(AiModel)
            .filter(AiModel.capability == CAP_IMAGE, AiModel.id != model.id)
            .all()
        )
        for old in legacy:
            moved = 0
            for rule in (
                db.session.query(ModelPricingRule)
                .filter_by(model_id=old.id, is_active=True)
                .all()
            ):
                rule.model_id = model.id
                moved += 1
            old.is_active = False
            log.info("adopted legacy image model %s: moved %d pricing rules", old.id, moved)
        db.session.commit()
    return model


def _job_payload(job: GenerationJob) -> dict:
    """Shape matching the frontend ImageJob contract.

    The critical field is ``result_url``: without it the user panel can
    never display the generated image (it renders "no result" even for
    succeeded jobs). It is a fresh short-lived signed URL minted on each
    poll; polling stops once the job is terminal.
    """
    output_asset = (
        db.session.query(Asset)
        .filter_by(job_id=job.id, kind=ASSET_GENERATED_IMAGE)
        .order_by(Asset.created_at.desc())
        .first()
    )
    params = job.parameters_json or {}
    result_url = None
    if output_asset is not None:
        try:
            result_url = storage.presigned_get_url(output_asset.storage_key)
        except Exception:  # noqa: BLE001 - storage optional/misconfigured
            log.warning("could not mint result_url for image job %s", job.id)
    model = db.session.get(AiModel, job.model_id) if job.model_id else None
    width, height = params.get("width"), params.get("height")
    return {
        "id": job.id,
        "type": job.mode,
        "status": job.status,
        "model_id": job.model_id,
        "model_name": model.display_name if model else None,
        "prompt": job.prompt_text,
        "size": f"{width}x{height}" if width and height else None,
        "quality": params.get("quality"),
        "result_url": result_url,
        "result_width": output_asset.width if output_asset else None,
        "result_height": output_asset.height if output_asset else None,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@bp.get("/image/config")
@login_required
def image_config():
    # The image backend is hardcoded; no model selection is exposed.
    profile = get_active_profile()
    # Flat shape matching the frontend ImageConfig contract. The nested
    # `profile` is kept for richer clients; the flat fields are what the
    # user-facing page reads.
    payload = _profile_payload(profile) or {}
    hard = payload.get("hard_ceilings") or {}
    return success_response({
        "profile": payload or None,
        "sizes": [],
        "qualities": [],
        "max_upload_bytes": payload.get("max_upload_bytes") or hard.get("max_bytes") or 0,
        "max_input_pixels": payload.get("max_input_pixels") or hard.get("max_pixels") or 0,
        "max_input_width": hard.get("max_width") or 0,
        "max_input_height": hard.get("max_height") or 0,
        "allowed_mime_types": payload.get("allowed_mime_types") or [],
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
    body = request.get_json(silent=True) or {}

    def _val(*names):
        """First non-empty value across form fields and JSON body."""
        for n in names:
            v = form.get(n)
            if v in (None, ""):
                v = body.get(n)
            if v not in (None, ""):
                return v
        return None

    prompt = (_val("prompt") or "").strip()
    # Frontend sends `type`; accept `mode` as an alias.
    mode = _val("mode", "type") or MODE_TEXT_TO_IMAGE
    if not prompt or mode not in (MODE_TEXT_TO_IMAGE, MODE_IMAGE_TO_IMAGE):
        return validation_error()

    # Model-driven image backend: explicit model_id wins, else the active
    # image model matching the mode (edit model for image_to_image,
    # generation model otherwise). The legacy system row ("hardcoded")
    # is never selected for new jobs.
    model = _resolve_image_model(_val("model_id"), mode)
    if model is None:
        return error_response("MODEL_UNAVAILABLE", "مدل فعال تولید تصویر یافت نشد.", 404)
    profile = get_active_profile(model.id)
    if profile is None:
        return error_response("MODEL_UNAVAILABLE", "پروفایل پردازش تصویر تنظیم نشده است.", 500)
    profile_snapshot = profile.snapshot()

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    width = _as_int(_val("width"), profile.target_width)
    height = _as_int(_val("height"), profile.target_height)
    # Optional "WIDTHxHEIGHT" size string (frontend size select).
    size = _val("size")
    if size and isinstance(size, str) and "x" in size.lower():
        try:
            sw, sh = size.lower().split("x", 1)
            width = _as_int(sw.strip(), width)
            height = _as_int(sh.strip(), height)
        except (TypeError, ValueError):
            pass

    original_asset = processed_asset = None
    input_mp = Decimal(0)
    # Frontend uploads the file field as `image`; accept `file` too.
    upload = request.files.get("image") or request.files.get("file")

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
            "model_id": model.id,
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
