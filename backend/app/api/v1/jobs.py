"""User job cancellation: cancel your own queued job, hold is released."""
from __future__ import annotations

from flask import Blueprint, g

from app.api.deps import (
    client_ip,
    error_response,
    ip_hash,
    login_required,
    success_response,
)
from app.extensions import db
from app.models import GenerationJob
from app.models.jobs import JOB_QUEUED
from app.services.audit import audit
from app.tasks import cancel_job

bp = Blueprint("jobs", __name__)


@bp.post("/jobs/<job_id>/cancel")
@login_required
def cancel_own_job(job_id: str):
    job = db.session.get(GenerationJob, job_id)
    if job is None or job.user_id != g.current_user_id:
        return error_response("NOT_FOUND", status=404)
    # Users may only cancel while the job is still queued; once the worker
    # picked it up, cancellation is an admin operation.
    if job.status != JOB_QUEUED:
        return error_response("JOB_NOT_CANCELLABLE", "این درخواست دیگر قابل لغو نیست.", 409)
    if not cancel_job(db.session, job=job, reason="cancelled by user"):
        return error_response("JOB_NOT_CANCELLABLE", "این درخواست دیگر قابل لغو نیست.", 409)
    db.session.commit()
    audit(db.session, actor_type="user", actor_id=g.current_user_id,
          action="job.cancelled", target_type="job", target_id=job.id,
          metadata={"capability": job.capability}, ip_hash=ip_hash(client_ip()))
    db.session.commit()
    return success_response({"id": job.id, "status": job.status})
