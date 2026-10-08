from __future__ import annotations

from flask import Blueprint, g, request

from app.api.deps import _load_token, error_response, success_response
from app.config import config
from app.extensions import db
from app.models import Asset, GalleryEntry, User
from app.services.storage import storage

bp = Blueprint("assets", __name__)

# Gallery status constant (matches app.services.gallery)
GALLERY_APPROVED = "approved"


def _is_public_gallery_asset(asset_id: str) -> bool:
    """Check if asset is an approved public gallery image."""
    entry = db.session.query(GalleryEntry).filter_by(
        asset_id=asset_id,
        status=GALLERY_APPROVED,
    ).first()
    return entry is not None


@bp.get("/assets/<asset_id>/download")
def download_asset(asset_id: str):
    from flask import Response
    asset = db.session.get(Asset, asset_id)
    if asset is None:
        return error_response("NOT_FOUND", status=404)

    # Public gallery images (approved) are visible to everyone, no login needed.
    if _is_public_gallery_asset(asset_id):
        pass  # public, skip auth
    else:
        # All other assets require authentication and ownership.
        claims, err = _load_token("user")
        if err:
            return err
        user = db.session.get(User, claims["sub"])
        if user is None:
            return error_response("UNAUTHORIZED", status=401)
        if not user.is_active:
            return error_response("USER_DISABLED", status=403)
        if asset.user_id != user.id:
            return error_response("FORBIDDEN", status=403)

    # ?stream=1: stream the file bytes directly (for browser <audio>/<img>
    # tags). Presigned S3 URLs point at localhost and don't work in browsers.
    if request.args.get("stream") == "1":
        try:
            data = storage.get_bytes(asset.storage_key)
        except Exception:  # noqa: BLE001
            return error_response("PROVIDER_ERROR", status=502)
        return Response(data, mimetype=asset.mime_type or "application/octet-stream",
                        headers={"Content-Length": str(len(data)),
                                 "Accept-Ranges": "bytes"})
    try:
        url = storage.presigned_get_url(asset.storage_key)
    except Exception:  # noqa: BLE001
        return error_response("PROVIDER_ERROR", status=502)
    return success_response({
        "download_url": url,
        "expires_in_seconds": config.signed_url_ttl_seconds,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
    })
