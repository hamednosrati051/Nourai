"""Audio job worker: STT -> text model -> TTS chain.

Every artefact (input audio, transcript, reply text, output audio) is stored
as an asset owned by the user. Each sub-step settles against its own usage
event; a failure anywhere releases the remaining reserve and marks the job
failed with a safe message.
"""
from __future__ import annotations

import hashlib
import logging
import math

from app.ai.adapters import get_stt_provider, get_text_provider, get_tts_provider
from app.ai.tokens import TokenCounter
from app.billing.pricing import PricingService
from app.extensions import db
from app.models import AiModel, Asset, GenerationJob, UsageEvent
from app.models.catalog import CAP_TEXT
from app.models.jobs import (
    ASSET_INPUT_AUDIO,
    ASSET_OUTPUT_AUDIO,
    JOB_FAILED,
    JOB_PROCESSING,
    JOB_SUCCEEDED,
)
from app.services.storage import asset_key, storage
from app.services.plans import PlanLimitService
from app.tasks import (
    aborted_during_processing,
    get_flask_app,
    release_job_billing,
    settle_job_billing,
)
from app.tasks.celery_app import celery

log = logging.getLogger(__name__)

_SAFE_ERROR = "پردازش صوت ناموفق بود. لطفاً دوباره تلاش کنید."


@celery.task(bind=True, name="nourai.audio.process", max_retries=2)
def process_audio_job(self, job_id: str) -> dict:
    app = get_flask_app()
    with app.app_context():
        from app.api.deps import utcnow

        session = db.session
        job = session.get(GenerationJob, job_id)
        if job is None:
            return {"ok": False, "error": "not_found"}
        if job.status not in ("queued", "processing"):
            log.info("audio job %s already %s; skipping", job_id, job.status)
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
        try:
            transcript, reply_text, output_asset = _run_chain(session, job)
        except Exception:  # noqa: BLE001
            log.exception("audio job %s failed", job_id)
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

        # The job may have been cancelled (admin) while the provider chain
        # was in flight: release the hold instead of settling.
        if aborted_during_processing(session, job):
            return {"ok": False, "error": "CANCELLED"}

        # --- settle on actual consumption ----------------------------------
        duration = int((job.parameters_json or {}).get("duration_seconds") or 0)
        pricing = PricingService(session)
        estimate = pricing.estimate_audio(job.model_id, duration or 1)
        final_amount = estimate["total_irr"]
        if usage is not None:
            usage.audio_seconds = duration
            usage.pricing_snapshot_json = estimate["pricing_snapshots"]
            if quota_covered:
                usage.charged_amount_irr = 0
                usage.status = "succeeded"
            else:
                settle_job_billing(session, job=job, usage=usage, final_amount_irr=final_amount)

        job.status = JOB_SUCCEEDED
        job.result_text = reply_text
        job.prompt_text = transcript
        job.finished_at = utcnow()
        minutes = max(1, math.ceil(duration / 60))
        PlanLimitService(session).increment(job.user_id, "audio", amount=minutes)
        session.commit()
        log.info("audio job %s succeeded transcript=%d chars", job_id, len(transcript))
        return {"ok": True, "asset_id": output_asset.id if output_asset else None}


def _run_chain(session, job: GenerationJob) -> tuple[str, str, Asset | None]:
    params = job.parameters_json or {}
    duration = int(params.get("duration_seconds") or 0)

    input_asset = (
        session.query(Asset).filter_by(id=params.get("input_asset_id"), kind=ASSET_INPUT_AUDIO).one()
    )

    stt_model = session.get(AiModel, params.get("stt_model_id") or job.model_id)

    # 1. speech -> text
    stt = get_stt_provider(stt_model.provider_key if stt_model else None, stt_model)
    transcript_res = stt.transcribe(
        stt_model.provider_model_name if stt_model else "default",
        input_asset.storage_key,
        {"duration_seconds": duration, "mime_type": input_asset.mime_type,
         "language": params.get("language") or "fa"},
    )
    if not transcript_res.ok:
        raise RuntimeError(transcript_res.error_code or "stt failed")
    transcript = transcript_res.text

    if (params.get("mode") or "assistant") == "transcribe":
        # Transcribe-only: skip the text-reply and TTS legs entirely.
        return transcript, "", None

    text_model = session.get(AiModel, params.get("text_model_id"))
    tts_model = session.get(AiModel, params.get("tts_model_id") or job.model_id)

    # 2. text -> reply
    if text_model is None:
        text_model = (
            session.query(AiModel)
            .filter_by(capability=CAP_TEXT, is_active=True)
            .order_by(AiModel.created_at)
            .first()
        )
    if text_model is None:
        raise RuntimeError("no active text model")
    messages = [
        {"role": "system", "content": "You are Nourai (نورا), a helpful Persian AI assistant."},
        {"role": "user", "content": transcript},
    ]
    text_provider = get_text_provider(text_model.provider_key, text_model)
    text_res = text_provider.generate(text_model.provider_model_name, messages, {})
    if not text_res.ok:
        raise RuntimeError(text_res.error_code or "text generation failed")
    reply_text = text_res.text

    # Token accounting for the text leg (tiktoken; provider usage wins when valid).
    if text_model.tokenizer_encoding:
        counter = TokenCounter(text_model.tokenizer_encoding)
        overhead = getattr(text_provider, "OVERHEAD_PER_MESSAGE", 0)
        input_tokens = counter.count_chat_messages(messages, overhead_per_message=overhead)
        output_tokens = counter.count_text(reply_text)
    else:
        input_tokens = output_tokens = None

    # 3. reply -> speech
    tts = get_tts_provider(tts_model.provider_key if tts_model else None, tts_model)
    audio_res = tts.synthesize(
        tts_model.provider_model_name if tts_model else "default", reply_text, {"voice": None}
    )
    if not audio_res.ok or not audio_res.audio_bytes:
        raise RuntimeError(audio_res.error_code or "tts failed")

    key = asset_key(job.user_id, ASSET_OUTPUT_AUDIO, "mp3")
    storage.put_bytes(key, audio_res.audio_bytes, audio_res.mime_type)
    output_asset = Asset(
        user_id=job.user_id,
        job_id=job.id,
        kind=ASSET_OUTPUT_AUDIO,
        storage_key=key,
        mime_type=audio_res.mime_type,
        size_bytes=len(audio_res.audio_bytes),
        sha256=hashlib.sha256(audio_res.audio_bytes).hexdigest(),
        duration_seconds=audio_res.duration_seconds,
        processing_metadata_json={
            "transcript_chars": len(transcript),
            "reply_chars": len(reply_text),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "token_count_source": "tiktoken" if input_tokens is not None else None,
        },
    )
    session.add(output_asset)
    session.flush()
    return transcript, reply_text, output_asset
