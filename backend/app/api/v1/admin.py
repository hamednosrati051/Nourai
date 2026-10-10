"""Admin panel API. Every endpoint requires an admin session and writes an
audit log entry."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError
from sqlalchemy import func

from app.ai.image_pipeline import HardCeilings, ImageValidationError, validate_and_process
from app.api.deps import (
    admin_required,
    client_ip,
    error_response,
    ip_hash,
    paginate_query,
    paginated_response,
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
from app.billing.pricing import PricingService, format_usd
from app.config import config
from app.extensions import db
from app.models import (
    AdminUser,
    AiModel,
    Asset,
    AuditLog,
    BalePublishQueue,
    BlogPost,
    Conversation,
    CurrencySettings,
    SiteSettings,
    GalleryEntry,
    GenerationJob,
    ModerationSettings,
    ImageProcessingProfile,
    Message,
    ModelPricingRule,
    Payment,
    Plan,
    PromptBlocklist,
    UserPlanSubscription,
    UsageEvent,
    User,
    WalletAccount,
    WalletTransaction,
    MessengerUser,
    new_uuid,
)
from app.models.catalog import CAP_IMAGE, CAPABILITIES
from app.models.payment import PAY_PAID
from app.models.gallery import GALLERY_APPROVED, GALLERY_PENDING, GALLERY_REJECTED
from app.models.jobs import ASSET_CHAT_INPUT_IMAGE, ASSET_GENERATED_IMAGE, ASSET_KINDS
from app.services import users as user_service
from app.services.audit import audit
from app.services.storage import storage
from app.tasks import cancel_job
from app.auth.otp import mask_mobile

log = logging.getLogger(__name__)

# Persian/Arabic-Indic digits -> ASCII (for admin search inputs).
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

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
    total_revenue_irr = (
        db.session.query(func.coalesce(func.sum(Payment.amount_irr), 0))
        .filter_by(status=PAY_PAID).scalar()
    )
    today_start = _tehran_day_start_utc()
    revenue_today_irr = (
        db.session.query(func.coalesce(func.sum(Payment.amount_irr), 0))
        .filter(Payment.status == PAY_PAID, Payment.created_at >= today_start)
        .scalar()
    )
    payments_today = (
        db.session.query(func.count(Payment.id))
        .filter(Payment.status == PAY_PAID, Payment.created_at >= today_start)
        .scalar()
    )
    jobs_today = (
        db.session.query(func.count(GenerationJob.id))
        .filter(GenerationJob.created_at >= today_start)
        .scalar()
    )
    active_models = (
        db.session.query(func.count(AiModel.id)).filter_by(is_active=True).scalar()
    )
    pending_gallery_items = (
        db.session.query(func.count(GalleryEntry.id))
        .filter_by(status=GALLERY_PENDING).scalar()
    )
    return success_response({
        "total_users": total_users,
        "active_users": active_users,
        "total_revenue_irr": int(total_revenue_irr or 0),
        "revenue_today_irr": int(revenue_today_irr or 0),
        "payments_today": payments_today,
        "jobs_today": jobs_today,
        "active_models": active_models,
        "pending_gallery_items": pending_gallery_items,
    })


def _tehran_day_start_utc():
    """Naive-UTC datetime of today's 00:00 in Asia/Tehran.

    Timestamps are stored as naive UTC; the dashboard's "today" cards
    follow the admin's local day.
    """
    from zoneinfo import ZoneInfo
    tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
    day_start_tehran = tehran_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start_tehran.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@bp.get("/admin/users")
@admin_required
def list_users():
    from app.models.messenger import MessengerUser
    from sqlalchemy import or_
    search = (request.args.get("search") or "").strip()
    query = db.session.query(User)
    if search:
        # Try mobile first
        try:
            normalized = normalize_mobile(search)
            query = query.filter(User.mobile_normalized == normalized)
        except ValueError:
            digits = "".join(c for c in search if c.isdigit())
            if digits:
                # Could be mobile prefix OR user ID starting with digits
                # Also check Bale username
                username_match = (
                    db.session.query(MessengerUser.user_id)
                    .filter(MessengerUser.platform_username.ilike(f"%{search}%"))
                    .subquery()
                )
                query = query.filter(
                    or_(
                        User.mobile_normalized.startswith(digits),
                        User.id.startswith(search),
                        User.id.in_(username_match),
                    )
                )
            else:
                # Text search: user ID or Bale username
                username_match = (
                    db.session.query(MessengerUser.user_id)
                    .filter(MessengerUser.platform_username.ilike(f"%{search}%"))
                    .subquery()
                )
                query = query.filter(
                    or_(
                        User.id == search,
                        User.id.in_(username_match),
                    )
                )
    is_active = request.args.get("is_active")
    if is_active in ("true", "false"):
        query = query.filter_by(is_active=is_active == "true")
    query = query.order_by(User.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([user_service.user_summary(db.session, u) for u in items], page, page_size, meta["total"])


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
    page, page_size = pagination_params()
    events = user_service.activity_timeline(db.session, user_id, limit=200)
    total = len(events)
    start = (page - 1) * page_size
    items = [_activity_item(e, i) for i, e in enumerate(events[start:start + page_size], start=start)]
    return paginated_response(items, page, page_size, total)


@bp.get("/admin/users/<user_id>/chats/<chat_id>/messages")
@admin_required
def user_chat_messages(user_id: str, chat_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    conv = db.session.get(Conversation, chat_id)
    if conv is None or conv.user_id != user_id:
        return error_response("NOT_FOUND", status=404)
    page, page_size = pagination_params()
    query = (
        db.session.query(Message)
        .filter_by(conversation_id=chat_id)
        .order_by(Message.created_at.asc())
    )
    total = query.count()
    msgs = query.offset((page - 1) * page_size).limit(page_size).all()
    items = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content_text,
            "input_tokens": m.input_tokens,
            "output_tokens": m.output_tokens,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]
    return paginated_response(items, page, page_size, total)


@bp.get("/admin/users/<user_id>/chats")
@admin_required
def user_chats(user_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    page, page_size = pagination_params()
    query = (
        db.session.query(Conversation)
        .filter_by(user_id=user_id)
        .order_by(Conversation.created_at.desc())
    )
    total = query.count()
    convs = query.offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for c in convs:
        msg_count = db.session.query(Message).filter_by(conversation_id=c.id).count()
        first_msg = (
            db.session.query(Message)
            .filter_by(conversation_id=c.id, role="user")
            .order_by(Message.created_at.asc())
            .first()
        )
        model = db.session.get(AiModel, c.model_id) if c.model_id else None
        items.append({
            "id": c.id,
            "title": c.title,
            "model": model.slug if model else None,
            "message_count": msg_count,
            "preview": (first_msg.content_text or "")[:120] if first_msg else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return paginated_response(items, page, page_size, total)


# Maps the raw timeline event kinds to the frontend's ActivityKind labels.
_ACTIVITY_UI_KIND = {
    "payment": "payment",
    "usage": "ai_request",
    "wallet": "wallet",
}


def _activity_item(event: dict, index: int) -> dict:
    """Shape one timeline event as the frontend's ActivityItem."""
    kind = event.get("kind") or ""
    action = event.get("action") or ""
    if kind == "audit":
        if action in ("user.login", "user.logout"):
            ui_kind = "login"
        elif action.startswith("payment"):
            ui_kind = "payment"
        elif action.startswith(("chat.", "image.", "audio.")):
            ui_kind = "ai_request"
        else:
            ui_kind = "admin_action"
    else:
        ui_kind = _ACTIVITY_UI_KIND.get(kind, "admin_action")
    detail = event.get("detail")
    description = None
    if isinstance(detail, dict):
        description = ", ".join(f"{k}={v}" for k, v in detail.items() if v is not None) or None
    return {
        "id": f"{kind}-{index}",
        "kind": ui_kind,
        "title": action,
        "description": description,
        "created_at": event.get("at") or "",
    }


