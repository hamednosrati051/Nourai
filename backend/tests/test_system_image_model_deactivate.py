"""Deactivating the system image model must stick.

Regression test: the admin model listing used to force-reactivate the
system image row (``nourai-image``) on every load, making it impossible
to deactivate from the panel. ``ensure_system_image_model`` now only
guarantees the row exists.
"""
from __future__ import annotations

from app.api.v1.image import SYSTEM_IMAGE_MODEL_SLUG, ensure_system_image_model
from app.extensions import db
from app.models import AiModel
from tests.conftest import admin_headers


def test_system_image_model_stays_deactivated(client, app, admin):
    with app.app_context():
        model = ensure_system_image_model()
        model_id = model.id
    headers = admin_headers(client, admin)

    resp = client.patch(
        f"/api/v1/admin/models/{model_id}", json={"is_active": False}, headers=headers
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["is_active"] is False

    # The listing triggers ensure_system_image_model(); it must not revert.
    resp = client.get("/api/v1/admin/models", headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        row = db.session.query(AiModel).filter_by(slug=SYSTEM_IMAGE_MODEL_SLUG).one()
        assert row.is_active is False


def test_system_image_model_still_created_when_missing(client, app, admin):
    with app.app_context():
        db.session.query(AiModel).filter_by(slug=SYSTEM_IMAGE_MODEL_SLUG).delete()
        db.session.commit()
    headers = admin_headers(client, admin)

    resp = client.get("/api/v1/admin/models", headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        row = (
            db.session.query(AiModel).filter_by(slug=SYSTEM_IMAGE_MODEL_SLUG).one_or_none()
        )
        assert row is not None
