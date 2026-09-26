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


from app.tasks import audio_tasks, image_tasks  # noqa: E402,F401

__all__ = ["audio_tasks", "image_tasks", "get_flask_app", "settle_job_billing", "release_job_billing"]
