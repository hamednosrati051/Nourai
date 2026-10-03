"""Image model resolution picks the capability matching the job mode."""
from __future__ import annotations

from app.api.v1.image import _resolve_image_model
from app.extensions import db
from app.models import AiModel
from app.models.catalog import CAP_EDIT_IMAGE, CAP_GENERATE_IMAGE, CAP_IMAGE
from app.models.jobs import MODE_IMAGE_TO_IMAGE, MODE_TEXT_TO_IMAGE


def _mk(app, slug, capability):
    with app.app_context():
        m = AiModel(
            slug=slug, display_name=slug, capability=capability,
            provider_key="k", provider_model_name="m",
            provider_type="openai_compat", is_active=True, pricing_type="image",
        )
        db.session.add(m)
        db.session.commit()
        return m.id


def test_resolve_image_model_by_mode(app):
    gid = _mk(app, "gen", CAP_GENERATE_IMAGE)
    eid = _mk(app, "edt", CAP_EDIT_IMAGE)
    with app.app_context():
        assert _resolve_image_model(None, MODE_TEXT_TO_IMAGE).id == gid
        assert _resolve_image_model(None, MODE_IMAGE_TO_IMAGE).id == eid
        # Explicit model_id still wins over the mode default.
        assert _resolve_image_model(eid, MODE_TEXT_TO_IMAGE).id == eid
        assert _resolve_image_model(gid, MODE_IMAGE_TO_IMAGE).id == gid


def test_resolve_image_model_legacy_fallback(app):
    lid = _mk(app, "legacy", CAP_IMAGE)
    with app.app_context():
        assert _resolve_image_model(None, MODE_TEXT_TO_IMAGE).id == lid
        assert _resolve_image_model(None, MODE_IMAGE_TO_IMAGE).id == lid
        assert _resolve_image_model(None, None).id == lid


def test_resolve_image_model_none_when_empty(app):
    with app.app_context():
        assert _resolve_image_model(None, MODE_TEXT_TO_IMAGE) is None
        assert _resolve_image_model(None, MODE_IMAGE_TO_IMAGE) is None
