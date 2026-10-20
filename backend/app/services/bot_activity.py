"""Best-effort activity recording for the Bale bots.

Everything here is strictly additive and failure-isolated: recording what a
bot user did must NEVER break the bot's reply flow, so every public helper
swallows exceptions (after a rollback) and only logs them. Callers invoke
these helpers right after a ``db.session.commit()`` in the bot handlers
(clean session state), so a rollback here can only discard the recording
itself, never billing or wallet state.

Recorded data lands in the same tables the site uses, so the existing admin
user-detail page shows bot users exactly like site users: conversations in
the chats tab, input/output media in the asset tabs, PDFs in the PDF tab,
and generated images in the gallery moderation queue (pending).
"""
from __future__ import annotations

import hashlib
import io
import logging

from app.extensions import db
from app.models import Asset, Conversation, Message, MessageAsset
from app.models.base import new_uuid
from app.models.gallery import GALLERY_PENDING, GalleryEntry
from app.models.jobs import ASSET_CHAT_INPUT_IMAGE, ASSET_GENERATED_IMAGE
from app.models.pdf_document import PdfDocument
from app.services.storage import asset_key, storage

log = logging.getLogger(__name__)

BOT_TITLES = {
    "main": "ربات بله — گفت‌وگو با نورا",
    "lab": "ربات آزمایش",
    "tts": "ربات متن به صدا",
    "stt": "ربات صدا به متن",
    "pdf": "ربات ساخت PDF",
    "contract": "ربات قرارداد",
}

_IMAGE_KINDS = (ASSET_GENERATED_IMAGE, ASSET_CHAT_INPUT_IMAGE)

_AUDIO_EXT = {
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/aac": "aac",
}


def _sniff_image(data: bytes) -> tuple[str, str]:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return "image/jpeg", "jpg"


def save_bot_asset(
    user_id: str,
    kind: str,
    data: bytes | None,
    mime_type: str | None = None,
    *,
    duration_seconds: int | None = None,
) -> Asset | None:
    """Store raw bytes as a user asset (flushed, not committed).

    The caller's ``record_exchange`` commit persists it. Returns the Asset,
    or None on any failure. Never raises.
    """
    if not data:
        return None
    try:
        width = height = None
        if kind in _IMAGE_KINDS:
            mime_type, ext = _sniff_image(data)
            try:
                from PIL import Image

                with Image.open(io.BytesIO(data)) as im:
                    width, height = im.size
            except Exception:  # noqa: BLE001 - dimensions are best-effort
                pass
        elif (mime_type or "").startswith("audio/"):
            ext = _AUDIO_EXT.get(mime_type or "", "ogg")
        else:
            ext = "bin"
        key = asset_key(user_id, kind, ext)
        storage.put_bytes(key, data, mime_type or "application/octet-stream")
        asset = Asset(
            user_id=user_id,
            kind=kind,
            storage_key=key,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            width=width,
            height=height,
            duration_seconds=duration_seconds,
        )
        db.session.add(asset)
        db.session.flush()
        return asset
    except Exception:  # noqa: BLE001
        log.exception("bot asset save failed (user=%s kind=%s)", user_id, kind)
        db.session.rollback()
        return None


def _queue_gallery(asset: Asset, user_id: str) -> None:
    """Queue a bot-generated image for admin gallery moderation (pending)."""
    if asset.kind != ASSET_GENERATED_IMAGE:
        return
    existing = (
        db.session.query(GalleryEntry).filter_by(asset_id=asset.id).one_or_none()
    )
    if existing is None:
        db.session.add(
            GalleryEntry(asset_id=asset.id, user_id=user_id, status=GALLERY_PENDING)
        )


def _get_or_create_conversation(user_id: str, bot: str, model_id: str | None):
    source = f"bale_{bot}"
    conv = (
        db.session.query(Conversation)
        .filter_by(user_id=user_id, source=source)
        .order_by(Conversation.created_at.desc())
        .first()
    )
    if conv is None:
        conv = Conversation(
            user_id=user_id,
            title=BOT_TITLES.get(bot, "ربات بله"),
            source=source,
            model_id=model_id,
        )
        db.session.add(conv)
        db.session.flush()
    elif model_id and conv.model_id != model_id:
        conv.model_id = model_id
    return conv


def record_exchange(
    user_id: str,
    bot: str,
    *,
    user_text: str | None = None,
    assistant_text: str | None = None,
    user_asset: Asset | None = None,
    assistant_asset: Asset | None = None,
    model_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    """Append one bot exchange to the user's per-bot conversation.

    Commits on success; on any failure rolls back and only logs. Never raises.
    """
    if (
        user_text is None
        and assistant_text is None
        and user_asset is None
        and assistant_asset is None
    ):
        return
    try:
        conv = _get_or_create_conversation(user_id, bot, model_id)
        if user_text is not None or user_asset is not None:
            msg = Message(
                conversation_id=conv.id,
                role="user",
                content_text=user_text,
                input_asset_id=user_asset.id if user_asset else None,
            )
            db.session.add(msg)
            db.session.flush()
            if user_asset is not None:
                db.session.add(
                    MessageAsset(message_id=msg.id, asset_id=user_asset.id, role="input")
                )
        if assistant_text is not None or assistant_asset is not None:
            msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content_text=assistant_text,
                output_asset_id=assistant_asset.id if assistant_asset else None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            db.session.add(msg)
            db.session.flush()
            if assistant_asset is not None:
                db.session.add(
                    MessageAsset(
                        message_id=msg.id, asset_id=assistant_asset.id, role="output"
                    )
                )
                _queue_gallery(assistant_asset, user_id)
        db.session.commit()
    except Exception:  # noqa: BLE001
        log.exception("bot exchange record failed (user=%s bot=%s)", user_id, bot)
        db.session.rollback()


def record_bot_pdf(user_id: str, title: str, pdf_bytes: bytes | None) -> None:
    """Store a bot-generated PDF in the user's PDF history. Never raises."""
    if not pdf_bytes:
        return
    try:
        key = asset_key(user_id, "pdf", "pdf")
        storage.put_bytes(key, pdf_bytes, "application/pdf")
        db.session.add(
            PdfDocument(
                id=new_uuid(),
                user_id=user_id,
                title=(title or "سند PDF")[:255],
                storage_key=key,
            )
        )
        db.session.commit()
    except Exception:  # noqa: BLE001
        log.exception("bot pdf record failed (user=%s)", user_id)
        db.session.rollback()
