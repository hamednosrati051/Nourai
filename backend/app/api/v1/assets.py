"""Private asset download via short-lived signed URLs.

Ownership is always checked: knowing an asset UUID is not enough. Admins
may access any asset through the admin endpoints instead.
"""
from __future__ import annotations

from flask import Blueprint, g

from app.api.deps import error_response, login_required, success_response
from app.config import config
from app.extensions import db
from app.models import Asset
from app.services.storage import storage

bp = Blueprint("assets", __name__)


@bp.get("/assets/<asset_id>/download")
@login_required
def download_asset(asset_id: str):
    from flask import Response
    asset = db.session.get(Asset, asset_id)
    if asset is None:
        return error_response("NOT_FOUND", status=404)
    if asset.user_id != g.current_user_id:
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
