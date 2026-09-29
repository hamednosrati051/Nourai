"""Periodic sweeper: fail `processing` jobs stuck longer than the threshold.

A job stuck in `processing` with an old `started_at` means its worker died
without redelivery (with acks_late a redelivered task resets started_at).
Failing it releases the wallet hold; a later redelivery becomes a no-op via
the task's status guard.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from app.api.deps import utcnow
from app.extensions import db
from app.models import GenerationJob, UsageEvent
from app.models.jobs import JOB_FAILED, JOB_PROCESSING
from app.tasks import get_flask_app, release_job_billing
from app.tasks.celery_app import celery

log = logging.getLogger(__name__)

STUCK_PROCESSING_MINUTES = 30


def sweep_stuck_jobs(max_age_minutes: int = STUCK_PROCESSING_MINUTES) -> int:
    cutoff = utcnow() - timedelta(minutes=max_age_minutes)
    jobs = (
        db.session.query(GenerationJob)
        .filter_by(status=JOB_PROCESSING)
        .filter(GenerationJob.started_at < cutoff)
        .all()
    )
    swept = 0
    for job in jobs:
        usage = (
            db.session.query(UsageEvent)
            .filter_by(job_id=job.id)
            .order_by(UsageEvent.created_at.desc())
            .first()
        )
        if usage is not None:
            release_job_billing(
                db.session, job=job, usage=usage, reason="stuck job sweeper"
            )
        job.status = JOB_FAILED
        job.error_code = "STUCK_TIMEOUT"
        job.finished_at = utcnow()
        swept += 1
        log.warning("sweeper failed stuck job %s (%s)", job.id, job.capability)
    db.session.commit()
    return swept


@celery.task(name="nourai.jobs.sweep_stuck")
def sweep_stuck() -> dict:
    app = get_flask_app()
    with app.app_context():
        swept = sweep_stuck_jobs()
    log.info("stuck-job sweep done: %d failed", swept)
    return {"ok": True, "swept": swept}
