"""Audio job transcribe mode: STT-only jobs skip the text-reply and TTS legs."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.v1.audio import AudioJobSchema, _job_payload
from app.extensions import db
from app.models import Asset, GenerationJob
from app.models.jobs import ASSET_INPUT_AUDIO, JOB_QUEUED
from app.tasks import audio_tasks


def test_audio_job_schema_mode_defaults_and_validation():
    assert AudioJobSchema().mode == "assistant"
    assert AudioJobSchema(mode="transcribe").mode == "transcribe"
    assert AudioJobSchema(mode="  Transcribe ").mode == "transcribe"
    with pytest.raises(ValidationError):
        AudioJobSchema(mode="bogus")


def test_job_payload_reports_mode(app, user):
    with app.app_context():
        job = GenerationJob(
            user_id=user, capability="audio", status=JOB_QUEUED,
            parameters_json={"input_asset_id": "in-1", "mode": "transcribe"},
        )
        db.session.add(job)
        db.session.commit()
        assert _job_payload(job)["mode"] == "transcribe"

        legacy = GenerationJob(
            user_id=user, capability="audio", status=JOB_QUEUED,
            parameters_json={"input_asset_id": "in-1"},
        )
        db.session.add(legacy)
        db.session.commit()
        assert _job_payload(legacy)["mode"] == "assistant"


def test_run_chain_transcribe_skips_text_and_tts(app, user, monkeypatch):
    with app.app_context():
        job = GenerationJob(
            user_id=user, capability="audio", status=JOB_QUEUED,
            parameters_json={"mode": "transcribe"},
        )
        db.session.add(job)
        db.session.flush()
        asset = Asset(
            user_id=user, job_id=job.id, kind=ASSET_INPUT_AUDIO,
            storage_key="k", mime_type="audio/webm", size_bytes=10, sha256="x",
        )
        db.session.add(asset)
        db.session.flush()
        job.parameters_json = {"mode": "transcribe", "input_asset_id": asset.id}
        db.session.commit()

        stt_calls = []

        class FakeStt:
            def transcribe(self, model_name, storage_key, options):
                stt_calls.append((model_name, storage_key))
                return SimpleNamespace(ok=True, text="سلام نورا")

        def _boom(*args, **kwargs):
            raise AssertionError("this leg must not run in transcribe mode")

        monkeypatch.setattr(audio_tasks, "get_stt_provider", lambda *a: FakeStt())
        monkeypatch.setattr(audio_tasks, "get_text_provider", _boom)
        monkeypatch.setattr(audio_tasks, "get_tts_provider", _boom)

        transcript, reply_text, output_asset = audio_tasks._run_chain(db.session, job)

        assert transcript == "سلام نورا"
        assert reply_text == ""
        assert output_asset is None
        assert stt_calls, "STT provider must run"
