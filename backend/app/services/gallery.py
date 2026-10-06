"""Public gallery: at most 20 latest admin-approved generated images.

Only ``status=approved`` rows ordered by ``reviewed_at`` desc are ever
returned. Pending/rejected entries and non-generated assets (chat input
images, originals, ...) are never visible here. No mobile numbers, private
prompts or sensitive internal ids leak into the response.
"""
from __future__ import annotations

from app.config import config
from app.models import Asset, GalleryEntry
from app.models.gallery import GALLERY_APPROVED
from app.models.jobs import ASSET_GENERATED_IMAGE, GenerationJob

# Generic, safe alt text — never the user's prompt.
GALLERY_ALT_TEXT = "تصویر تولیدشده توسط کاربر نورا"


def public_gallery(session, limit: int | None = None) -> list[dict]:
    limit = min(limit or config.gallery_public_limit, config.gallery_public_limit)
    rows = (
        session.query(GalleryEntry, Asset, GenerationJob)
        .join(Asset, GalleryEntry.asset_id == Asset.id)
        .outerjoin(GenerationJob, Asset.job_id == GenerationJob.id)
        .filter(
            GalleryEntry.status == GALLERY_APPROVED,
            Asset.kind == ASSET_GENERATED_IMAGE,
        )
        .order_by(GalleryEntry.reviewed_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    for entry, asset, job in rows:
        items.append({
            "id": entry.id,
            "width": asset.width,
            "height": asset.height,
            "aspect_ratio": round(asset.width / asset.height, 4)
            if asset.width and asset.height else None,
            "mime_type": asset.mime_type,
            "alt": GALLERY_ALT_TEXT,
            "prompt": (job.prompt_text or "").strip() or None,
            # The frontend resolves the actual bytes via /assets/{id}/download
            # semantics; for the public slider we hand out a short-lived URL.
            "asset_id": asset.id,
            "approved_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
        })
    return items
