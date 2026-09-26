"""Audio jobs: upload -> STT -> text -> TTS chain (async via Celery)."""
from __future__ import annotations

import hashlib
import logging

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError

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
from app.models import AiModel, Asset, GenerationJob, UsageEvent
from app.models.catalog import CAP_STT, CAP_TEXT, CAP_TTS
from app.models.jobs import ASSET_INPUT_AUDIO, JOB_QUEUED
from app.services.storage import asset_key, storage
from app.services.audit import audit
from app.services.plans import PlanLimitExceeded, PlanLimitService

log = logging.getLogger(__name__)

bp = Blueprint("audio", __name__)


def sniff_audio_mime(data: bytes, declared: str | None = None) -> str | None:
    """Best-effort audio MIME sniff from magic bytes (never trust extension)."""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if len(data) > 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"M4A ", b"mp42", b"isom"):
            return "audio/m4a" if brand == b"M4A " else "audio/mp4"
    # Fall back to the declared type only if it is on the allowlist.
    if declared in config.audio_allowed_mime_types:
        return declared
    return None


def _resolve_model(model_id: str | None, capability: str) -> AiModel | None:
    if model_id:
        model = db.session.get(AiModel, model_id)
        if model and model.capability == capability and model.is_active:
            return model
        return None
    return (
        db.session.query(AiModel)
        .filter_by(capability=capability, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )


class AudioJobSchema(BaseModel):
    stt_model_id: str | None = None
    text_model_id: str | None = None
    tts_model_id: str | None = None


def _job_payload(job: GenerationJob) -> dict:
    output_asset = (
        db.session.query(Asset)
        .filter_by(job_id=job.id, kind="output_audio")
        .order_by(Asset.created_at.desc())
        .first()
    )
    return {
        "id": job.id,
        "status": job.status,
        "result_text": job.result_text,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "input_asset_id": (job.parameters_json or {}).get("input_asset_id"),
        "output_asset_id": output_asset.id if output_asset else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@bp.post("/audio/jobs")
@login_required
def create_audio_job():
    if rate_limited(f"ai:req:{g.current_user_id}", config.rate_limit_ai_request,
                    config.rate_limit_ai_request_window):
        return error_response("RATE_LIMITED", status=429)

    try:
        PlanLimitService(db.session).check(g.current_user_id, "audio")
    except PlanLimitExceeded:
        return error_response("PLAN_LIMIT_EXCEEDED", status=403)

    try:
        data = AudioJobSchema(**{k: request.form.get(k) or None
                                 for k in ("stt_model_id", "text_model_id", "tts_model_id")})
    except ValidationError:
        return validation_error()

    upload = request.files.get("file")
    if upload is None:
        return validation_error()
    raw = upload.read()
    if not raw:
        return validation_error()
    if len(raw) > config.audio_upload_max_bytes:
        return error_response("FILE_TOO_LARGE", status=413)

    mime = sniff_audio_mime(raw, upload.mimetype)
    if mime not in config.audio_allowed_mime_types:
        return error_response("VALIDATION_ERROR", "نوع فایل صوتی پشتیبانی نمی‌شود.", 422)

    stt_model = _resolve_model(data.stt_model_id, CAP_STT)
    text_model = _resolve_model(data.text_model_id, CAP_TEXT)
    tts_model = _resolve_model(data.tts_model_id, CAP_TTS)
    if not stt_model or not tts_model or not text_model:
        return error_response("MODEL_UNAVAILABLE", status=404)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("VALIDATION_ERROR", "Idempotency-Key header is required.", 422)

    # Reserve conservatively on the maximum billable duration; the worker
    # settles on the actual duration afterwards.
    pricing = PricingService(db.session)
    try:
        estimate = pricing.estimate_audio(stt_model.id, config.audio_max_duration_seconds,
                                          text_model_id=text_model.id)
    except PricingRuleUnavailable:
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)
    estimated_irr = estimate["total_irr"]

    # Store the private input asset.
    ext = {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg",
           "audio/webm": "webm", "audio/mp4": "mp4", "audio/m4a": "m4a"}.get(mime, "bin")
    key = asset_key(g.current_user_id, ASSET_INPUT_AUDIO, ext)
    try:
        storage.put_bytes(key, raw, mime)
    except Exception:  # noqa: BLE001
        log.exception("audio upload to storage failed")
        return error_response("PROVIDER_ERROR", status=502)

    input_asset = Asset(
        user_id=g.current_user_id, kind=ASSET_INPUT_AUDIO, storage_key=key,
        mime_type=mime, size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    db.session.add(input_asset)
    db.session.flush()

    job = GenerationJob(
        user_id=g.current_user_id,
        capability="audio",
        model_id=stt_model.id,
        status=JOB_QUEUED,
        parameters_json={
            "input_asset_id": input_asset.id,
            "stt_model_id": stt_model.id,
            "text_model_id": text_model.id,
            "tts_model_id": tts_model.id,
            "mime_type": mime,
            "size_bytes": len(raw),
        },
    )
    db.session.add(job)
    db.session.flush()

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"audio:{job.id}:reserve",
            reference_type="job", reference_id=job.id,
            description="reserve audio processing",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass

    input_asset.job_id = job.id
    usage = UsageEvent(
        user_id=g.current_user_id, job_id=job.id, model_id=stt_model.id,
        provider_key=stt_model.provider_key, status="processing",
        audio_seconds=config.audio_max_duration_seconds,
        tokenizer_encoding=None, token_count_source=None,
        pricing_snapshot_json=estimate["pricing_snapshots"],
        estimated_amount_irr=estimated_irr, reserved_amount_irr=estimated_irr,
        metadata_json={"idempotency_key": idempotency_key},
    )
    db.session.add(usage)
    db.session.commit()

    audit(db.session, actor_type="user", actor_id=g.current_user_id,
          action="audio.job_created", target_type="job", target_id=job.id,
          metadata={"size_bytes": len(raw)}, ip_hash=ip_hash(client_ip()))
    db.session.commit()

    from app.tasks.audio_tasks import process_audio_job
    process_audio_job.delay(job.id)

    return success_response(_job_payload(job), status=201)


@bp.get("/audio/jobs/<job_id>")
@login_required
def get_audio_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None or job.user_id != g.current_user_id or job.capability != "audio":
        return error_response("NOT_FOUND", status=404)
    return success_response(_job_payload(job))


@bp.get("/audio/jobs")
@login_required
def list_audio_jobs():
    page, page_size = pagination_params()
    query = (
        db.session.query(GenerationJob)
        .filter_by(user_id=g.current_user_id, capability="audio")
        .order_by(GenerationJob.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([_job_payload(j) for j in items], page, page_size, meta["total"])
