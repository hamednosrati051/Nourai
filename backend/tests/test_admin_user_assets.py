"""Admin user assets: kind filter accepts comma-separated kinds."""
from __future__ import annotations

from app.extensions import db
from app.models import Asset, User
from app.models.jobs import (
    ASSET_GENERATED_IMAGE,
    ASSET_INPUT_IMAGE_ORIGINAL,
    ASSET_INPUT_IMAGE_PROCESSED,
)
from tests.conftest import admin_headers


def _asset(user_id, kind):
    a = Asset(
        user_id=user_id, kind=kind, storage_key=f"k-{kind}",
        mime_type="image/jpeg", size_bytes=10, sha256="0" * 64,
    )
    db.session.add(a)
    return a


def test_user_assets_multi_kind(app, client, admin):
    with app.app_context():
        u = User(mobile_normalized="989120000002", is_active=True)
        db.session.add(u)
        db.session.flush()
        _asset(u.id, ASSET_GENERATED_IMAGE)
        _asset(u.id, ASSET_INPUT_IMAGE_ORIGINAL)
        _asset(u.id, ASSET_INPUT_IMAGE_PROCESSED)
        db.session.commit()
        uid = u.id
    headers = admin_headers(client, admin)
    kinds = f"{ASSET_INPUT_IMAGE_ORIGINAL},{ASSET_INPUT_IMAGE_PROCESSED}"
    resp = client.get(f"/api/v1/admin/users/{uid}/assets?kind={kinds}", headers=headers)
    assert resp.status_code == 200
    got = {i["kind"] for i in resp.get_json()["data"]}
    assert got == {ASSET_INPUT_IMAGE_ORIGINAL, ASSET_INPUT_IMAGE_PROCESSED}


def test_user_assets_invalid_kind(app, client, admin):
    with app.app_context():
        u = User(mobile_normalized="989120000003", is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    headers = admin_headers(client, admin)
    resp = client.get(f"/api/v1/admin/users/{uid}/assets?kind=nope", headers=headers)
    assert resp.status_code in (400, 422)
