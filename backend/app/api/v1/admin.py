"""Admin panel API. Every endpoint requires an admin session and writes an
audit log entry."""
from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError
from sqlalchemy import func

from app.ai.image_pipeline import HardCeilings, ImageValidationError, validate_and_process
from app.ai.tokens import TokenizerUnavailable, validate_encoding
from app.api.deps import (
    admin_required,
    client_ip,
    error_response,
    ip_hash,
    paginate_query,
    pagination_params,
    success_response,
    utcnow,
    validation_error,
)
from app.services.plans import (
    SUB_ACTIVE,
    plan_to_public_dict,
)
from app.auth.otp import mask_mobile, normalize_mobile
from app.billing.ledger import DuplicateIdempotencyKey, admin_adjust, get_wallet_for_update
from app.billing.pricing import PricingService
from app.config import config
from app.extensions import db
from app.models import (
    AdminUser,
    AiModel,
    Asset,
    AuditLog,
    GalleryEntry,
    GenerationJob,
    ImageProcessingProfile,
    Message,
    ModelPricingRule,
    Payment,
    Plan,
    UserPlanSubscription,
    UsageEvent,
    User,
    WalletAccount,
    WalletTransaction,
    new_uuid,
)
from app.models.catalog import CAPABILITIES
from app.models.gallery import GALLERY_APPROVED, GALLERY_PENDING, GALLERY_REJECTED
from app.models.jobs import ASSET_CHAT_INPUT_IMAGE, ASSET_GENERATED_IMAGE, ASSET_KINDS
from app.services import users as user_service
from app.services.audit import audit
from app.services.storage import storage

log = logging.getLogger(__name__)

bp = Blueprint("admin", __name__)


def _audit(action: str, target_type: str | None = None, target_id: str | None = None,
           metadata: dict | None = None) -> None:
    audit(
        db.session, actor_type="admin", actor_id=g.current_admin_id, action=action,
        target_type=target_type, target_id=target_id, metadata=metadata,
        ip_hash=ip_hash(client_ip()),
    )


def _parse(schema_cls, payload: dict):
    try:
        return schema_cls(**payload), None
    except ValidationError:
        return None, validation_error()


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@bp.get("/admin/dashboard")
@admin_required
def dashboard():
    total_users = db.session.query(func.count(User.id)).scalar()
    active_users = db.session.query(func.count(User.id)).filter_by(is_active=True).scalar()
    paid_sum = (
        db.session.query(func.coalesce(func.sum(Payment.amount_irr), 0))
        .filter_by(status="paid").scalar()
    )
    charged_sum = (
        db.session.query(func.coalesce(func.sum(UsageEvent.charged_amount_irr), 0)).scalar()
    )
    jobs_by_status = {
        status: count
        for status, count in db.session.query(
            GenerationJob.status, func.count(GenerationJob.id)
        ).group_by(GenerationJob.status).all()
    }
    pending_gallery = (
        db.session.query(func.count(GalleryEntry.id))
        .filter_by(status=GALLERY_PENDING).scalar()
    )
    return success_response({
        "total_users": total_users,
        "active_users": active_users,
        "total_paid_irr": int(paid_sum or 0),
        "total_charged_irr": int(charged_sum or 0),
        "jobs_by_status": jobs_by_status,
        "pending_gallery": pending_gallery,
    })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@bp.get("/admin/users")
