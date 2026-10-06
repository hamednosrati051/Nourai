"""Standalone text-to-speech worker: text -> TTS provider -> output audio asset.

The provider is resolved from the TTS model row (model-driven, same pattern
as the text/STT selectors). Billing was held at request time as a fixed
per-request tariff; success settles it, failure releases it.
"""
from __future__ import annotations

import hashlib
import logging

from app.ai.adapters import get_tts_provider
from app.extensions import db
from app.models import AiModel, Asset, GenerationJob, UsageEvent
from app.models.catalog import CAP_TTS
from app.models.jobs import (
    ASSET_OUTPUT_AUDIO,
    JOB_FAILED,
    JOB_PROCESSING,
    JOB_SUCCEEDED,
)
from app.services.plans import PlanLimitService
from app.services.storage import asset_key, storage
from app.tasks import (
    aborted_during_processing,
    get_flask_app,
    release_job_billing,
    settle_job_billing,
)
from app.tasks.celery_app import celery

log = logging.getLogger(__name__)

_SAFE_ERROR = "تبدیل متن به صوت ناموفق بود. لطفاً دوباره تلاش کنید."


@celery.task(bind=True, name="nourai.tts.process", max_retries=2)
def process_tts_job(self, job_id: str) -> dict:
    app = get_flask_app()
    with app.app_context():
        from app.api.deps import utcnow

        session = db.session
        job = session.get(GenerationJob, job_id)
        if job is None:
            return {"ok": False, "error": "not_found"}
        if job.status not in ("queued", "processing"):
            log.info("tts job %s already %s; skipping", job_id, job.status)
            return {"ok": True, "already": job.status}

        usage = (
            session.query(UsageEvent)
            .filter_by(job_id=job.id)
            .order_by(UsageEvent.created_at.desc())
            .first()
        )

        job.status = JOB_PROCESSING
        job.started_at = utcnow()
        session.commit()

        quota_covered = bool((job.parameters_json or {}).get("quota_covered"))
        quota_minutes = int((job.parameters_json or {}).get("quota_minutes") or 1)
        try:
            output_asset = _run_synthesis(session, job)
        except Exception:  # noqa: BLE001
            log.exception("tts job %s failed", job_id)
            job.status = JOB_FAILED
            job.error_code = "PROVIDER_ERROR"
            job.error_message = _SAFE_ERROR
            job.finished_at = utcnow()
            if usage is not None and not quota_covered:
                release_job_billing(session, job=job, usage=usage, reason="provider failed")
            elif usage is not None:
                usage.charged_amount_irr = 0
                usage.status = "failed"
            session.commit()
            return {"ok": False, "error": "PROVIDER_ERROR"}

        # The job may have been cancelled (admin) while the provider call
        # was in flight: release the hold instead of settling.
        if aborted_during_processing(session, job):
            return {"ok": False, "error": "CANCELLED"}

        final_amount = usage.reserved_amount_irr or 0 if usage else 0
        if usage is not None:
            if quota_covered:
                usage.charged_amount_irr = 0
                usage.status = "succeeded"
            else:
                settle_job_billing(session, job=job, usage=usage, final_amount_irr=final_amount)

        job.status = JOB_SUCCEEDED
        job.finished_at = utcnow()
        PlanLimitService(session).increment(job.user_id, "audio", amount=quota_minutes)
        session.commit()
        log.info("tts job %s succeeded chars=%d", job_id, len(job.prompt_text or ""))
        return {"ok": True, "asset_id": output_asset.id}


def _run_synthesis(session, job: GenerationJob) -> Asset:
    params = job.parameters_json or {}
    tts_model = session.get(AiModel, params.get("tts_model_id") or job.model_id)
    if tts_model is None or not tts_model.is_active:
        raise RuntimeError("no active TTS model")

    text = job.prompt_text or ""
    if not text:
        raise RuntimeError("empty text")

    tts = get_tts_provider(tts_model.provider_key, tts_model)
    audio_res = tts.synthesize(tts_model.provider_model_name, text, {"voice": params.get("voice")})
    if not audio_res.ok or not audio_res.audio_bytes:
        raise RuntimeError(audio_res.error_code or "tts failed")

    key = asset_key(job.user_id, ASSET_OUTPUT_AUDIO, "mp3")
    storage.put_bytes(key, audio_res.audio_bytes, audio_res.mime_type or "audio/mpeg")
    output_asset = Asset(
        user_id=job.user_id,
        job_id=job.id,
        kind=ASSET_OUTPUT_AUDIO,
        storage_key=key,
        mime_type=audio_res.mime_type or "audio/mpeg",
        size_bytes=len(audio_res.audio_bytes),
        sha256=hashlib.sha256(audio_res.audio_bytes).hexdigest(),
        duration_seconds=audio_res.duration_seconds,
        processing_metadata_json={"text_chars": len(text)},
    )
    session.add(output_asset)
    session.flush()
    return output_asset
