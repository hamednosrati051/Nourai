"""Standalone text-to-speech jobs: text -> TTS (async via Celery).

The TTS provider is model-driven: ``get_tts_provider`` reads ``provider_type``
from the admin model row (``fake`` | ``openai_compat``), same pattern as the
text and STT selectors. Billing is a fixed per-request tariff defined on the
TTS model in the admin pricing panel.
"""
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
from app.billing.pricing import (
    UNIT_FIXED_REQUEST,
    PricingRuleUnavailable,
    PricingService,
    snapshot_rule,
)
from app.config import config
from app.extensions import db
from app.models import AiModel, Asset, GenerationJob, UsageEvent
from app.models.catalog import CAP_TTS
from app.models.jobs import ASSET_OUTPUT_AUDIO, JOB_QUEUED
from app.services.audit import audit

log = logging.getLogger(__name__)

bp = Blueprint("tts", __name__)

TTS_MAX_CHARS = 2000


class TtsJobSchema(BaseModel):
    text: str
    tts_model_id: str | None = None


def _resolve_tts_model(model_id: str | None) -> AiModel | None:
    if model_id:
        model = db.session.get(AiModel, model_id)
        if model and model.capability == CAP_TTS and model.is_active:
            return model
        return None
    return (
        db.session.query(AiModel)
        .filter_by(capability=CAP_TTS, is_active=True)
        .order_by(AiModel.created_at)
        .first()
    )


def _tts_job_payload(job: GenerationJob) -> dict:
    output_asset = (
        db.session.query(Asset)
        .filter_by(job_id=job.id, kind=ASSET_OUTPUT_AUDIO)
        .order_by(Asset.created_at.desc())
        .first()
    )
    return {
        "id": job.id,
        "status": job.status,
        "text": job.prompt_text,
        "output_asset_id": output_asset.id if output_asset else None,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@bp.post("/tts/jobs")
@login_required
def create_tts_job():
    if rate_limited(f"ai:req:{g.current_user_id}", config.rate_limit_ai_request,
                    config.rate_limit_ai_request_window):
        return error_response("RATE_LIMITED", status=429)

    try:
        data = TtsJobSchema.model_validate(request.get_json(force=True, silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)

    text = (data.text or "").strip()
    if not text:
        return error_response("EMPTY_TEXT", "متن خالی است.", 422)
    if len(text) > TTS_MAX_CHARS:
        return error_response(
            "TEXT_TOO_LONG", f"متن نباید بیشتر از {TTS_MAX_CHARS} کاراکتر باشد.", 422
        )

    tts_model = _resolve_tts_model(data.tts_model_id)
    if not tts_model:
        return error_response("MODEL_UNAVAILABLE", status=404)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return error_response("IDEMPOTENCY_KEY_REQUIRED", status=428)

    pricing = PricingService(db.session)
    try:
        rule = pricing.get_active_rule(tts_model.id, UNIT_FIXED_REQUEST)
        estimated_irr, _breakdown = pricing.calculate(rule, 1)
        snapshots = [snapshot_rule(rule)]
    except PricingRuleUnavailable:
        return error_response("PRICING_RULE_UNAVAILABLE", status=500)

    job = GenerationJob(
        user_id=g.current_user_id,
        capability=CAP_TTS,
        model_id=tts_model.id,
        status=JOB_QUEUED,
        prompt_text=text,
        parameters_json={"tts_model_id": tts_model.id, "text_chars": len(text)},
    )
    db.session.add(job)
    db.session.flush()

    wallet = get_wallet_for_update(db.session, g.current_user_id)
    try:
        reserve(
            db.session, wallet=wallet, amount_irr=estimated_irr,
            idempotency_key=f"tts:{job.id}:reserve",
            reference_type="job", reference_id=job.id,
            description="reserve text-to-speech",
        )
    except InsufficientBalance:
        db.session.rollback()
        return error_response("INSUFFICIENT_BALANCE", status=402)
    except DuplicateIdempotencyKey:
        pass

    usage = UsageEvent(
        user_id=g.current_user_id, job_id=job.id, model_id=tts_model.id,
        provider_key=tts_model.provider_key, status="processing",
        tokenizer_encoding=None, token_count_source=None,
        pricing_snapshot_json=snapshots,
        estimated_amount_irr=estimated_irr, reserved_amount_irr=estimated_irr,
        metadata_json={"idempotency_key": idempotency_key},
    )
    db.session.add(usage)
    db.session.commit()

    audit(db.session, actor_type="user", actor_id=g.current_user_id,
          action="tts.job_created", target_type="job", target_id=job.id,
          metadata={"text_chars": len(text)}, ip_hash=ip_hash(client_ip()))
    db.session.commit()

    from app.tasks.tts_tasks import process_tts_job
    process_tts_job.delay(job.id)

    return success_response(_tts_job_payload(job), status=201)


@bp.get("/tts/jobs/<job_id>")
@login_required
def get_tts_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None or job.user_id != g.current_user_id or job.capability != CAP_TTS:
        return error_response("NOT_FOUND", status=404)
    return success_response(_tts_job_payload(job))


@bp.get("/tts/jobs")
@login_required
def list_tts_jobs():
    page, page_size = pagination_params()
    query = (
        db.session.query(GenerationJob)
        .filter_by(user_id=g.current_user_id, capability=CAP_TTS)
        .order_by(GenerationJob.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return paginated_response([_tts_job_payload(j) for j in items], page, page_size, meta["total"])
