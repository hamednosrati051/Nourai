"""_job_payload contract: chat UI reads transcript/reply_text/asset ids."""
from __future__ import annotations

from app.api.v1.audio import _job_payload
from app.extensions import db
from app.models import Asset, GenerationJob
from app.models.jobs import ASSET_OUTPUT_AUDIO, JOB_QUEUED, JOB_SUCCEEDED


def _make_job(user_id, **kwargs):
    job = GenerationJob(user_id=user_id, capability="audio", **kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_job_payload_chat_contract(app, user):
    with app.app_context():
        job = _make_job(
            user,
            status=JOB_QUEUED,
            prompt_text=None,
            result_text=None,
            parameters_json={"input_asset_id": "in-1"},
        )
        payload = _job_payload(job)
        assert payload["id"] == job.id
        assert payload["status"] == JOB_QUEUED
        assert payload["transcript"] is None
        assert payload["reply_text"] is None
        assert payload["input_asset_id"] == "in-1"
        assert payload["output_asset_id"] is None
        assert "result_text" not in payload


def test_job_payload_succeeded_includes_transcript_and_output_asset(app, user):
    with app.app_context():
        job = _make_job(
            user,
            status=JOB_SUCCEEDED,
            prompt_text="سلام نورا",
            result_text="سلام! چطور کمکت کنم؟",
            parameters_json={"input_asset_id": "in-1"},
        )
        asset = Asset(
            user_id=user,
            job_id=job.id,
            kind=ASSET_OUTPUT_AUDIO,
            storage_key="k",
            mime_type="audio/mpeg",
            size_bytes=10,
            sha256="x",
        )
        db.session.add(asset)
        db.session.commit()

        payload = _job_payload(job)
        assert payload["transcript"] == "سلام نورا"
        assert payload["reply_text"] == "سلام! چطور کمکت کنم؟"
        assert payload["output_asset_id"] == asset.id
