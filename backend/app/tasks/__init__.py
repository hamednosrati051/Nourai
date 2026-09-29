"""Celery tasks package: shared billing finalisation + job workers."""
from __future__ import annotations

import logging

from app.billing import ledger
from app.models import GenerationJob, UsageEvent

log = logging.getLogger(__name__)

_flask_app = None


def get_flask_app():
    """Lazily build (and cache) the Flask app for worker processes.

    Deferred import avoids a circular import: app/__init__ imports the task
    modules, so tasks must not import app at module level.
    """
    global _flask_app
    if _flask_app is None:
        from app import create_app

        _flask_app = create_app()
    return _flask_app


def settle_job_billing(session, *, job: GenerationJob, usage: UsageEvent, final_amount_irr: int) -> None:
    """Convert the job's reserve into the final charge (idempotent)."""
    wallet = ledger.get_wallet_for_update(session, job.user_id)
    try:
        ledger.settle(
            session,
            wallet=wallet,
            reserved_amount_irr=usage.reserved_amount_irr or 0,
            final_amount_irr=final_amount_irr,
            idempotency_key=f"job:{job.id}:settle",
            reference_type="usage_event",
            reference_id=usage.id,
            description=f"settle {job.capability} job",
        )
    except ledger.DuplicateIdempotencyKey:
        log.info("job %s already settled; skipping duplicate", job.id)
    usage.charged_amount_irr = final_amount_irr
    usage.status = "succeeded"


def release_job_billing(session, *, job: GenerationJob, usage: UsageEvent, reason: str) -> None:
    """Free the job's reserve after a failure (idempotent, no charge)."""
    wallet = ledger.get_wallet_for_update(session, job.user_id)
    try:
        ledger.release(
            session,
            wallet=wallet,
            reserved_amount_irr=usage.reserved_amount_irr or 0,
            idempotency_key=f"job:{job.id}:release",
            reference_type="usage_event",
            reference_id=usage.id,
            description=f"release {job.capability} job: {reason}",
        )
    except ledger.DuplicateIdempotencyKey:
        log.info("job %s reserve already released; skipping duplicate", job.id)
    usage.charged_amount_irr = 0
    usage.status = "failed"


def cancel_job(session, *, job: GenerationJob, reason: str) -> bool:
    """Cancel a queued/processing job and release its wallet hold.

    Returns True when the job was cancelled, False when it was already
    terminal (succeeded/failed/cancelled). Safe to call on redelivered
    worker tasks: the status guard at task start turns them into no-ops.
    """
    from app.api.deps import utcnow
    from app.models.jobs import JOB_CANCELLED, JOB_PROCESSING, JOB_QUEUED

    if job.status not in (JOB_QUEUED, JOB_PROCESSING):
        return False
    usage = (
        session.query(UsageEvent)
        .filter_by(job_id=job.id)
        .order_by(UsageEvent.created_at.desc())
        .first()
    )
    if usage is not None:
        release_job_billing(session, job=job, usage=usage, reason=reason)
    job.status = JOB_CANCELLED
    job.error_code = "CANCELLED"
    job.finished_at = utcnow()
    log.info("job %s cancelled (%s)", job.id, reason)
    return True


def aborted_during_processing(session, job: GenerationJob) -> bool:
    """Re-read the job row after a provider call: True if it left the
    processing state meanwhile (e.g. cancelled by an admin mid-flight).

    When aborted, the wallet hold is released instead of settled — the user
    is not charged for a job they cancelled. Any already-created output
    asset is left orphaned (the provider cost was already incurred).
    """
    from app.models.jobs import JOB_PROCESSING

    session.refresh(job)
    if job.status == JOB_PROCESSING:
        return False
    usage = (
        session.query(UsageEvent)
        .filter_by(job_id=job.id)
        .order_by(UsageEvent.created_at.desc())
        .first()
    )
    if usage is not None:
        release_job_billing(
            session, job=job, usage=usage, reason="cancelled during processing"
        )
    session.commit()
    log.info("job %s aborted during processing (now %s); hold released",
             job.id, job.status)
    return True


from app.tasks import audio_tasks, image_tasks, sweep_tasks, tts_tasks  # noqa: E402,F401

__all__ = ["audio_tasks", "image_tasks", "sweep_tasks", "tts_tasks", "get_flask_app", "settle_job_billing", "release_job_billing", "cancel_job", "aborted_during_processing"]
