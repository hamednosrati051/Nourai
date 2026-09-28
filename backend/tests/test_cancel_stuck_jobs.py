"""cancel-stuck-jobs CLI: stuck queued jobs become cancelled, reserves released."""
from __future__ import annotations

from app.extensions import db
from app.models import GenerationJob, UsageEvent, User
from app.models.jobs import JOB_CANCELLED, JOB_QUEUED
from app.models.wallet import WalletAccount


def _make_job(app, status):
    with app.app_context():
        user = User(id="u" * 36, mobile_normalized="09000000000")
        db.session.add(user)
        db.session.add(WalletAccount(user_id=user.id, balance_irr=1_000_000))
        job = GenerationJob(user_id=user.id, capability="image", status=status)
        db.session.add(job)
        db.session.flush()
        usage = UsageEvent(user_id=user.id, job_id=job.id,
                           reserved_amount_irr=420_000, status="reserved")
        db.session.add(usage)
        db.session.commit()
        return job.id


def test_cancel_stuck_jobs(app):
    job_id = _make_job(app, JOB_QUEUED)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["cancel-stuck-jobs"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        assert job.status == JOB_CANCELLED
        usage = db.session.query(UsageEvent).filter_by(job_id=job_id).one()
        assert usage.status == "failed"
        assert usage.charged_amount_irr == 0


def test_cancel_stuck_jobs_nothing_queued(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["cancel-stuck-jobs"])
    assert result.exit_code == 0
    assert "nothing to do" in result.output
