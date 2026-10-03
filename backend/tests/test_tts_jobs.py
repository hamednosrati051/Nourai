"""Standalone TTS endpoints: POST /tts/jobs, GET list/detail, synthesis task."""
from __future__ import annotations

from unittest.mock import patch

from decimal import Decimal

from app.extensions import db
from app.models import AiModel, GenerationJob, ModelPricingRule, WalletAccount
from app.models.catalog import CAP_TTS
from app.models.jobs import JOB_QUEUED
from app.tasks.tts_tasks import _run_synthesis
from tests.conftest import user_headers


def _make_tts_setup(app, user_id, tariff_usd="0.0018797"):
    with app.app_context():
        m = AiModel(
            slug="tts-test", display_name="TTS Test", capability=CAP_TTS,
            provider_key="test-tts", provider_model_name="test-voice",
            provider_type="fake", is_active=True, pricing_type="fixed",
        )
        db.session.add(m)
        db.session.flush()
        rule = ModelPricingRule(
            model_id=m.id, version=1, billing_unit="fixed_request",
            unit_size=1, unit_price_usd=Decimal(tariff_usd), rounding_mode="up",
            is_active=True,
        )
        db.session.add(rule)
        wallet = WalletAccount(user_id=user_id, currency="IRR", balance_irr=100000, version=0)
        db.session.add(wallet)
        db.session.commit()
        return m.id


def _post(client, headers, payload):
    return client.post(
        "/api/v1/tts/jobs", json=payload,
        headers={**headers, "Idempotency-Key": "test-key-1"},
    )


def test_create_tts_job_happy_path(client, app, user):
    _make_tts_setup(app, user)
    headers = user_headers(client, user)
    with patch("app.tasks.tts_tasks.process_tts_job") as task:
        resp = _post(client, headers, {"text": "سلام دنیا"})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["status"] == "queued"
    assert data["text"] == "سلام دنیا"
    assert data["output_asset_id"] is None
    task.delay.assert_called_once_with(data["id"])


def test_create_tts_job_validation(client, app, user):
    _make_tts_setup(app, user)
    headers = user_headers(client, user)
    with patch("app.tasks.tts_tasks.process_tts_job"):
        assert _post(client, headers, {"text": "   "}).status_code == 422
        assert _post(client, headers, {"text": "x" * 2001}).status_code == 422


def test_create_tts_job_no_model(client, app, user):
    headers = user_headers(client, user)
    resp = _post(client, headers, {"text": "سلام"})
    assert resp.status_code == 404


def test_create_tts_job_insufficient_balance(client, app, user):
    _make_tts_setup(app, user)
    with app.app_context():
        wallet = db.session.query(WalletAccount).filter_by(user_id=user).one()
        wallet.balance_irr = 0
        db.session.commit()
    headers = user_headers(client, user)
    with patch("app.tasks.tts_tasks.process_tts_job"):
        assert _post(client, headers, {"text": "سلام"}).status_code == 402


def test_tts_job_list_and_detail(client, app, user):
    _make_tts_setup(app, user)
    headers = user_headers(client, user)
    with patch("app.tasks.tts_tasks.process_tts_job"):
        created = _post(client, headers, {"text": "سلام"}).get_json()["data"]
    job_id = created["id"]

    detail = client.get(f"/api/v1/tts/jobs/{job_id}", headers=headers).get_json()["data"]
    assert detail["id"] == job_id
    assert detail["text"] == "سلام"

    listing = client.get("/api/v1/tts/jobs", headers=headers).get_json()["data"]
    assert listing["meta"]["total_items"] == 1
    assert listing["items"][0]["id"] == job_id

    assert client.get("/api/v1/tts/jobs/does-not-exist", headers=headers).status_code == 404


def test_run_synthesis_stores_output_asset(app, user):
    _make_tts_setup(app, user)
    with app.app_context():
        model = db.session.query(AiModel).filter_by(capability=CAP_TTS).one()
        job = GenerationJob(
            user_id=user, capability=CAP_TTS, model_id=model.id,
            status=JOB_QUEUED, prompt_text="سلام",
            parameters_json={"tts_model_id": model.id},
        )
        db.session.add(job)
        db.session.commit()
        with patch("app.tasks.tts_tasks.storage") as storage:
            asset = _run_synthesis(db.session, job)
        storage.put_bytes.assert_called_once()
        assert asset.kind == "output_audio"
        assert asset.job_id == job.id
        assert asset.size_bytes > 0
