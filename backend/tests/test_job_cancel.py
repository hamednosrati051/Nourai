"""Job cancellation: helper, user/admin endpoints, worker re-check, sweeper."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.api.deps import utcnow
from app.billing.ledger import deposit, get_wallet_for_update
from app.extensions import db
from app.models import GenerationJob, UsageEvent, WalletAccount
from app.models.jobs import JOB_CANCELLED, JOB_FAILED, JOB_PROCESSING, JOB_QUEUED, JOB_SUCCEEDED
from app.tasks import aborted_during_processing, cancel_job
from app.tasks.sweep_tasks import sweep_stuck_jobs
from tests.conftest import admin_headers, user_headers


def _job(app, user_id, status=JOB_QUEUED, capability="image"):
    with app.app_context():
        job = GenerationJob(
            user_id=user_id, capability=capability, model_id="m",
            status=status, prompt_text="p",
            started_at=utcnow() if status == JOB_PROCESSING else None,
        )
        db.session.add(job)
        db.session.flush()
        usage = UsageEvent(
            user_id=user_id, job_id=job.id, model_id="m",
            status="processing", estimated_amount_irr=10000,
            reserved_amount_irr=10000,
        )
        db.session.add(usage)
        db.session.commit()
        return job.id


def _fund(app, user_id):
    with app.app_context():
        wallet = get_wallet_for_update(db.session, user_id)
        deposit(session=db.session, wallet=wallet, amount_irr=100000,
                idempotency_key=f"dep-cancel-{user_id}")
        db.session.commit()


def test_cancel_job_releases_hold(app, user):
    _fund(app, user)
    job_id = _job(app, user, JOB_QUEUED)
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        assert cancel_job(db.session, job=job, reason="t") is True
        db.session.commit()
        assert job.status == JOB_CANCELLED
        usage = db.session.query(UsageEvent).filter_by(job_id=job_id).one()
        assert usage.charged_amount_irr == 0


def test_cancel_job_terminal_is_noop(app, user):
    job_id = _job(app, user, JOB_SUCCEEDED)
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        assert cancel_job(db.session, job=job, reason="t") is False
        assert job.status == JOB_SUCCEEDED


def test_user_can_cancel_own_queued_job(client, app, user):
    _fund(app, user)
    job_id = _job(app, user, JOB_QUEUED)
    r = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=user_headers(client, user))
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["data"]["status"] == "cancelled"


def test_user_cannot_cancel_processing_job(client, app, user):
    _fund(app, user)
    job_id = _job(app, user, JOB_PROCESSING)
    r = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=user_headers(client, user))
    assert r.status_code == 409


def test_user_cannot_cancel_others_job(client, app, user, admin):
    _fund(app, admin)
    job_id = _job(app, admin, JOB_QUEUED)
    r = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=user_headers(client, user))
    assert r.status_code == 404


def test_admin_can_cancel_processing_job(client, app, user, admin):
    _fund(app, user)
    job_id = _job(app, user, JOB_PROCESSING)
    r = client.post(f"/api/v1/admin/jobs/{job_id}/cancel", headers=admin_headers(client, admin))
    assert r.status_code == 200, r.get_data(as_text=True)


def test_admin_jobs_list(client, app, user, admin):
    queued_id = _job(app, user, JOB_QUEUED)
    _job(app, user, JOB_SUCCEEDED)
    r = client.get("/api/v1/admin/jobs?status=queued", headers=admin_headers(client, admin))
    assert r.status_code == 200
    items = r.get_json()["data"]["items"]
    assert all(i["status"] == "queued" for i in items)
    assert queued_id in {i["id"] for i in items}


def test_aborted_during_processing(app, user):
    _fund(app, user)
    job_id = _job(app, user, JOB_PROCESSING)
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        # Admin cancels mid-flight in another session.
        job.status = JOB_CANCELLED
        db.session.commit()
        assert aborted_during_processing(db.session, job) is True
        usage = db.session.query(UsageEvent).filter_by(job_id=job_id).one()
        assert usage.charged_amount_irr == 0


def test_aborted_not_triggered_when_processing(app, user):
    job_id = _job(app, user, JOB_PROCESSING)
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        assert aborted_during_processing(db.session, job) is False


def test_sweeper_fails_old_processing_jobs(app, user):
    _fund(app, user)
    old_id = _job(app, user, JOB_PROCESSING)
    new_id = _job(app, user, JOB_PROCESSING)
    with app.app_context():
        old = db.session.get(GenerationJob, old_id)
        old.started_at = utcnow() - timedelta(minutes=45)
        db.session.commit()
        swept = sweep_stuck_jobs(max_age_minutes=30)
        assert swept == 1
        assert db.session.get(GenerationJob, old_id).status == JOB_FAILED
        assert db.session.get(GenerationJob, new_id).status == JOB_PROCESSING
        usage = db.session.query(UsageEvent).filter_by(job_id=old_id).one()
        assert usage.charged_amount_irr == 0
