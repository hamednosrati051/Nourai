"""Public site info: contact page data."""
from __future__ import annotations

from flask import Blueprint

from app.api.deps import success_response
from app.models import SiteSettings
from app.extensions import db

bp = Blueprint("site", __name__)


def _get_settings() -> SiteSettings:
    settings = db.session.query(SiteSettings).first()
    if settings is None:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.flush()
    return settings


@bp.get("/site/contact")
def get_contact():
    """Public contact info for the contact page."""
    return success_response(_get_settings().to_dict())
