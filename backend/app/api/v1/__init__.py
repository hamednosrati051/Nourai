"""Versioned API blueprint: /api/v1/*."""
from flask import Blueprint

from app.api.v1 import (
    admin,
    admin_auth,
    assets,
    audio,
    auth,
    chat,
    gallery,
    image,
    models,
    payments,
    plans,
    tts,
    usage,
    wallet,
)

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

for module in (
    auth, admin_auth, wallet, payments, plans, models, chat, audio, image, gallery,
    usage, assets, tts, admin,
):
    bp.register_blueprint(module.bp)

__all__ = ["bp"]
