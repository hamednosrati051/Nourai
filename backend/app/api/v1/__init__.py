"""Versioned API blueprint: /api/v1/*."""
from flask import Blueprint

from app.api.v1 import (
    admin,
    admin_auth,
    assets,
    audio,
    auth,
    bale,
    blog,
    chat,
    gallery,
    image,
    models,
    payments,
    pdf,
    plans,
    site,
    tts,
    usage,
    video,
    vision,
    wallet,
)

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

for module in (
    auth, admin_auth, wallet, payments, plans, models, chat, audio, image, gallery,
    usage, assets, tts, blog, site, admin, bale, vision, video, pdf,
):
    bp.register_blueprint(module.bp)

__all__ = ["bp"]
