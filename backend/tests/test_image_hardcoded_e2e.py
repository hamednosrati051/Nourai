"""End-to-end: hardcoded image pipeline, mirroring Hamed's panel flow.

1. Admin opens models  -> system image row exists AND is persisted (not
   rolled back by the read-only listing).
2. Admin defines the image tariff (pricing rule) -> 201
   (regression: used to 404 with "مدل یافت نشد").
3. Admin "edits" the tariff -> new rule version wins the estimate.
4. Admin edits the system model row -> 200.
5. Creating an image model from the form -> 422.
6. User creates an image job -> 201 (wallet reserve).
7. Worker processes the job (stubbed provider) -> succeeded + settled.
"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.billing.ledger import deposit, get_wallet_for_update
from app.extensions import db
from app.models import AiModel, GenerationJob, WalletAccount, Asset
from app.providers.base import ImageResult
from tests.conftest import admin_headers, user_headers

SYSTEM_SLUG = "nourai-image"


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


def test_hamed_panel_flow(app, client, admin, user, monkeypatch):
    aheaders = admin_headers(client, admin)
    uheaders = user_headers(client, user)

    # 1. Admin opens the model list: the system row must exist AND be
    #    committed (the listing endpoint itself never commits).
    r = client.get("/api/v1/admin/models", headers=aheaders)
    assert r.status_code == 200
    rows = [m for m in r.get_json()["data"] if m["slug"] == SYSTEM_SLUG]
    assert rows, "system image row missing from admin listing"
    system_id = rows[0]["id"]
    db.session.remove()  # fresh session, like a later request would have
    assert db.session.get(AiModel, system_id) is not None

    # 2. Admin defines the image tariff (was 404 "مدل یافت نشد").
    r = client.post(
        "/api/v1/admin/pricing-rules",
        headers=aheaders,
        json={"model_id": system_id, "billing_unit": "image_count",
              "unit_size": 1, "unit_price_irr": 420000},
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    # 3. Admin "edits" the tariff -> new version wins the estimate.
    r = client.post(
        "/api/v1/admin/pricing-rules",
        headers=aheaders,
        json={"model_id": system_id, "billing_unit": "image_count",
              "unit_size": 1, "unit_price_irr": 400000},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    r = client.post(
        "/api/v1/admin/pricing/estimate",
        headers=aheaders,
        json={"model_id": system_id, "kind": "image", "image_count": 1},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["data"]["total_irr"] == 400000

    # 4. Admin edits the system model row itself.
    r = client.patch(
        f"/api/v1/admin/models/{system_id}", headers=aheaders,
        json={"display_name": "تولید تصویر (سیستمی)"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    db.session.remove()
    assert db.session.get(AiModel, system_id).display_name == "تولید تصویر (سیستمی)"

    # 5. Creating an image model from the form is rejected.
    r = client.post(
        "/api/v1/admin/models",
        headers=aheaders,
        json={"display_name": "x", "capability": "image",
              "provider_type": "async_generation",
              "provider_model_name": "m", "base_url": "https://x",
              "api_key": "k"},
    )
    assert r.status_code == 422

    # 6. Fund the wallet; user creates an image job.
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

    # 7. Worker runs the job with the stubbed provider: succeeded + settled.
    monkeypatch.setattr(
        "app.tasks.image_tasks.get_hardcoded_image_provider",
        lambda: _StubImageProvider(),
    )
    from app.tasks.image_tasks import process_image_job

    # In production the worker shares MySQL; in tests, point the task at the
    # test app's in-memory SQLite instead of a fresh (empty) app.
    monkeypatch.setattr(
        "app.tasks.image_tasks.get_flask_app", lambda: app
    )
    # Object storage (S3/MinIO) is not available in tests; the task would
    # fail on upload, which is unrelated to what this test covers.
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
        storage_key = asset.storage_key

    # 8. The user panel poll (GET /image/jobs/<id>) must return the frontend
    #    contract — most importantly result_url, without which the panel
    #    shows "no result" even for succeeded jobs.
    #
    # NOTE: the test-suite app fixture keeps one app context (and therefore
    # one db.session) alive across requests, so the session still holds the
    # pre-worker snapshot of the job. expire_all() simulates what a real
    # request (fresh session) would see.
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
    assert data["result_url"] == f"https://cdn.test/{storage_key}"
    assert data["result_width"] == 1024
    assert data["result_height"] == 1024
