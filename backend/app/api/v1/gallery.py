"""Public gallery: at most 20 latest admin-approved images.

No pagination beyond the fixed cap (MVP). Empty array when nothing is
approved — never placeholder images. No mobile numbers, private prompts or
sensitive ids are exposed.
"""
from __future__ import annotations

from flask import Blueprint

from app.api.deps import success_response
from app.config import config
from app.extensions import db
from app.models import Asset
from app.services.gallery import public_gallery
from app.services.storage import storage

bp = Blueprint("gallery", __name__)


@bp.get("/gallery")
def get_gallery():
    items = public_gallery(db.session)
    for item in items:
        try:
            asset = db.session.get(Asset, item["asset_id"])
            item["image_url"] = storage.presigned_get_url(asset.storage_key)
        except Exception:  # noqa: BLE001 - storage down -> omit url
            item["image_url"] = None
        del item["asset_id"]
    return success_response(items, {"limit": config.gallery_public_limit})
