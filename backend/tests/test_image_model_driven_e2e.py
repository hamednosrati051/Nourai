"""End-to-end: model-driven image pipeline, mirroring Hamed's panel flow.

1. Admin creates an image model from the form (Metis-style async_generation).
2. Admin defines the image tariff on that model.
3. User creates an image job (no model_id -> active image model).
4. Worker processes the job (stubbed provider) -> succeeded + settled.
5. The user panel poll (GET /image/jobs/<id>) returns the frontend contract.
"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.billing.ledger import deposit, get_wallet_for_update
from app.extensions import db
from app.models import GenerationJob, WalletAccount, Asset
from app.providers.base import ImageResult
from tests.conftest import admin_headers, user_headers


def _png_bytes() -> bytes:
    img = PILImage.new("RGB", (8, 8), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _StubImageProvider:
    def generate(self, model, prompt, options=None, **kwargs):
        return ImageResult(
            ok=True, image_bytes=_png_bytes(), mime_type="image/png",
            width=1024, height=1024, provider_request_id="stub-1",
        )

    def edit(self, model, image_bytes, prompt, options=None, **kwargs):
        return self.generate(model, prompt, options, **kwargs)


def test_model_driven_image_flow(app, client, admin, user, monkeypatch):
    aheaders = admin_headers(client, admin)
    uheaders = user_headers(client, user)

    # 1. Admin creates an image model from the form.
    r = client.post(
        "/api/v1/admin/models",
        headers=aheaders,
        json={"display_name": "Metis", "capability": "image",
              "provider_type": "async_generation",
              "provider_model_name": "google/nano-banana-2",
              "base_url": "https://platform-api.metisai.ir",
              "api_key": "k"},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    model_id = r.get_json()["data"]["id"]

    # 2. Admin defines the tariff on the new model.
    r = client.post(
        "/api/v1/admin/pricing-rules",
        headers=aheaders,
        json={"model_id": model_id, "billing_unit": "image_count",
              "unit_size": 1, "unit_price_irr": 400000},
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    # 3. Fund the wallet; user creates an image job (active model fallback).
    with app.app_context():
        wallet = get_wallet_for_update(db.session, user)
        assert isinstance(wallet, WalletAccount)
        deposit(session=db.session, wallet=wallet, amount_irr=1_000_000,
                idempotency_key="test-dep-image-1")
        db.session.commit()
    monkeypatch.setattr(
        "app.tasks.image_tasks.process_image_job.delay", lambda *a, **k: None
    )
    r = client.post(
        "/api/v1/image/jobs",
        headers={**uheaders, "Idempotency-Key": "job-1"},
        json={"prompt": "یک گربه روی فرش ایرانی"},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    job_id = r.get_json()["data"]["id"]
    assert r.get_json()["data"]["model_id"] == model_id

    # 4. Worker runs the job with the stubbed provider: succeeded + settled.
    monkeypatch.setattr(
        "app.tasks.image_tasks.get_image_provider",
        lambda *a, **k: _StubImageProvider(),
    )
    from app.tasks.image_tasks import process_image_job

    monkeypatch.setattr(
        "app.tasks.image_tasks.get_flask_app", lambda: app
    )
    monkeypatch.setattr(
        "app.tasks.image_tasks.storage.put_bytes", lambda *a, **k: None
    )
    result = process_image_job.apply(args=(job_id,))
    assert result.get()["ok"] is True
    with app.app_context():
        job = db.session.get(GenerationJob, job_id)
        assert job.status == "succeeded"
        asset = (
            db.session.query(Asset)
            .filter_by(job_id=job_id, kind="generated_image")
            .one_or_none()
        )
        assert asset is not None
        assert asset.size_bytes > 0

    # 5. The user panel poll must return the frontend contract.
    db.session.expire_all()
    import types as _types
    monkeypatch.setattr(
        "app.api.v1.image.storage",
        _types.SimpleNamespace(
            presigned_get_url=lambda key: f"https://cdn.test/{key}"
        ),
    )
    r = client.get(f"/api/v1/image/jobs/{job_id}", headers=uheaders)
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json()["data"]
    assert data["status"] == "succeeded"
    assert data["type"] == "text_to_image"
    assert data["prompt"] == "یک گربه روی فرش ایرانی"
    assert data["result_url"] == f"https://cdn.test/{asset.storage_key}"