@bp.get("/admin/users/<user_id>/assets")
@admin_required
def user_assets(user_id: str):
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("NOT_FOUND", status=404)
    kind = request.args.get("kind")
    query = db.session.query(Asset).filter_by(user_id=user_id)
    if kind:
        # Comma-separated kinds, e.g. input_image_original,input_image_processed.
        kinds = [k.strip() for k in kind.split(",") if k.strip()]
        if not kinds or any(k not in ASSET_KINDS for k in kinds):
            return validation_error()
        query = query.filter(Asset.kind.in_(kinds))
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
    return paginated_response([_tx_payload(t) for t in items], page, page_size, meta["total"])


def _tx_payload(tx: WalletTransaction) -> dict:
    track_id = None
    if tx.reference_type == "payment" and tx.reference_id:
        payment = db.session.get(Payment, tx.reference_id)
        if payment:
            track_id = payment.track_id
    return {
        "id": tx.id, "type": tx.type, "amount_irr": tx.amount_irr,
        "balance_after_irr": tx.balance_after_irr,
        "reference_type": tx.reference_type, "reference_id": tx.reference_id,
        "description": tx.description, "track_id": track_id,
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
    # Search by user mobile (partial match; accepts Persian digits).
    mobile = request.args.get("mobile")
    if mobile:
        digits = re.sub(r"\D", "", mobile.translate(_FA_DIGITS))
        if digits:
            query = query.join(User, Payment.user_id == User.id).filter(
                User.mobile_normalized.like(f"%{digits}%")
            )
        else:
            query = query.filter(False)
    # Search by bot username or ID (partial match, case-insensitive).
    username = request.args.get("username")
    if username:
        uname = username.strip().lstrip("@")
        if uname:
            query = query.join(
                MessengerUser, Payment.user_id == MessengerUser.user_id
            ).filter(
                db.or_(
                    MessengerUser.platform_username.ilike(f"%{uname}%"),
                    MessengerUser.platform_user_id.like(f"%{uname}%"),
                )
            )
        else:
            query = query.filter(False)
    # Date range filter on creation date (YYYY-MM-DD, inclusive).
    date_from = request.args.get("date_from")
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Payment.created_at >= dt_from)
        except ValueError:
            pass
    date_to = request.args.get("date_to")
    if date_to:
        try:
            # Inclusive end: everything before the next day.
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Payment.created_at < dt_to)
        except ValueError:
            pass
    query = query.order_by(Payment.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([_payment_payload(p) for p in items], page, page_size, meta["total"])


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


@bp.post("/admin/payments/<payment_id>/cancel")
@admin_required
def cancel_payment(payment_id: str):
    """Cancel a pending payment (admin only). Does not affect the payment flow."""
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return error_response("NOT_FOUND", status=404)
    if payment.status not in ("pending", "created"):
        return error_response("INVALID_STATUS", status=400)
    payment.status = "cancelled"
    db.session.commit()
    return success_response(_payment_payload(payment))


def _payment_payload(payment: Payment) -> dict:
    user = db.session.get(User, payment.user_id)
    # Bot user info (Bale/Eitaa) if linked
    bot_info = None
    if user:
        link = db.session.query(MessengerUser).filter_by(user_id=user.id).first()
        if link:
            bot_info = {
                "platform": link.platform,
                "platform_user_id": link.platform_user_id,
                "platform_username": link.platform_username,
            }
    return {
        "id": payment.id,
        "user_id": payment.user_id,
        "user_mobile_masked": mask_mobile(user.mobile_normalized) if user and user.mobile_normalized else None,
        "bot_user": bot_info,
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
    return paginated_response([_usage_payload(e) for e in items], page, page_size, meta["total"])


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
    return paginated_response([_job_payload(j) for j in items], page, page_size, meta["total"])


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
# Support messages
# ---------------------------------------------------------------------------
@bp.get("/admin/support")
@admin_required
def list_support():
    from app.models.messenger import SupportMessage, MessengerUser
    query = db.session.query(SupportMessage).order_by(SupportMessage.created_at.desc())
    unread_only = request.args.get("unread_only") == "true"
    if unread_only:
        query = query.filter_by(is_read=False)
    items = query.limit(100).all()
    total = query.count()
    # Map user_id -> username for display
    user_ids = {m.user_id for m in items if m.user_id}
    username_map = {}
    if user_ids:
        links = db.session.query(MessengerUser).filter(
            MessengerUser.user_id.in_(user_ids)
        ).all()
        username_map = {l.user_id: l.platform_username for l in links}
    return paginated_response([{
        "id": m.id,
        "platform": m.platform,
        "platform_user_id": m.platform_user_id,
        "platform_username": username_map.get(m.user_id),
        "user_id": m.user_id,
        "message": m.message,
        "is_read": m.is_read,
        "admin_reply": m.admin_reply,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in items], 1, 100, total)


@bp.get("/admin/support/unread-count")
@admin_required
def support_unread_count():
    from app.models.messenger import SupportMessage
    count = db.session.query(SupportMessage).filter_by(is_read=False).count()
    return success_response({"unread_count": count})


@bp.post("/admin/support/<msg_id>/read")
@admin_required
def mark_support_read(msg_id: str):
    from app.models.messenger import SupportMessage
    m = db.session.get(SupportMessage, msg_id)
    if not m:
        return error_response("NOT_FOUND", status=404)
    m.is_read = True
    db.session.commit()
    return success_response({"ok": True})


@bp.post("/admin/support/<msg_id>/reply")
@admin_required
def reply_support(msg_id: str):
    from app.models.messenger import SupportMessage
    m = db.session.get(SupportMessage, msg_id)
    if not m:
        return error_response("NOT_FOUND", status=404)
    data = request.get_json(silent=True) or {}
    reply = (data.get("reply") or "").strip()
    if not reply:
        return error_response("EMPTY_REPLY", status=400)
    m.admin_reply = reply[:2000]
    m.is_read = True
    db.session.commit()
    # Send reply back to user via Bale
    try:
        from app.api.v1.bale import send_message
        send_message(
            int(m.platform_user_id),
            f"🛟 پاسخ پشتیبانی:\n\n{reply[:1800]}",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to send support reply via bale: %s", exc)
    return success_response({"ok": True})


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
    return paginated_response([_asset_payload(a, include_url=True) for a in items], page, page_size, meta["total"])


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
        # Stream via backend (same-origin). Presigned URLs point at localhost.
        payload["download_url"] = f"/api/v1/assets/{asset.id}/download?stream=1"
        # The admin UI's AssetItem contract expects `url`.
        payload["url"] = payload["download_url"]
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
            item["image_url"] = f"/api/v1/assets/{asset.id}/download?stream=1"
            # The admin UI renders the prompt (small) under each image.
            job = db.session.get(GenerationJob, asset.job_id) if asset.job_id else None
            prompt = (job.prompt_text or "").strip() if job else ""
            item["prompt_excerpt"] = prompt[:140] if prompt else None
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
    # Queue for Bale channel (requires separate approval)
    _queue_for_bale("gallery", entry.id, None)
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


@bp.post("/admin/gallery/<asset_id>/requeue")
@admin_required
def requeue_gallery(asset_id: str):
    """Move a rejected (or approved) entry back to pending for re-review."""
    asset, entry = _gallery_entry_for_asset(asset_id)
    if asset is None or entry is None:
        return error_response("NOT_FOUND", status=404)
    entry.status = GALLERY_PENDING
    entry.reviewed_by_admin_id = None
    entry.reviewed_at = None
    entry.rejection_reason = None
    _audit("gallery.requeued", "gallery_entry", entry.id, {"asset_id": asset.id})
    db.session.commit()
    return success_response({"id": entry.id, "status": entry.status})


@bp.delete("/admin/gallery/<asset_id>")
@admin_required
def remove_gallery(asset_id: str):
    """Remove from the public gallery only; the user's private asset stays.

    The entry goes back to pending (not deleted) so it stays visible
    in the admin queue for re-approval.
    """
    entry = db.session.query(GalleryEntry).filter_by(asset_id=asset_id).one_or_none()
    if entry is None:
        return error_response("NOT_FOUND", status=404)
    entry.status = GALLERY_PENDING
    entry.reviewed_by_admin_id = None
    entry.reviewed_at = None
    entry.rejection_reason = None
    _audit("gallery.removed", "gallery_entry", entry.id, {"asset_id": asset_id})
    db.session.commit()
    return success_response({"removed": True, "status": entry.status})


# ---------------------------------------------------------------------------
# AI models
# ---------------------------------------------------------------------------
class ModelCreateSchema(BaseModel):
    # slug / provider_key are optional: auto-generated when empty.
    slug: str | None = None
    display_name: str
    capability: str
    provider_key: str | None = None
    provider_model_name: str
    is_active: bool = True
    pricing_type: str = "token"
    # Adapter family; must be a known PROVIDER_TYPES key.
    provider_type: str = "openai_compat"
    tokenizer_encoding: str | None = None
    config_json: dict | None = None
    description: str | None = None
    # Write-only provider credentials (from the admin form). Stored on the
    # model record; never returned by the API. Env vars remain as fallback.
    base_url: str | None = None
    api_key: str | None = None


class ModelUpdateSchema(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    pricing_type: str | None = None
    provider_model_name: str | None = None
    provider_type: str | None = None
    tokenizer_encoding: str | None = None
    config_json: dict | None = None
    description: str | None = None
    # Write-only: non-empty values replace the stored credentials.
    base_url: str | None = None
    api_key: str | None = None


# Reserved config_json key holding form-provided provider credentials.
_PROVIDER_CREDS_KEY = "__provider__"

# Adapter families a model can use. The runtime picks the adapter from the
# model's own provider_type; env vars (AI_TEXT/AUDIO/IMAGE_PROVIDER) remain
# only as fallback. Extend this dict when new families are added.
PROVIDER_TYPES = {
    "openai_compat": "OpenAI Compatible",
    "async_generation": "Async Generation",
    "chat_image_edit_gemini": "Chat Image Edit (Gemini)",
}


def _extract_provider_creds(config_json: dict | None) -> tuple[str, str]:
    """(base_url, api_key) stored on the model via the admin form."""
    creds = (config_json or {}).get(_PROVIDER_CREDS_KEY) or {}
    return (creds.get("base_url") or "", creds.get("api_key") or "")


def _store_provider_creds(config_json: dict | None, base_url: str | None,
                          api_key: str | None) -> dict | None:
    """Merge form-provided credentials into config_json (write path only).

    The reserved ``__provider__`` key can only be written through the
    dedicated ``base_url``/``api_key`` fields, never via raw ``config_json``.
    """
    cfg = dict(config_json or {})
    cfg.pop(_PROVIDER_CREDS_KEY, None)
    bu = (base_url or "").strip()
    ak = (api_key or "").strip()
    if bu or ak:
        if not (bu and ak):
            raise ValueError("آدرس و توکن باید با هم وارد شوند.")
        cfg[_PROVIDER_CREDS_KEY] = {"base_url": bu, "api_key": ak}
    return cfg or None


def _model_payload(model: AiModel) -> dict:
    # Provider credentials are write-only: never expose api_key via the API.
    # base_url is not sensitive, so it is returned for display in edit forms.
    cfg = dict(model.config_json or {})
    creds = cfg.pop(_PROVIDER_CREDS_KEY, None) or {}
    has_credentials = bool(creds.get("base_url") and creds.get("api_key"))
    return {
        "id": model.id, "slug": model.slug, "display_name": model.display_name,
        "capability": model.capability, "provider_key": model.provider_key,
        "provider_model_name": model.provider_model_name, "is_active": model.is_active,
        "pricing_type": model.pricing_type, "provider_type": model.provider_type,
        "tokenizer_encoding": model.tokenizer_encoding,
        "base_url": creds.get("base_url") or "",
        "config_json": cfg or None, "description": model.description,
        "has_credentials": has_credentials,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }


@bp.get("/admin/models")
@admin_required
def list_models_admin():
    # Self-heal: the system image model (billing anchor for the hardcoded
    # image backend) must exist before the admin can set its tariff, so make
    # sure it is there on every admin listing.
    from app.api.v1.image import ensure_system_image_model
    ensure_system_image_model()
    capability = request.args.get("capability")
    query = db.session.query(AiModel)
    if capability:
        query = query.filter_by(capability=capability)
    query = query.order_by(AiModel.capability, AiModel.display_name)
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    return success_response([_model_payload(m) for m in items], meta)


def _slugify(value: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:60]


def _unique_slug(base: str) -> str:
    slug = base or f"model-{secrets.token_hex(3)}"
    candidate, n = slug, 2
    while db.session.query(AiModel.id).filter_by(slug=candidate).first():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


@bp.post("/admin/models")
@admin_required
def create_model():
    data, err = _parse(ModelCreateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if data.capability not in CAPABILITIES:
        return validation_error()
    provider_type = (data.provider_type or "").strip().lower() or "openai_compat"
    if provider_type not in PROVIDER_TYPES:
        return error_response("VALIDATION_ERROR", "نوع provider نامعتبر است.", 422)
    raw_slug = (data.slug or "").strip()
    if raw_slug:
        if db.session.query(AiModel).filter_by(slug=raw_slug).one_or_none():
            return error_response("CONFLICT", "این slug قبلاً ثبت شده است.", 409)
        slug = raw_slug
    else:
        slug = _unique_slug(
            _slugify(data.provider_model_name) or _slugify(data.display_name))
    provider_key = (data.provider_key or "").strip() or slug
    # TEMP (model testing): tokenizer validation disabled entirely.
    # The encoding name is stored as-is; chat falls back to estimated
    # token counts when tiktoken is unavailable.
    encoding = (data.tokenizer_encoding or "").strip() or None
    try:
        config_with_creds = _store_provider_creds(data.config_json, data.base_url, data.api_key)
    except ValueError as exc:
        return error_response("VALIDATION_ERROR", str(exc), 422)
    model = AiModel(
        slug=slug, display_name=data.display_name.strip(),
        capability=data.capability, provider_key=provider_key,
        provider_model_name=data.provider_model_name.strip(),
        provider_type=provider_type,
        is_active=data.is_active, pricing_type=data.pricing_type,
        tokenizer_encoding=encoding, config_json=config_with_creds,
        description=data.description,
    )
    db.session.add(model)
    db.session.flush()
    _audit("model.created", "ai_model", model.id, {"slug": model.slug})
    db.session.commit()
    payload = _model_payload(model)
    return success_response(payload, status=201)


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
    if data.provider_type is not None:
        pt = data.provider_type.strip().lower() or "openai_compat"
        if pt not in PROVIDER_TYPES:
            return error_response("VALIDATION_ERROR", "نوع provider نامعتبر است.", 422)
        model.provider_type = pt; changes["provider_type"] = pt
    if data.pricing_type is not None:
        model.pricing_type = data.pricing_type; changes["pricing_type"] = data.pricing_type
    if data.provider_model_name is not None:
        model.provider_model_name = data.provider_model_name.strip()
        changes["provider_model_name"] = model.provider_model_name
    if data.tokenizer_encoding is not None:
        # TEMP (model testing): tokenizer validation disabled; stored as-is.
        model.tokenizer_encoding = (data.tokenizer_encoding or "").strip() or None
        changes["tokenizer_encoding"] = model.tokenizer_encoding
    if data.config_json is not None:
        model.config_json = data.config_json; changes["config_json"] = True
    if data.base_url or data.api_key:
        try:
            model.config_json = _store_provider_creds(
                model.config_json, data.base_url, data.api_key)
        except ValueError as exc:
            return error_response("VALIDATION_ERROR", str(exc), 422)
        changes["provider_credentials"] = True
    if data.description is not None:
        model.description = data.description; changes["description"] = True
    _audit("model.updated", "ai_model", model.id, changes)
    db.session.commit()
    payload = _model_payload(model)
    return success_response(payload)


@bp.delete("/admin/models/<model_id>")
@admin_required
def delete_model(model_id: str):
    model = db.session.get(AiModel, model_id)
    if model is None:
        return error_response("NOT_FOUND", status=404)
    if model.slug == "nourai-image":
        return error_response(
            "VALIDATION_ERROR", "مدل سیستمی تصویر قابل حذف نیست.", 422
        )
    refs = []
    if db.session.query(GenerationJob).filter_by(model_id=model.id).limit(1).first():
        refs.append("jobها")
    if db.session.query(ModelPricingRule).filter_by(model_id=model.id).limit(1).first():
        refs.append("تعرفه‌ها")
    if db.session.query(UsageEvent).filter_by(model_id=model.id).limit(1).first():
        refs.append("رویدادهای مصرف")
    if refs:
        return error_response(
            "MODEL_IN_USE",
            f"این مدل در {'، '.join(refs)} استفاده شده و قابل حذف نیست؛ غیرفعالش کنید.",
            409,
        )
    _audit("model.deleted", "ai_model", model.id, {"slug": model.slug})
    db.session.delete(model)
    db.session.commit()
    return success_response({"deleted": model_id})


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
        "is_global": profile.model_id is None,
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
        # NULLS FIRST is not valid MySQL syntax; IS NULL DESC is portable.
        .order_by(ImageProcessingProfile.model_id.is_(None).desc(),
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
    upload = request.files.get("file") or request.files.get("image")
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
# Currency settings (USD->IRR rate + image cost-protection margin)
# ---------------------------------------------------------------------------
def get_currency_settings() -> CurrencySettings:
    """Get-or-create the singleton currency settings row."""
    settings = (
        db.session.query(CurrencySettings)
        .order_by(CurrencySettings.created_at)
        .first()
    )
    if settings is None:
        settings = CurrencySettings(usd_to_irr=0, image_cost_margin_pct=30.0)
        db.session.add(settings)
        db.session.flush()
    return settings


class CurrencySettingsSchema(BaseModel):
    usd_to_irr: int
    image_cost_margin_pct: float


@bp.get("/admin/settings/currency")
@admin_required
def get_currency():
    return success_response(get_currency_settings().snapshot())


@bp.put("/admin/settings/currency")
@admin_required
def update_currency():
    data, err = _parse(CurrencySettingsSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if data.usd_to_irr < 0:
        return error_response("VALIDATION_ERROR", "نرخ دلار نامعتبر است.", 422)
    if not 0 <= data.image_cost_margin_pct <= 100:
        return error_response("VALIDATION_ERROR", "درصد مارجین باید بین ۰ تا ۱۰۰ باشد.", 422)
    settings = get_currency_settings()
    changes = {}
    if settings.usd_to_irr != data.usd_to_irr:
        changes["usd_to_irr"] = data.usd_to_irr
        settings.usd_to_irr = data.usd_to_irr
    if settings.image_cost_margin_pct != data.image_cost_margin_pct:
        changes["image_cost_margin_pct"] = data.image_cost_margin_pct
        settings.image_cost_margin_pct = data.image_cost_margin_pct
    _audit("currency_settings.updated", "currency_settings", settings.id, changes)
    db.session.commit()
    return success_response(settings.snapshot())


# ---------------------------------------------------------------------------
# Site settings (contact page)
# ---------------------------------------------------------------------------
def _get_site_settings() -> SiteSettings:
    settings = db.session.query(SiteSettings).first()
    if settings is None:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.flush()
    return settings


@bp.get("/admin/settings/site")
@admin_required
def get_site_settings():
    return success_response(_get_site_settings().to_dict())


@bp.put("/admin/settings/site")
@admin_required
def update_site_settings():
    data = request.get_json(silent=True) or {}
    settings = _get_site_settings()
    fields = ("contact_phone", "contact_email", "contact_address",
              "contact_telegram", "contact_instagram", "contact_eitaa",
              "contact_bale", "contact_description")
    changes = {}
    for f in fields:
        if f in data:
            val = (data[f] or "").strip() or None
            if getattr(settings, f) != val:
                changes[f] = val
                setattr(settings, f, val)
    db.session.commit()
    return success_response(settings.to_dict())


# ---------------------------------------------------------------------------
# Pricing rules (versioned)
# ---------------------------------------------------------------------------
class PricingRuleCreateSchema(BaseModel):
    model_id: str
    billing_unit: str
    unit_size: int = 1
    unit_price_usd: Decimal
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


def _model_display_names(model_ids: set[str]) -> dict[str, str]:
    """Batch-load display names for pricing payloads (avoids N+1)."""
    if not model_ids:
        return {}
    rows = (
        db.session.query(AiModel.id, AiModel.display_name)
        .filter(AiModel.id.in_(model_ids))
        .all()
    )
    return {row[0]: row[1] for row in rows}


def _rule_payload(rule: ModelPricingRule, model_name: str | None = None) -> dict:
    return {
        "id": rule.id, "model_id": rule.model_id, "model_name": model_name,
        "version": rule.version,
        "billing_unit": rule.billing_unit, "unit_size": rule.unit_size,
        "unit_price_usd": format_usd(rule.unit_price_usd),
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
    names = _model_display_names({r.model_id for r in items})
    return success_response(
        [_rule_payload(r, names.get(r.model_id)) for r in items], meta
    )


@bp.post("/admin/pricing-rules")
@admin_required
def create_pricing_rule():
    data, err = _parse(PricingRuleCreateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    model = db.session.get(AiModel, data.model_id)
    if model is None:
        return error_response("NOT_FOUND", "مدل یافت نشد.", 404)
    if data.unit_size <= 0 or data.unit_price_usd < 0:
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
        unit_price_usd=data.unit_price_usd,
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
            "version": rule.version, "unit_price_usd": format_usd(data.unit_price_usd)})
    db.session.commit()
    names = _model_display_names({rule.model_id})
    return success_response(_rule_payload(rule, names.get(rule.model_id)), status=201)


@bp.patch("/admin/pricing-rules/<rule_id>")
@admin_required
def update_pricing_rule(rule_id: str):
    data, err = _parse(PricingRuleUpdateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    rule = db.session.get(ModelPricingRule, rule_id)
    if rule is None:
        return error_response("NOT_FOUND", status=404)
    # model_fields_set distinguishes "not sent" (leave alone) from
    # "sent as null" (clear the value).
    provided = data.model_fields_set
    changes: dict = {}
    if "is_active" in provided and data.is_active is not None:
        rule.is_active = data.is_active; changes["is_active"] = data.is_active
    if "minimum_charge_irr" in provided:
        rule.minimum_charge_irr = data.minimum_charge_irr
        changes["minimum_charge_irr"] = data.minimum_charge_irr
    if "maximum_charge_irr" in provided:
        rule.maximum_charge_irr = data.maximum_charge_irr
        changes["maximum_charge_irr"] = data.maximum_charge_irr
    if "effective_from" in provided:
        rule.effective_from = _parse_date(data.effective_from)
        changes["effective_from"] = data.effective_from
    if "effective_to" in provided:
        rule.effective_to = _parse_date(data.effective_to)
        changes["effective_to"] = data.effective_to
    # Price changes go through POST (new version); PATCH never rewrites history.
    _audit("pricing_rule.updated", "model_pricing_rule", rule.id, changes)
    db.session.commit()
    names = _model_display_names({rule.model_id})
    return success_response(_rule_payload(rule, names.get(rule.model_id)))


@bp.delete("/admin/pricing-rules/<rule_id>")
@admin_required
def delete_pricing_rule(rule_id: str):
    rule = db.session.get(ModelPricingRule, rule_id)
    if rule is None:
        return error_response("NOT_FOUND", status=404)
    # Usage events keep a frozen snapshot of the rule, so history survives;
    # only the link is cleared.
    db.session.query(UsageEvent).filter_by(pricing_rule_id=rule.id).update(
        {"pricing_rule_id": None}, synchronize_session=False
    )
    _audit("pricing_rule.deleted", "model_pricing_rule", rule.id,
           {"model_id": rule.model_id, "billing_unit": rule.billing_unit,
            "version": rule.version, "unit_price_usd": str(rule.unit_price_usd)})
    db.session.delete(rule)
    db.session.commit()
    return success_response({"deleted": True})


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
    search = (request.args.get("search") or "").strip()
    if search:
        user = _find_user_by_search(db.session, search)
        if user is None:
            query = query.filter(db.false())
        else:
            query = query.filter(
                ((AuditLog.actor_type == "user") & (AuditLog.actor_id == user.id))
                | ((AuditLog.target_type == "user") & (AuditLog.target_id == user.id))
            )
    query = query.order_by(AuditLog.created_at.desc())
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    labels = _audit_party_labels(db.session, items)
    return paginated_response(
        [
            {
                "id": e.id, "actor_type": e.actor_type, "actor_id": e.actor_id,
                "actor_label": labels.get((e.actor_type, e.actor_id)),
                "action": e.action,
                "target_type": e.target_type, "target_id": e.target_id,
                "target_label": labels.get((e.target_type, e.target_id)),
                "metadata": e.metadata_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
        page,
        page_size,
        meta["total"],
    )


def _find_user_by_search(session, search: str):
    """Find a user by mobile number (exact normalized match)."""
    try:
        normalized = normalize_mobile(search)
    except ValueError:
        normalized = "".join(c for c in search if c.isdigit())
    if not normalized:
        return None
    return session.query(User).filter_by(mobile_normalized=normalized).one_or_none()


def _audit_party_labels(session, entries) -> dict:
    """Human-readable names for audit actors and targets: username for
    admins, masked mobile for users. Bulk-fetched to avoid N+1 queries."""
    admin_ids: set = set()
    user_ids: set = set()
    for e in entries:
        for party_type, party_id in ((e.actor_type, e.actor_id), (e.target_type, e.target_id)):
            if not party_id:
                continue
            if party_type == "admin":
                admin_ids.add(party_id)
            elif party_type == "user":
                user_ids.add(party_id)
    labels: dict = {}
    if admin_ids:
        for admin in session.query(AdminUser).filter(AdminUser.id.in_(admin_ids)).all():
            labels[("admin", admin.id)] = admin.username
    if user_ids:
        for user in session.query(User).filter(User.id.in_(user_ids)).all():
            labels[("user", user.id)] = mask_mobile(user.mobile_normalized)
    return labels


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


# ---------------------------------------------------------------------------
# Job management: cancel stuck jobs.
# NOTE: GET /admin/jobs (list_jobs, with ?status= filter) already exists
# above; the frontend queries it with ?status=queued / ?status=processing.
# ---------------------------------------------------------------------------
@bp.post("/admin/jobs/<job_id>/cancel")
@admin_required
def admin_cancel_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None:
        return error_response("NOT_FOUND", status=404)
    if not cancel_job(db.session, job=job, reason="cancelled by admin"):
        return error_response("JOB_NOT_CANCELLABLE", "این درخواست در وضعیت پایانی است.", 409)
    db.session.commit()
    _audit("job.cancelled", "job", job.id,
           {"capability": job.capability, "user_id": job.user_id})
    db.session.commit()
    return success_response({"id": job.id, "status": job.status})


# ---------------------------------------------------------------------------
# Prompt filter: global kill switch + admin-managed blocklist.
# ---------------------------------------------------------------------------
def _get_moderation_settings() -> ModerationSettings:
    """Get-or-create the singleton moderation settings row."""
    settings = (
        db.session.query(ModerationSettings)
        .order_by(ModerationSettings.created_at)
        .first()
    )
    if settings is None:
        settings = ModerationSettings(prompt_filter_enabled=True)
        db.session.add(settings)
        db.session.flush()
    return settings


@bp.get("/admin/prompt-filter")
@admin_required
def get_prompt_filter():
    settings = _get_moderation_settings()
    return success_response({"enabled": settings.prompt_filter_enabled})


class PromptFilterToggleSchema(BaseModel):
    enabled: bool


@bp.put("/admin/prompt-filter")
@admin_required
def set_prompt_filter():
    data, err = _parse(PromptFilterToggleSchema, request.get_json(silent=True) or {})
    if err:
        return err
    settings = _get_moderation_settings()
    settings.prompt_filter_enabled = data.enabled
    _audit("prompt_filter.toggled", "moderation_settings", settings.id,
           {"enabled": data.enabled})
    db.session.commit()
    return success_response({"enabled": settings.prompt_filter_enabled})


def _blocklist_payload(word: PromptBlocklist) -> dict:
    return {
        "id": word.id,
        "phrase": word.phrase,
        "category": word.category,
        "is_active": word.is_active,
        "note": word.note,
        "created_at": word.created_at.isoformat() if word.created_at else None,
        "updated_at": word.updated_at.isoformat() if word.updated_at else None,
    }


@bp.get("/admin/prompt-filter/words")
@admin_required
def list_blocklist_words():
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = min(max(int(request.args.get("per_page", 20) or 20), 1), 100)
    q = (request.args.get("q") or "").strip()
    query = db.session.query(PromptBlocklist)
    if q:
        query = query.filter(PromptBlocklist.phrase.ilike(f"%{q}%"))
    query = query.order_by(PromptBlocklist.created_at.desc())
    total = query.count()
    words = query.offset((page - 1) * per_page).limit(per_page).all()
    return paginated_response(
        [_blocklist_payload(w) for w in words], page, per_page, total
    )


class BlocklistCreateSchema(BaseModel):
    phrase: str
    category: str | None = None
    is_active: bool = True
    note: str | None = None


@bp.post("/admin/prompt-filter/words")
@admin_required
def create_blocklist_word():
    from app.services.prompt_filter import normalize_text

    data, err = _parse(BlocklistCreateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    phrase = (data.phrase or "").strip()
    if not phrase:
        return validation_error()
    norm = normalize_text(phrase)
    for w in db.session.query(PromptBlocklist).all():
        if normalize_text(w.phrase) == norm:
            return error_response("DUPLICATE", "این عبارت قبلاً ثبت شده است.", 409)
    word = PromptBlocklist(
        phrase=phrase,
        category=(data.category or "").strip() or None,
        is_active=data.is_active,
        note=(data.note or "").strip() or None,
        created_by_admin_id=g.current_admin_id,
    )
    db.session.add(word)
    db.session.flush()
    _audit("prompt_blocklist.created", "prompt_blocklist", word.id, {"phrase": phrase})
    db.session.commit()
    return success_response(_blocklist_payload(word), status=201)


class BlocklistUpdateSchema(BaseModel):
    phrase: str | None = None
    category: str | None = None
    is_active: bool | None = None
    note: str | None = None


@bp.patch("/admin/prompt-filter/words/<word_id>")
@admin_required
def update_blocklist_word(word_id: str):
    from app.services.prompt_filter import normalize_text

    word = db.session.get(PromptBlocklist, word_id)
    if word is None:
        return error_response("NOT_FOUND", status=404)
    data, err = _parse(BlocklistUpdateSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if data.phrase is not None:
        phrase = data.phrase.strip()
        if not phrase:
            return validation_error()
        norm = normalize_text(phrase)
        for w in db.session.query(PromptBlocklist).all():
            if w.id != word.id and normalize_text(w.phrase) == norm:
                return error_response("DUPLICATE", "این عبارت قبلاً ثبت شده است.", 409)
        word.phrase = phrase
    if data.category is not None:
        word.category = data.category.strip() or None
    if data.is_active is not None:
        word.is_active = data.is_active
    if data.note is not None:
        word.note = data.note.strip() or None
    db.session.commit()
    return success_response(_blocklist_payload(word))


@bp.delete("/admin/prompt-filter/words/<word_id>")
@admin_required
def delete_blocklist_word(word_id: str):
    word = db.session.get(PromptBlocklist, word_id)
    if word is None:
        return error_response("NOT_FOUND", status=404)
    _audit("prompt_blocklist.deleted", "prompt_blocklist", word.id,
           {"phrase": word.phrase})
    db.session.delete(word)
    db.session.commit()
    return success_response({"id": word_id})


# -- blog posts ------------------------------------------------------------

def _blog_payload(p) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "description": p.description,
        "cover_image_url": p.cover_image_url,
        "content": p.content_json or [],
        "is_published": p.is_published,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@bp.get("/admin/blog")
@admin_required
def list_blog_posts():
    posts = db.session.query(BlogPost).order_by(BlogPost.created_at.desc()).all()
    return success_response([_blog_payload(p) for p in posts])


class BlogPostSchema(BaseModel):
    slug: str
    title: str
    description: str = ""
    cover_image_url: str | None = None
    content: list[str] = []
    is_published: bool = False


class BlogPostPatchSchema(BaseModel):
    """Partial update: every field optional; only provided fields change."""
    slug: str | None = None
    title: str | None = None
    description: str | None = None
    cover_image_url: str | None = None
    content: list[str] | None = None
    is_published: bool | None = None


@bp.post("/admin/blog")
@admin_required
def create_blog_post():
    data, err = _parse(BlogPostSchema, request.get_json(silent=True) or {})
    if err:
        return err
    slug = data.slug.strip()
    if not slug or not data.title.strip():
        return validation_error()
    if db.session.query(BlogPost).filter_by(slug=slug).first():
        return error_response("DUPLICATE", "این نامک قبلاً استفاده شده است.", 422)
    post = BlogPost(
        id=new_uuid(),
        slug=slug,
        title=data.title.strip(),
        description=(data.description or "").strip(),
        cover_image_url=(data.cover_image_url or "").strip() or None,
        content_json=[str(c) for c in (data.content or [])],
        is_published=data.is_published,
    )
    db.session.add(post)
    _audit("blog.created", "blog_post", post.id, {"slug": slug, "title": post.title})
    db.session.commit()
    return success_response(_blog_payload(post), status=201)


@bp.patch("/admin/blog/<post_id>")
@admin_required
def update_blog_post(post_id: str):
    post = db.session.get(BlogPost, post_id)
    if post is None:
        return error_response("NOT_FOUND", status=404)
    data, err = _parse(BlogPostPatchSchema, request.get_json(silent=True) or {})
    if err:
        return err
    if data.slug is not None:
        slug = data.slug.strip()
        if not slug:
            return validation_error()
        dup = db.session.query(BlogPost).filter(BlogPost.slug == slug, BlogPost.id != post_id).first()
        if dup:
            return error_response("DUPLICATE", "این نامک قبلاً استفاده شده است.", 422)
        post.slug = slug
    if data.title is not None:
        if not data.title.strip():
            return validation_error()
        post.title = data.title.strip()
    if data.description is not None:
        post.description = data.description.strip()
    if data.cover_image_url is not None:
        post.cover_image_url = data.cover_image_url.strip() or None
    if data.content is not None:
        post.content_json = [str(c) for c in data.content]
    if data.is_published is not None:
        was_published = post.is_published
        post.is_published = data.is_published
        # If newly published, queue for Bale channel
        if data.is_published and not was_published:
            db.session.flush()  # Ensure post.id is available
            _queue_for_bale("blog", post.id, None)
    _audit("blog.updated", "blog_post", post.id, {"slug": post.slug})
    db.session.commit()
    return success_response(_blog_payload(post))


@bp.delete("/admin/blog/<post_id>")
@admin_required
def delete_blog_post(post_id: str):
    post = db.session.get(BlogPost, post_id)
    if post is None:
        return error_response("NOT_FOUND", status=404)
    _audit("blog.deleted", "blog_post", post.id, {"slug": post.slug})
    db.session.delete(post)
    db.session.commit()
    return success_response({"id": post_id})


@bp.post("/admin/blog/upload-cover")
@admin_required
def upload_blog_cover():
    """Upload a blog cover image. Returns the storage key."""
    upload = request.files.get("file") or request.files.get("image")
    if upload is None:
        return validation_error()
    raw = upload.read()
    if not raw or len(raw) > 5 * 1024 * 1024:
        return validation_error()
    # Basic image type check.
    import imghdr
    kind = imghdr.what(None, h=raw)
    if kind not in ("jpeg", "png", "webp", "gif"):
        return error_response("VALIDATION_ERROR", "فرمت تصویر پشتیبانی نمی‌شود.", 422)
    ext = "jpg" if kind == "jpeg" else kind
    key = f"blog/covers/{new_uuid()}.{ext}"
    storage.put_bytes(key, raw, f"image/{kind}")
    return success_response({"key": key, "url": f"/api/v1/blog/cover?key={key}"})


@bp.post("/admin/blog/upload-image")
@admin_required
def upload_blog_image():
    """Upload an inline image for a blog post body. Returns the public URL."""
    upload = request.files.get("file") or request.files.get("image")
    if upload is None:
        return validation_error()
    raw = upload.read()
    if not raw or len(raw) > 5 * 1024 * 1024:
        return validation_error()
    import imghdr
    kind = imghdr.what(None, h=raw)
    if kind not in ("jpeg", "png", "webp", "gif"):
        return error_response("VALIDATION_ERROR", "فرمت تصویر پشتیبانی نمی‌شود.", 422)
    ext = "jpg" if kind == "jpeg" else kind
    key = f"blog/images/{new_uuid()}.{ext}"
    storage.put_bytes(key, raw, f"image/{kind}")
    return success_response({"key": key, "url": f"/api/v1/blog/image?key={key}"})


# --- Bale Publish Queue ---

def _queue_for_bale(content_type: str, content_id: str, caption: str | None):
    """Add an item to the Bale publish queue (if not already queued)."""
    from app.models.bale_publish import BALE_QUEUE_PENDING
    # Avoid duplicates
    existing = (
        db.session.query(BalePublishQueue)
        .filter_by(content_type=content_type, content_id=content_id)
        .filter(BalePublishQueue.status.in_(["pending", "approved"]))
        .first()
    )
    if existing:
        return existing
    q = BalePublishQueue(
        id=new_uuid(),
        content_type=content_type,
        content_id=content_id,
        status=BALE_QUEUE_PENDING,
        caption=caption,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.session.add(q)
    # Note: caller must commit
    return q


@bp.get("/admin/bale-queue")
@admin_required
def list_bale_queue():
    from app.models.bale_publish import BALE_QUEUE_STATUSES
    status = request.args.get("status", "pending")
    if status not in BALE_QUEUE_STATUSES:
        return validation_error()
    query = (
        db.session.query(BalePublishQueue)
        .filter_by(status=status)
        .order_by(BalePublishQueue.created_at.desc())
    )
    page, page_size = pagination_params()
    items, meta = paginate_query(query, page, page_size)
    results = []
    for q in items:
        item = {
            "id": q.id,
            "content_type": q.content_type,
            "content_id": q.content_id,
            "status": q.status,
            "caption": q.caption,
            "created_at": q.created_at.isoformat() + "Z" if q.created_at else None,
            "reviewed_at": q.reviewed_at.isoformat() + "Z" if q.reviewed_at else None,
            "published_at": q.published_at.isoformat() + "Z" if q.published_at else None,
        }
        # Enrich with content details
        if q.content_type == "gallery":
            entry = db.session.get(GalleryEntry, q.content_id)
            if entry:
                asset = db.session.get(Asset, entry.asset_id)
                if asset:
                    item["image_url"] = f"/api/v1/assets/{asset.id}/download?stream=1"
                    job = db.session.get(GenerationJob, asset.job_id) if asset.job_id else None
                    item["prompt"] = (job.prompt_text or "")[:200] if job else None
        elif q.content_type == "blog":
            post = db.session.get(BlogPost, q.content_id)
            if post:
                item["title"] = post.title
                item["description"] = post.description
                item["cover_image_url"] = post.cover_image_url
                item["slug"] = post.slug
        results.append(item)
    return success_response({"items": results, "meta": meta})


@bp.post("/admin/bale-queue/<queue_id>/approve")
@admin_required
def approve_bale_queue(queue_id):
    from app.models.bale_publish import BALE_QUEUE_PENDING, BALE_QUEUE_APPROVED
    q = db.session.get(BalePublishQueue, queue_id)
    if not q or q.status != BALE_QUEUE_PENDING:
        return error_response("NOT_FOUND", "یافت نشد.", 404)
    q.status = BALE_QUEUE_APPROVED
    q.reviewed_by_admin_id = g.admin_user.id
    q.reviewed_at = utcnow()
    q.updated_at = utcnow()
    db.session.commit()
    # Try to publish to Bale channel immediately
    try:
        _publish_to_bale_channel(q)
        q.status = "published"
        q.published_at = utcnow()
        db.session.commit()
    except Exception as e:
        # Log but don't fail - admin can retry
        import logging
        logging.getLogger(__name__).exception("Bale publish failed for %s", q.id)
    return success_response({"id": q.id, "status": q.status})


@bp.post("/admin/bale-queue/<queue_id>/reject")
@admin_required
def reject_bale_queue(queue_id):
    from app.models.bale_publish import BALE_QUEUE_PENDING, BALE_QUEUE_REJECTED
    q = db.session.get(BalePublishQueue, queue_id)
    if not q or q.status != BALE_QUEUE_PENDING:
        return error_response("NOT_FOUND", "یافت نشد.", 404)
    q.status = BALE_QUEUE_REJECTED
    q.reviewed_by_admin_id = g.admin_user.id
    q.reviewed_at = utcnow()
    q.updated_at = utcnow()
    db.session.commit()
    return success_response({"id": q.id, "status": q.status})


def _publish_to_bale_channel(queue_item):
    """Send the queue item to the Bale channel."""
    import requests
    from flask import current_app

    # Get bot token from config (not from .env directly)
    token = current_app.config.get("BALE_BOT_TOKEN")
    if not token:
        raise RuntimeError("Bale bot token not configured")

    channel = "@iNourAi"
    base_url = f"https://tapi.bale.ai/bot{token}"

    if queue_item.content_type == "gallery":
        entry = db.session.get(GalleryEntry, queue_item.content_id)
        if not entry:
            raise RuntimeError("Gallery entry not found")
        asset = db.session.get(Asset, entry.asset_id)
        if not asset:
            raise RuntimeError("Asset not found")

        # Get image URL (public)
        image_url = f"https://inourai.ir/api/v1/assets/{asset.id}/download?stream=1"
        caption = queue_item.caption or "🎨 تصویر جدید در گالری نورا"

        resp = requests.post(
            f"{base_url}/sendPhoto",
            json={"chat_id": channel, "photo": image_url, "caption": caption},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            queue_item.bale_message_id = str(data["result"]["message_id"])

    elif queue_item.content_type == "blog":
        post = db.session.get(BlogPost, queue_item.content_id)
        if not post:
            raise RuntimeError("Blog post not found")

        text = f"📝 {post.title}\n\n{post.description}\n\nhttps://inourai.ir/blog/{post.slug}"
        resp = requests.post(
            f"{base_url}/sendMessage",
            json={"chat_id": channel, "text": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            queue_item.bale_message_id = str(data["result"]["message_id"])
