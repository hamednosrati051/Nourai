"""Succeeded image jobs queue a pending gallery entry (idempotent)."""
from __future__ import annotations

from app.extensions import db
from app.models import Asset, User
from app.models.gallery import GALLERY_PENDING, GalleryEntry
from app.models.jobs import ASSET_GENERATED_IMAGE
from app.tasks.image_tasks import _enqueue_gallery


def _user_and_asset(app):
    with app.app_context():
        u = User(mobile_normalized="989120000001", is_active=True)
        db.session.add(u)
        db.session.flush()
        a = Asset(
            user_id=u.id, kind=ASSET_GENERATED_IMAGE, storage_key="k",
            mime_type="image/jpeg", size_bytes=10, sha256="0" * 64,
        )
        db.session.add(a)
        db.session.commit()
        return u.id, a.id


def test_enqueue_gallery_creates_pending_entry(app):
    user_id, asset_id = _user_and_asset(app)
    with app.app_context():
        asset = db.session.get(Asset, asset_id)
        _enqueue_gallery(db.session, asset, user_id)
        db.session.commit()
        entry = db.session.query(GalleryEntry).filter_by(asset_id=asset_id).one()
        assert entry.status == GALLERY_PENDING
        assert entry.user_id == user_id


def test_enqueue_gallery_idempotent(app):
    user_id, asset_id = _user_and_asset(app)
    with app.app_context():
        asset = db.session.get(Asset, asset_id)
        _enqueue_gallery(db.session, asset, user_id)
        _enqueue_gallery(db.session, asset, user_id)
        db.session.commit()
        count = db.session.query(GalleryEntry).filter_by(asset_id=asset_id).count()
        assert count == 1
