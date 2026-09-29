"""Repro: PUT /admin/settings/image-processing/<id> -> INTERNAL_ERROR."""
from __future__ import annotations

from app.extensions import db
from app.models import ImageProcessingProfile
from tests.conftest import admin_headers


def _make_profile(app):
    with app.app_context():
        p = ImageProcessingProfile(
            name="test", model_id=None, max_upload_bytes=8388608,
            max_input_pixels=12582912, allowed_mime_types_json=["image/jpeg"],
            target_width=1024, target_height=1024, resize_mode="fit",
            allow_upscale=False, output_format="jpeg", output_quality=85,
            strip_metadata=True, is_active=True, version=1,
        )
        db.session.add(p)
        db.session.commit()
        return p.id


def test_update_image_profile_no_500(client, app, admin):
    pid = _make_profile(app)
    headers = admin_headers(client, admin)
    resp = client.put(
        f"/api/v1/admin/settings/image-processing/{pid}",
        json={
            "name": "test", "max_upload_bytes": 5242880,
            "max_input_pixels": 12582912,
            "allowed_mime_types": ["image/jpeg", "image/png", "image/webp"],
            "target_width": 1024, "target_height": 1024, "resize_mode": "fit",
            "output_format": "jpeg", "output_quality": 85,
            "allow_upscale": False, "is_active": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["max_upload_bytes"] == 5242880
