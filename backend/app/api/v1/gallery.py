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
        asset = db.session.get(Asset, item["asset_id"])
        # Stream via backend (same-origin). Presigned URLs point at localhost.
        item["image_url"] = f"/api/v1/assets/{asset.id}/download?stream=1" if asset else None
        del item["asset_id"]
    return success_response(items, {"limit": config.gallery_public_limit})