@admin_required
def list_users():
    search = (request.args.get("search") or "").strip()
    query = db.session.query(User)
    if search:
        try:
            normalized = normalize_mobile(search)
            query = query.filter(User.mobile_normalized == normalized)
        except ValueError:
            # Fall back to prefix search on the raw digits.
            digits = "".join(c for c in search if c.isdigit())
            if digits:
                query = query.filter(User.mobile_normalized.startswith(digits))
            else:
                query = query.filter(User.id == search)
    is_active = request.args.get("is_active")
    if is_active in ("true", "false"):
        query = query.filter_by(is_active=is_active == "true")
    query = query.order_by(User.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([user_service.user_summary(db.session, u) for u in items], meta)


@bp.get("/admin/users/<user_id>")
@admin_required
def get_user(user_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    return success_response(user_service.user_summary(db.session, user))


@bp.get("/admin/users/<user_id>/activity")
@admin_required
def user_activity(user_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    limit = min(int(request.args.get("limit", 100) or 100), 200)
    return success_response(user_service.activity_timeline(db.session, user_id, limit=limit))


@bp.get("/admin/users/<user_id>/assets")
@admin_required
def user_assets(user_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    kind = request.args.get("kind")
    query = db.session.query(Asset).filter_by(user_id=user_id)
    if kind:
        if kind not in ASSET_KINDS:
            return validation_error()
        query = query.filter_by(kind=kind)
    query = query.order_by(Asset.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_asset_payload(a, include_url=True) for a in items], meta)


class UserStatusSchema(BaseModel):
    is_active: bool
    reason: str


@bp.patch("/admin/users/<user_id>/status")
@admin_required
def set_user_status(user_id: str):
    data, err = _parse(UserStatusSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if not data.reason.strip():
        return validation_error()
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    user_service.set_user_active(
        db.session, user=user, active=data.is_active, reason=data.reason.strip(),
        admin_id=g.current_admin_id, ip_hash=ip_hash(client_ip()),
    )
    db.session.commit()
    return success_response(user_service.user_summary(db.session, user))


class WalletAdjustmentSchema(BaseModel):
    amount_irr: int
    reason: str


@bp.post("/admin/users/<user_id>/wallet-adjustments")
@admin_required
def wallet_adjustment(user_id: str):
    data, err = _parse(WalletAdjustmentSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if not data.reason.strip():
        return validation_error()
    if data.amount_irr == 0 or abs(data.amount_irr) > 1_000_000_000:
        return validation_error()
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    wallet = get_wallet_for_update(db.session, user_id)
    try:
        tx = admin_adjust(
            db.session, wallet=wallet, amount_irr=data.amount_irr,
            idempotency_key=request.headers.get("Idempotency-Key") or f"adminadj-{new_uuid()}",
            admin_id=g.current_admin_id, description=data.reason.strip(),
        )
    except DuplicateIdempotencyKey:
        db.session.rollback()
        return error_response("CONFLICT", "این تراکنش قبلاً ثبت شده است.", 409)
    _audit("wallet.adjusted", "user", user_id,
           {"amount_irr": data.amount_irr, "reason": data.reason.strip()})
    db.session.commit()
    return success_response({
        "id": tx.id, "type": tx.type, "amount_irr": tx.amount_irr,
        "balance_after_irr": tx.balance_after_irr,
    }, status=201)


@bp.get("/admin/users/<user_id>/wallet-transactions")
@admin_required
def user_wallet_transactions(user_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    wallet = db.session.query(WalletAccount).filter_by(user_id=user_id).one_or_none()
    if wallet is None:
        return success_response([], {"page": 1, "page_size": 20, "total": 0, "pages": 0})
    page, page_size = pagination_params()
    query = (
        db.session.query(WalletTransaction)
        .filter_by(wallet_id=wallet.id)
        .order_by(WalletTransaction.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return success_response([_tx_payload(t) for t in items], meta)


def _tx_payload(tx: WalletTransaction) -> dict:
    return {
        "id": tx.id, "type": tx.type, "amount_irr": tx.amount_irr,
        "balance_after_irr": tx.balance_after_irr,
        "reference_type": tx.reference_type, "reference_id": tx.reference_id,
        "description": tx.description,
        "created_by_admin_id": tx.created_by_admin_id,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
    }


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@bp.get("/admin/payments")
@admin_required
def list_payments():
    query = db.session.query(Payment)
    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)
    user_id = request.args.get("user_id")
    if user_id:
        query = query.filter_by(user_id=user_id)
    query = query.order_by(Payment.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_payment_payload(p) for p in items], meta)


@bp.get("/admin/payments/<payment_id>")
@admin_required
def get_payment(payment_id: str):
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return error_response("NOT_FOUND", status=404)
    payload = _payment_payload(payment)
    payload["failure_code"] = payment.failure_code
    payload["failure_message"] = payment.failure_message
    payload["gateway_reference"] = payment.gateway_reference
    return success_response(payload)


def _payment_payload(payment: Payment) -> dict:
    user = db.session.get(User, payment.user_id)
    return {
        "id": payment.id,
        "user_id": payment.user_id,
        "user_mobile_masked": mask_mobile(user.mobile_normalized) if user else None,
        "gateway": payment.gateway,
        "amount_irr": payment.amount_irr,
        "status": payment.status,
        "track_id": payment.track_id,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
    }


# ---------------------------------------------------------------------------
# Usage & jobs
# ---------------------------------------------------------------------------
@bp.get("/admin/usage")
@admin_required
def list_usage():
    query = db.session.query(UsageEvent)
    for key, column in (("user_id", UsageEvent.user_id), ("model_id", UsageEvent.model_id),
                        ("status", UsageEvent.status)):
        value = request.args.get(key)
        if value:
            query = query.filter(column == value)
    date_from, date_to = _parse_date(request.args.get("from")), _parse_date(request.args.get("to"))
    if date_from:
        query = query.filter(UsageEvent.created_at >= date_from)
    if date_to:
        query = query.filter(UsageEvent.created_at <= date_to)
    query = query.order_by(UsageEvent.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_usage_payload(e) for e in items], meta)


def _usage_payload(event: UsageEvent) -> dict:
    return {
        "id": event.id, "user_id": event.user_id, "job_id": event.job_id,
        "model_id": event.model_id, "provider_key": event.provider_key,
        "provider_request_id": event.provider_request_id, "status": event.status,
        "est_input_tokens": event.est_input_tokens,
        "final_input_tokens": event.final_input_tokens,
        "est_output_tokens": event.est_output_tokens,
        "final_output_tokens": event.final_output_tokens,
        "audio_seconds": event.audio_seconds, "image_count": event.image_count,
        "input_pixels": event.input_pixels, "output_pixels": event.output_pixels,
        "tokenizer_encoding": event.tokenizer_encoding,
        "token_count_source": event.token_count_source,
        "pricing_snapshot": event.pricing_snapshot_json,
        "estimated_amount_irr": event.estimated_amount_irr,
        "reserved_amount_irr": event.reserved_amount_irr,
        "charged_amount_irr": event.charged_amount_irr,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


@bp.get("/admin/jobs")
@admin_required
def list_jobs():
    query = db.session.query(GenerationJob)
    for key, column in (("status", GenerationJob.status),
                        ("capability", GenerationJob.capability),
                        ("user_id", GenerationJob.user_id)):
        value = request.args.get(key)
        if value:
            query = query.filter(column == value)
    query = query.order_by(GenerationJob.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_job_payload(j) for j in items], meta)


@bp.get("/admin/jobs/<job_id>")
@admin_required
def get_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None:
        return error_response("NOT_FOUND", status=404)
    payload = _job_payload(job)
    payload["usage_events"] = [
        _usage_payload(e)
        for e in db.session.query(UsageEvent).filter_by(job_id=job.id)
        .order_by(UsageEvent.created_at).all()
    ]
    payload["assets"] = [
        _asset_payload(a, include_url=True)
        for a in db.session.query(Asset).filter_by(job_id=job.id)
        .order_by(Asset.created_at).all()
    ]
    return success_response(payload)


def _job_payload(job: GenerationJob) -> dict:
    user = db.session.get(User, job.user_id)
    return {
        "id": job.id, "user_id": job.user_id,
        "user_mobile_masked": mask_mobile(user.mobile_normalized) if user else None,
        "capability": job.capability, "model_id": job.model_id, "status": job.status,
        "mode": job.mode,
        "prompt_text": job.prompt_text,
        "parameters": job.parameters_json,
        "provider_request_id": job.provider_request_id,
        "result_text": job.result_text,
        "error_code": job.error_code, "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
@bp.get("/admin/assets")
@admin_required
def list_assets():
    query = db.session.query(Asset)
    user_id = request.args.get("user_id")
    if user_id:
        query = query.filter_by(user_id=user_id)
    kind = request.args.get("kind")
    if kind:
        if kind not in ASSET_KINDS:
            return validation_error()
        query = query.filter_by(kind=kind)
    query = query.order_by(Asset.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_asset_payload(a, include_url=True) for a in items], meta)


def _asset_payload(asset: Asset, include_url: bool = False) -> dict:
    payload = {
        "id": asset.id, "user_id": asset.user_id, "job_id": asset.job_id,
        "kind": asset.kind, "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes, "width": asset.width, "height": asset.height,
        "duration_seconds": asset.duration_seconds,
        "derived_from_asset_id": asset.derived_from_asset_id,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }
    if include_url:
        try:
            payload["download_url"] = storage.presigned_get_url(asset.storage_key)
        except Exception:  # noqa: BLE001
            payload["download_url"] = None
    return payload


# ---------------------------------------------------------------------------
# Gallery moderation
# ---------------------------------------------------------------------------
@bp.get("/admin/gallery")
@admin_required
def list_gallery():
    status = request.args.get("status", GALLERY_PENDING)
    if status not in (GALLERY_PENDING, GALLERY_APPROVED, GALLERY_REJECTED):
        return validation_error()
    query = (
        db.session.query(GalleryEntry)
        .filter_by(status=status)
        .order_by(GalleryEntry.reviewed_at.desc(), GalleryEntry.created_at.desc())
    )
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    results = []
    for entry in items:
        asset = db.session.get(Asset, entry.asset_id)
        user = db.session.get(User, entry.user_id)
        item = {
            "id": entry.id,
            "asset_id": entry.asset_id,
            "status": entry.status,
            "user_mobile_masked": mask_mobile(user.mobile_normalized) if user else None,
            "reviewed_by_admin_id": entry.reviewed_by_admin_id,
            "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
            "rejection_reason": entry.rejection_reason,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        if asset is not None:
            item.update({
                "width": asset.width, "height": asset.height,
                "mime_type": asset.mime_type, "size_bytes": asset.size_bytes,
            })
            try:
                item["preview_url"] = storage.presigned_get_url(asset.storage_key)
            except Exception:  # noqa: BLE001
                item["preview_url"] = None
        results.append(item)
    return success_response(results, meta)


def _gallery_entry_for_asset(asset_id: str) -> tuple[Asset | None, GalleryEntry | None]:
    asset = db.session.get(Asset, asset_id)
    if asset is None or asset.kind != ASSET_GENERATED_IMAGE:
        return None, None
    entry = db.session.query(GalleryEntry).filter_by(asset_id=asset_id).one_or_none()
    return asset, entry


@bp.post("/admin/gallery/<asset_id>/approve")
@admin_required
def approve_gallery(asset_id: str):
    asset, entry = _gallery_entry_for_asset(asset_id)
    if asset is None:
        return error_response("NOT_FOUND", "فقط تصاویر تولیدشده می‌توانند وارد گالری شوند.", 404)
    now = utcnow()
    if entry is None:
        entry = GalleryEntry(asset_id=asset.id, user_id=asset.user_id)
        db.session.add(entry)
    entry.status = GALLERY_APPROVED
    entry.reviewed_by_admin_id = g.current_admin_id
    entry.reviewed_at = now
    entry.rejection_reason = None
    _audit("gallery.approved", "gallery_entry", entry.id, {"asset_id": asset.id})
    db.session.commit()
    return success_response({"id": entry.id, "status": entry.status})


class GalleryRejectSchema(BaseModel):
    reason: str | None = None


@bp.post("/admin/gallery/<asset_id>/reject")
@admin_required
def reject_gallery(asset_id: str):
    data, err = _parse(GalleryRejectSchema, request.get_json(silent=True) or {})
    if err:
        return err
    asset, entry = _gallery_entry_for_asset(asset_id)
    if asset is None:
        return error_response("NOT_FOUND", status=404)
    now = utcnow()
    if entry is None:
        entry = GalleryEntry(asset_id=asset.id, user_id=asset.user_id)
        db.session.add(entry)
    entry.status = GALLERY_REJECTED
    entry.reviewed_by_admin_id = g.current_admin_id
    entry.reviewed_at = now
    entry.rejection_reason = (data.reason or "").strip()[:1000] or None
    _audit("gallery.rejected", "gallery_entry", entry.id,
           {"asset_id": asset.id, "reason": entry.rejection_reason})
    db.session.commit()
    return success_response({"id": entry.id, "status": entry.status})


@bp.delete("/admin/gallery/<asset_id>")
@admin_required
def remove_gallery(asset_id: str):
    """Remove from the public gallery only; the user's private asset stays."""
    entry = db.session.query(GalleryEntry).filter_by(asset_id=asset_id).one_or_none()
    if entry is None:
        return error_response("NOT_FOUND", status=404)
    db.session.delete(entry)
    _audit("gallery.removed", "gallery_entry", entry.id, {"asset_id": asset_id})
    db.session.commit()
    return success_response({"removed": True})


# ---------------------------------------------------------------------------
# AI models
# ---------------------------------------------------------------------------
class ModelCreateSchema(BaseModel):
    slug: str
    display_name: str
    capability: str
    provider_key: str
    provider_model_name: str
    is_active: bool = True
    pricing_type: str = "token"
    tokenizer_encoding: str | None = None
    config_json: dict | None = None
    description: str | None = None


class ModelUpdateSchema(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    pricing_type: str | None = None
    provider_model_name: str | None = None
    tokenizer_encoding: str | None = None
    config_json: dict | None = None
    description: str | None = None


def _model_payload(model: AiModel) -> dict:
    return {
        "id": model.id, "slug": model.slug, "display_name": model.display_name,
        "capability": model.capability, "provider_key": model.provider_key,
        "provider_model_name": model.provider_model_name, "is_active": model.is_active,
        "pricing_type": model.pricing_type, "tokenizer_encoding": model.tokenizer_encoding,
        "config_json": model.config_json, "description": model.description,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


@bp.get("/admin/models")
@admin_required
def list_models_admin():
    capability = request.args.get("capability")
    query = db.session.query(AiModel)
    if capability:
        query = query.filter_by(capability=capability)
    query = query.order_by(AiModel.capability, AiModel.display_name)
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_model_payload(m) for m in items], meta)


@bp.post("/admin/models")
@admin_required
def create_model():
    data, err = _parse(ModelCreateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if data.capability not in CAPABILITIES:
        return validation_error()
    if db.session.query(AiModel).filter_by(slug=data.slug.strip()).one_or_none():
        return error_response("CONFLICT", "این slug قبلاً ثبت شده است.", 409)
    encoding = None
    if data.tokenizer_encoding:
        try:
            encoding = validate_encoding(data.tokenizer_encoding)
        except TokenizerUnavailable:
            return error_response("TOKENIZER_UNAVAILABLE", status=422)
    if data.capability == "text" and not encoding:
        return error_response("TOKENIZER_UNAVAILABLE", "برای مدل متنی encoding الزامی است.", 422)
    model = AiModel(
        slug=data.slug.strip(), display_name=data.display_name.strip(),
        capability=data.capability, provider_key=data.provider_key.strip(),
        provider_model_name=data.provider_model_name.strip(),
        is_active=data.is_active, pricing_type=data.pricing_type,
        tokenizer_encoding=encoding, config_json=data.config_json,
        description=data.description,
    )
    db.session.add(model)
    _audit("model.created", "ai_model", model.id, {"slug": model.slug})
    db.session.commit()
    return success_response(_model_payload(model), status=201)


@bp.patch("/admin/models/<model_id>")
@admin_required
def update_model(model_id: str):
    data, err = _parse(ModelUpdateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    model = db.session.get(AiModel, model_id)
    if model is None:
        return error_response("NOT_FOUND", status=404)
    changes: dict = {}
    if data.display_name is not None:
        model.display_name = data.display_name.strip(); changes["display_name"] = model.display_name
    if data.is_active is not None:
        model.is_active = data.is_active; changes["is_active"] = data.is_active
    if data.pricing_type is not None:
        model.pricing_type = data.pricing_type; changes["pricing_type"] = data.pricing_type
    if data.provider_model_name is not None:
        model.provider_model_name = data.provider_model_name.strip()
        changes["provider_model_name"] = model.provider_model_name
    if data.tokenizer_encoding is not None:
        try:
            model.tokenizer_encoding = validate_encoding(data.tokenizer_encoding)
        except TokenizerUnavailable:
            return error_response("TOKENIZER_UNAVAILABLE", status=422)
        changes["tokenizer_encoding"] = model.tokenizer_encoding
    if data.config_json is not None:
        model.config_json = data.config_json; changes["config_json"] = True
    if data.description is not None:
        model.description = data.description; changes["description"] = True
    _audit("model.updated", "ai_model", model.id, changes)
    db.session.commit()
    return success_response(_model_payload(model))


# ---------------------------------------------------------------------------
# Image processing profiles
# ---------------------------------------------------------------------------
class ImageProfileUpdateSchema(BaseModel):
    name: str | None = None
    max_upload_bytes: int | None = None
    max_input_pixels: int | None = None
    allowed_mime_types: list[str] | None = None
    target_width: int | None = None
    target_height: int | None = None
    resize_mode: str | None = None
    allow_upscale: bool | None = None
    output_format: str | None = None
    output_quality: int | None = None
    strip_metadata: bool | None = None
    is_active: bool | None = None


def _profile_payload(profile: ImageProcessingProfile) -> dict:
    return {
        "id": profile.id, "name": profile.name, "model_id": profile.model_id,
        "max_upload_bytes": profile.max_upload_bytes,
        "max_input_pixels": profile.max_input_pixels,
        "allowed_mime_types": profile.allowed_mime_types_json,
        "target_width": profile.target_width, "target_height": profile.target_height,
        "resize_mode": profile.resize_mode, "allow_upscale": profile.allow_upscale,
        "output_format": profile.output_format, "output_quality": profile.output_quality,
        "strip_metadata": profile.strip_metadata, "is_active": profile.is_active,
        "version": profile.version,
        "updated_by_admin_id": profile.updated_by_admin_id,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@bp.get("/admin/settings/image-processing")
@admin_required
def list_image_profiles():
    profiles = (
        db.session.query(ImageProcessingProfile)
        .order_by(ImageProcessingProfile.model_id.nullsfirst(),
                   ImageProcessingProfile.version.desc())
        .all()
    )
    return success_response([_profile_payload(p) for p in profiles])


@bp.put("/admin/settings/image-processing/<profile_id>")
@admin_required
def update_image_profile(profile_id: str):
    data, err = _parse(ImageProfileUpdateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    profile = db.session.get(ImageProcessingProfile, profile_id)
    if profile is None:
        return error_response("NOT_FOUND", status=404)
    hard = HardCeilings()
    changes: dict = {}

    def _set(attr: str, value, change_key: str | None = None):
        if value is not None:
            setattr(profile, attr, value)
            changes[change_key or attr] = value

    _set("name", data.name.strip() if data.name else None)
    _set("max_upload_bytes", data.max_upload_bytes)
    _set("max_input_pixels", data.max_input_pixels)
    _set("allowed_mime_types_json", data.allowed_mime_types, "allowed_mime_types")
    _set("target_width", data.target_width)
    _set("target_height", data.target_height)
    _set("resize_mode", data.resize_mode)
    _set("allow_upscale", data.allow_upscale)
    _set("output_format", data.output_format)
    _set("output_quality", data.output_quality)
    _set("strip_metadata", data.strip_metadata)
    _set("is_active", data.is_active)

    # Admin values may never exceed the hard security ceilings.
    if profile.max_upload_bytes > hard.max_bytes:
        return error_response("VALIDATION_ERROR", "سقف حجم از حد امنیتی بیشتر است.", 422)
    if profile.max_input_pixels > hard.max_pixels:
        return error_response("VALIDATION_ERROR", "سقف پیکسل از حد امنیتی بیشتر است.", 422)
    if profile.target_width > hard.max_width or profile.target_height > hard.max_height:
        return error_response("VALIDATION_ERROR", "ابعاد مقصد از حد امنیتی بیشتر است.", 422)
    if profile.resize_mode not in ("fit", "fill", "stretch"):
        return error_response("VALIDATION_ERROR", "resize_mode نامعتبر است.", 422)
    if profile.output_format not in ("jpeg", "png", "webp"):
        return error_response("VALIDATION_ERROR", "output_format نامعتبر است.", 422)
    if not 1 <= profile.output_quality <= 100:
        return error_response("VALIDATION_ERROR", "output_quality باید بین ۱ تا ۱۰۰ باشد.", 422)

    profile.version = (profile.version or 0) + 1
    profile.updated_by_admin_id = g.current_admin_id
    _audit("image_profile.updated", "image_processing_profile", profile.id, changes)
    db.session.commit()
    return success_response(_profile_payload(profile))


@bp.post("/admin/settings/image-processing/preview")
@admin_required
def preview_image_profile():
    """Preview a resize with proposed (unsaved) settings. Nothing is stored
    publicly; the test file never leaves this request."""
    upload = request.files.get("file")
    if upload is None:
        return validation_error()
    raw = upload.read()
    if not raw:
        return validation_error()

    profile = db.session.get(ImageProcessingProfile, request.form.get("profile_id") or "")
    base = profile.snapshot() if profile else {}
    overrides = {}
    for key, caster in (
        ("target_width", int), ("target_height", int), ("output_quality", int),
        ("max_upload_bytes", int), ("max_input_pixels", int),
    ):
        value = request.form.get(key)
        if value:
            try:
                overrides[key] = caster(value)
            except ValueError:
                return validation_error()
    for key in ("resize_mode", "output_format"):
        if request.form.get(key):
            overrides[key] = request.form.get(key)
    if request.form.get("allow_upscale") in ("true", "false"):
        overrides["allow_upscale"] = request.form.get("allow_upscale") == "true"
    if request.form.get("strip_metadata") in ("true", "false"):
        overrides["strip_metadata"] = request.form.get("strip_metadata") == "true"

    trial = {**base, **overrides}
    try:
        processed = validate_and_process(raw, trial, HardCeilings())
    except ImageValidationError as exc:
        return error_response(exc.code, status=422)
    return success_response({
        "before": {"width": processed.metadata["before_width"],
                   "height": processed.metadata["before_height"],
                   "size_bytes": len(raw)},
        "after": {"width": processed.width, "height": processed.height,
                  "size_bytes": processed.size_bytes, "mime_type": processed.mime_type},
        "resize_mode": processed.metadata["resize_mode"],
        "encoder": processed.metadata["encoder"],
    })


# ---------------------------------------------------------------------------
# Pricing rules (versioned)
# ---------------------------------------------------------------------------
class PricingRuleCreateSchema(BaseModel):
    model_id: str
    billing_unit: str
    unit_size: int = 1
    unit_price_irr: int
    dimension_key: str | None = None
    quality_key: str | None = None
    minimum_charge_irr: int | None = None
    maximum_charge_irr: int | None = None
    rounding_mode: str = "up"
    effective_from: str | None = None
    effective_to: str | None = None


class PricingRuleUpdateSchema(BaseModel):
    is_active: bool | None = None
    minimum_charge_irr: int | None = None
    maximum_charge_irr: int | None = None
    effective_from: str | None = None
    effective_to: str | None = None


def _rule_payload(rule: ModelPricingRule) -> dict:
    return {
        "id": rule.id, "model_id": rule.model_id, "version": rule.version,
        "billing_unit": rule.billing_unit, "unit_size": rule.unit_size,
        "unit_price_irr": rule.unit_price_irr,
        "dimension_key": rule.dimension_key, "quality_key": rule.quality_key,
        "minimum_charge_irr": rule.minimum_charge_irr,
        "maximum_charge_irr": rule.maximum_charge_irr,
        "rounding_mode": rule.rounding_mode,
        "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
        "is_active": rule.is_active,
        "created_by_admin_id": rule.created_by_admin_id,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


@bp.get("/admin/pricing-rules")
@admin_required
def list_pricing_rules():
    query = db.session.query(ModelPricingRule)
    model_id = request.args.get("model_id")
    if model_id:
        query = query.filter_by(model_id=model_id)
    billing_unit = request.args.get("billing_unit")
    if billing_unit:
        query = query.filter_by(billing_unit=billing_unit)
    query = query.order_by(ModelPricingRule.model_id, ModelPricingRule.version.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_rule_payload(r) for r in items], meta)


@bp.post("/admin/pricing-rules")
@admin_required
def create_pricing_rule():
    data, err = _parse(PricingRuleCreateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    model = db.session.get(AiModel, data.model_id)
    if model is None:
        return error_response("NOT_FOUND", "مدل یافت نشد.", 404)
    if data.unit_size <= 0 or data.unit_price_irr < 0:
        return validation_error()
    if data.rounding_mode not in ("up", "down", "nearest"):
        return validation_error()
    max_version = (
        db.session.query(func.coalesce(func.max(ModelPricingRule.version), 0))
        .filter_by(model_id=data.model_id, billing_unit=data.billing_unit,
                   dimension_key=data.dimension_key, quality_key=data.quality_key)
        .scalar()
    )
    rule = ModelPricingRule(
        model_id=data.model_id, version=int(max_version or 0) + 1,
        billing_unit=data.billing_unit, unit_size=data.unit_size,
        unit_price_irr=data.unit_price_irr,
        dimension_key=data.dimension_key, quality_key=data.quality_key,
        minimum_charge_irr=data.minimum_charge_irr,
        maximum_charge_irr=data.maximum_charge_irr,
        rounding_mode=data.rounding_mode,
        effective_from=_parse_date(data.effective_from),
        effective_to=_parse_date(data.effective_to),
        is_active=True, created_by_admin_id=g.current_admin_id,
    )
    db.session.add(rule)
    _audit("pricing_rule.created", "model_pricing_rule", rule.id,
           {"model_id": data.model_id, "billing_unit": data.billing_unit,
            "version": rule.version, "unit_price_irr": data.unit_price_irr})
    db.session.commit()
    return success_response(_rule_payload(rule), status=201)


@bp.patch("/admin/pricing-rules/<rule_id>")
@admin_required
def update_pricing_rule(rule_id: str):
    data, err = _parse(PricingRuleUpdateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    rule = db.session.get(ModelPricingRule, rule_id)
    if rule is None:
        return error_response("NOT_FOUND", status=404)
    changes: dict = {}
    if data.is_active is not None:
        rule.is_active = data.is_active; changes["is_active"] = data.is_active
    if data.minimum_charge_irr is not None:
        rule.minimum_charge_irr = data.minimum_charge_irr
        changes["minimum_charge_irr"] = data.minimum_charge_irr
    if data.maximum_charge_irr is not None:
        rule.maximum_charge_irr = data.maximum_charge_irr
        changes["maximum_charge_irr"] = data.maximum_charge_irr
    if data.effective_from is not None:
        rule.effective_from = _parse_date(data.effective_from)
        changes["effective_from"] = data.effective_from
    if data.effective_to is not None:
        rule.effective_to = _parse_date(data.effective_to)
        changes["effective_to"] = data.effective_to
    # Price changes go through POST (new version); PATCH never rewrites history.
    _audit("pricing_rule.updated", "model_pricing_rule", rule.id, changes)
    db.session.commit()
    return success_response(_rule_payload(rule))


class PricingEstimateSchema(BaseModel):
    kind: str  # text | audio | image
    model_id: str
    input_tokens: int = 0
    max_output_tokens: int = 0
    audio_seconds: int = 0
    image_count: int = 1
    input_megapixels: float = 0
    output_megapixels: float = 0
    dimension_key: str | None = None
    quality_key: str | None = None


@bp.post("/admin/pricing/estimate")
@admin_required
def pricing_estimate():
    """Test-drive the pricing calculation with sample inputs."""
    data, err = _parse(PricingEstimateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    model = db.session.get(AiModel, data.model_id)
    if model is None:
        return error_response("NOT_FOUND", "مدل یافت نشد.", 404)
    pricing = PricingService(db.session)
    try:
        if data.kind == "text":
            estimate = pricing.estimate_text(data.model_id, data.input_tokens,
                                             data.max_output_tokens)
        elif data.kind == "audio":
            estimate = pricing.estimate_audio(data.model_id, data.audio_seconds)
        elif data.kind == "image":
            from decimal import Decimal

            estimate = pricing.estimate_image(
                data.model_id, image_count=data.image_count,
                input_megapixels=Decimal(str(data.input_megapixels)),
                output_megapixels=Decimal(str(data.output_megapixels)),
                dimension_key=data.dimension_key, quality_key=data.quality_key,
            )
        else:
            return validation_error()
    except Exception as exc:  # noqa: BLE001 - PricingRuleUnavailable etc.
        log.warning("pricing estimate failed: %s", exc)
        return error_response("PRICING_RULE_UNAVAILABLE", status=422)
    _audit("pricing.estimated", "ai_model", data.model_id, {"kind": data.kind})
    db.session.commit()
    return success_response(estimate)


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------
@bp.get("/admin/audit-logs")
@admin_required
def list_audit_logs():
    query = db.session.query(AuditLog)
    actor_type = request.args.get("actor_type")
    if actor_type:
        query = query.filter_by(actor_type=actor_type)
    action = request.args.get("action")
    if action:
        query = query.filter(AuditLog.action.startswith(action))
    query = query.order_by(AuditLog.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response(
        [
            {
                "id": e.id, "actor_type": e.actor_type, "actor_id": e.actor_id,
                "action": e.action, "target_type": e.target_type, "target_id": e.target_id,
                "metadata": e.metadata_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        meta,
    )


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Subscription plans
# ---------------------------------------------------------------------------
class PlanCreateSchema(BaseModel):
    name: str
    description: str | None = None
    price_irr: int
    period_days: int = 30
    features: list[str] = []
    usage_limits: dict | None = None
    bonus_irr: int = 0
    is_free: bool = False
    is_featured: bool = False
    is_active: bool = True
    sort_order: int = 0


class PlanUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None
    price_irr: int | None = None
    period_days: int | None = None
    features: list[str] | None = None
    usage_limits: dict | None = None
    bonus_irr: int | None = None
    is_free: bool | None = None
    is_featured: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


def _plan_payload_admin(plan: Plan) -> dict:
    payload = plan_to_public_dict(plan)
    payload["is_active"] = plan.is_active
    payload["created_at"] = plan.created_at.isoformat() if plan.created_at else None
    return payload


def _validate_plan_numbers(price_irr, bonus_irr, period_days):
    if price_irr is not None and (price_irr < 0 or price_irr > 1_000_000_000):
        return error_response("VALIDATION_ERROR", "مبلغ پلن نامعتبر است.", 422)
    if bonus_irr is not None and (bonus_irr < 0 or bonus_irr > 1_000_000_000):
        return error_response("VALIDATION_ERROR", "مبلغ تشویقی نامعتبر است.", 422)
    if period_days is not None and (period_days < 1 or period_days > 3650):
        return error_response("VALIDATION_ERROR", "مدت دوره پلن نامعتبر است.", 422)
    return None


def _validate_usage_limits(usage_limits):
    if usage_limits is None:
        return None
    if not isinstance(usage_limits, dict):
        return error_response("VALIDATION_ERROR", "سقف‌های مصرف باید یک شیء باشند.", 422)
    allowed = {"monthly_text", "monthly_image", "monthly_audio_minutes"}
    for key, value in usage_limits.items():
        if key not in allowed or not isinstance(value, int) or value < 0:
            return error_response("VALIDATION_ERROR", "سقف مصرف نامعتبر است.", 422)
    return None


@bp.get("/admin/plans")
@admin_required
def list_plans_admin():
    plans = (
        db.session.query(Plan)
        .order_by(Plan.sort_order, Plan.created_at)
        .all()
    )
    return success_response([_plan_payload_admin(p) for p in plans])


@bp.post("/admin/plans")
@admin_required
def create_plan():
    data, err = _parse(PlanCreateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if not data.name.strip():
        return validation_error()
    if data.is_free and data.price_irr != 0:
        return error_response("VALIDATION_ERROR", "پلن رایگان باید قیمت صفر داشته باشد.", 422)
    num_err = _validate_plan_numbers(data.price_irr, data.bonus_irr, data.period_days)
    if num_err:
        return num_err
    lim_err = _validate_usage_limits(data.usage_limits)
    if lim_err:
        return lim_err
    plan = Plan(
        name=data.name.strip(),
        description=(data.description or "").strip() or None,
        price_irr=data.price_irr,
        period_days=data.period_days,
        features_json=[str(f) for f in (data.features or [])],
        usage_limits_json=data.usage_limits,
        bonus_irr=data.bonus_irr,
        is_free=data.is_free,
        is_featured=data.is_featured,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )
    db.session.add(plan)
    _audit("plan.created", "plan", plan.id,
           {"name": plan.name, "price_irr": plan.price_irr,
            "bonus_irr": plan.bonus_irr, "is_free": plan.is_free})
    db.session.commit()
    return success_response(_plan_payload_admin(plan), status=201)


@bp.patch("/admin/plans/<plan_id>")
@admin_required
def update_plan(plan_id: str):
    data, err = _parse(PlanUpdateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    plan = db.session.get(Plan, plan_id)
    if plan is None:
        return error_response("NOT_FOUND", status=404)
    num_err = _validate_plan_numbers(data.price_irr, data.bonus_irr, data.period_days)
    if num_err:
        return num_err
    lim_err = _validate_usage_limits(data.usage_limits)
    if lim_err:
        return lim_err
    changes: dict = {}
    if data.name is not None and data.name.strip():
        plan.name = data.name.strip(); changes["name"] = plan.name
    if data.description is not None:
        plan.description = data.description.strip() or None
        changes["description"] = plan.description
    if data.price_irr is not None:
        plan.price_irr = data.price_irr; changes["price_irr"] = data.price_irr
    if data.period_days is not None:
        plan.period_days = data.period_days; changes["period_days"] = data.period_days
    if data.features is not None:
        plan.features_json = [str(f) for f in data.features]; changes["features"] = True
    if data.usage_limits is not None:
        plan.usage_limits_json = data.usage_limits; changes["usage_limits"] = True
    if data.bonus_irr is not None:
        plan.bonus_irr = data.bonus_irr; changes["bonus_irr"] = data.bonus_irr
    if data.is_free is not None:
        plan.is_free = data.is_free; changes["is_free"] = data.is_free
    if data.is_featured is not None:
        plan.is_featured = data.is_featured; changes["is_featured"] = data.is_featured
    if data.is_active is not None:
        plan.is_active = data.is_active; changes["is_active"] = data.is_active
    if data.sort_order is not None:
        plan.sort_order = data.sort_order; changes["sort_order"] = data.sort_order
    # Deactivation replaces deletion for most cases; existing paid
    # payments and subscriptions keep working against a deactivated plan.
    _audit("plan.updated", "plan", plan.id, changes)
    db.session.commit()
    return success_response(_plan_payload_admin(plan))


@bp.delete("/admin/plans/<plan_id>")
@admin_required
def delete_plan(plan_id: str):
    plan = db.session.get(Plan, plan_id)
    if plan is None:
        return error_response("NOT_FOUND", status=404)
    active_subs = (
        db.session.query(UserPlanSubscription)
        .filter_by(plan_id=plan.id, status=SUB_ACTIVE)
        .count()
    )
    if active_subs:
        return error_response(
            "CONFLICT",
            "این پلن اشتراک فعال دارد. ابتدا پلن را غیرفعال کنید.",
            409,
        )
    _audit("plan.deleted", "plan", plan.id,
           {"name": plan.name, "price_irr": plan.price_irr})
    db.session.delete(plan)
    db.session.commit()
    return success_response({"deleted": True})
