"""Secure image validation + processing pipeline.

- Real MIME is sniffed from decoded content (Pillow), never from the extension.
- Hard security ceilings come from the environment; the admin profile can
  only tighten them, never exceed them.
- Decompression-bomb guard: Pillow's MAX_IMAGE_PIXELS plus our own
  dimension/pixel checks *before* the full decode where possible.
- EXIF/GPS metadata is stripped; orientation is fixed before resize.
- Resize modes: fit / fill / stretch to the admin's target dimensions.
- Upscaling is forbidden unless the profile explicitly allows it.
"""
from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field

from PIL import Image, ImageOps

from app.config import config
from app.models.settings import RESIZE_FILL, RESIZE_FIT, RESIZE_MODES, RESIZE_STRETCH

log = logging.getLogger(__name__)

# Pillow aborts (raises DecompressionBombError) above this pixel count.
Image.MAX_IMAGE_PIXELS = config.image_input_hard_max_pixels

_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class ImageValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class HardCeilings:
    max_bytes: int = config.image_upload_hard_max_bytes
    max_pixels: int = config.image_input_hard_max_pixels
    max_width: int = config.image_input_hard_max_width
    max_height: int = config.image_input_hard_max_height


@dataclass
class ProcessedImage:
    data: bytes
    mime_type: str
    width: int
    height: int
    sha256: str
    size_bytes: int
    metadata: dict = field(default_factory=dict)


def _profile_value(profile: dict, key: str, default=None):
    return profile.get(key, default)


def validate_and_process(image_bytes: bytes, profile: dict, hard: HardCeilings | None = None) -> ProcessedImage:
    """Validate an uploaded image and produce the provider-ready derivative.

    ``profile`` is the snapshotted dict from ImageProcessingProfile.snapshot().
    Raises ImageValidationError with an API error code on any problem.
    """
    hard = hard or HardCeilings()

    if not image_bytes:
        raise ImageValidationError("VALIDATION_ERROR", "empty file")
    if len(image_bytes) > hard.max_bytes:
        raise ImageValidationError("FILE_TOO_LARGE", "file exceeds hard byte ceiling")
    max_upload = _profile_value(profile, "max_upload_bytes", hard.max_bytes)
    if max_upload > hard.max_bytes:
        max_upload = hard.max_bytes  # profile can never exceed the hard ceiling
    if len(image_bytes) > max_upload:
        raise ImageValidationError("FILE_TOO_LARGE", "file exceeds profile upload limit")

    # --- decode (real content sniffing) -----------------------------------
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            fmt = probe.format
            width, height = probe.size
    except Image.DecompressionBombError as exc:
        raise ImageValidationError("IMAGE_DIMENSIONS_EXCEEDED", "image too large") from exc
    except Exception as exc:  # noqa: BLE001 - not a decodable image
        raise ImageValidationError("UNSUPPORTED_IMAGE_TYPE", "undecodable image") from exc

    mime = _MIME_BY_FORMAT.get(fmt or "")
    if not mime:
        raise ImageValidationError("UNSUPPORTED_IMAGE_TYPE", f"unsupported format: {fmt}")
    allowed = _profile_value(profile, "allowed_mime_types", []) or []
    if allowed and mime not in allowed:
        raise ImageValidationError("UNSUPPORTED_IMAGE_TYPE", f"mime not allowed: {mime}")

    pixels = width * height
    max_pixels = min(_profile_value(profile, "max_input_pixels", hard.max_pixels), hard.max_pixels)
    if pixels > max_pixels:
        raise ImageValidationError("IMAGE_DIMENSIONS_EXCEEDED", "pixel count exceeds limit")
    if width > hard.max_width or height > hard.max_height:
        raise ImageValidationError("IMAGE_DIMENSIONS_EXCEEDED", "dimensions exceed hard ceiling")

    # --- full decode + orientation fix + metadata strip --------------------
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)  # fix orientation BEFORE resize
        if image.mode in ("RGBA", "LA", "PA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        # Strip metadata: rebuild without info/exif.
        clean = Image.new(image.mode, image.size)
        clean.putdata(list(image.getdata()))
        image = clean
        width, height = image.size
    except ImageValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageValidationError("IMAGE_PROCESSING_FAILED", "decode failed") from exc

    # --- resize ------------------------------------------------------------
    target_w = int(_profile_value(profile, "target_width", width))
    target_h = int(_profile_value(profile, "target_height", height))
    mode = _profile_value(profile, "resize_mode", RESIZE_FIT)
    if mode not in RESIZE_MODES:
        mode = RESIZE_FIT
    allow_upscale = bool(_profile_value(profile, "allow_upscale", False))

    before = (width, height)
    image, (width, height) = _resize(image, target_w, target_h, mode, allow_upscale)

    # --- encode --------------------------------------------------------------
    output_format = (_profile_value(profile, "output_format", "jpeg") or "jpeg").lower()
    quality = int(_profile_value(profile, "output_quality", 85))
    pillow_format = {"jpeg": "JPEG", "jpg": "JPEG", "png": "PNG", "webp": "WEBP"}.get(
        output_format, "JPEG"
    )
    out_mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[pillow_format]

    buf = io.BytesIO()
    save_kwargs: dict = {}
    if out_mime == "JPEG":
        save_kwargs = {"format": "JPEG", "quality": max(1, min(quality, 95)), "optimize": True}
    elif out_mime == "WEBP":
        save_kwargs = {"format": "WEBP", "quality": max(1, min(quality, 100))}
    else:
        save_kwargs = {"format": "PNG", "optimize": True}
    try:
        image.save(buf, **save_kwargs)
    except Exception as exc:  # noqa: BLE001
        raise ImageValidationError("IMAGE_PROCESSING_FAILED", "encode failed") from exc
    data = buf.getvalue()

    digest = hashlib.sha256(data).hexdigest()
    metadata = {
        "before_width": before[0],
        "before_height": before[1],
        "after_width": width,
        "after_height": height,
        "resize_mode": mode,
        "encoder": save_kwargs["format"].lower(),
        "quality": save_kwargs.get("quality"),
        "stripped_metadata": bool(_profile_value(profile, "strip_metadata", True)),
        "source_mime": mime,
    }
    log.info("image processed %dx%d -> %dx%d (%s)", before[0], before[1], width, height, mode)
    return ProcessedImage(
        data=data,
        mime_type=out_mime,
        width=width,
        height=height,
        sha256=digest,
        size_bytes=len(data),
        metadata=metadata,
    )


def _resize(image: Image.Image, target_w: int, target_h: int, mode: str, allow_upscale: bool):
    """Resize per mode; returns (image, (w, h))."""
    src_w, src_h = image.size
    if mode == RESIZE_STRETCH:
        new_w, new_h = target_w, target_h
    else:
        scale_w = target_w / src_w
        scale_h = target_h / src_h
        scale = min(scale_w, scale_h) if mode == RESIZE_FIT else max(scale_w, scale_h)
        if not allow_upscale:
            scale = min(scale, 1.0)
        new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))

    resized = image.resize((new_w, new_h), Image.LANCZOS)

    if mode == RESIZE_FILL:
        # Centre-crop to the exact target box (no upscale unless allowed).
        if not allow_upscale:
            target_w = min(target_w, new_w)
            target_h = min(target_h, new_h)
        left = max(0, (new_w - target_w) // 2)
        top = max(0, (new_h - target_h) // 2)
        resized = resized.crop((left, top, left + target_w, top + target_h))
        new_w, new_h = resized.size

    return resized, (new_w, new_h)


def sniff_mime(image_bytes: bytes) -> str | None:
    """Best-effort MIME sniff for uploads (images and audio)."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            return _MIME_BY_FORMAT.get(probe.format or "")
    except Exception:  # noqa: BLE001
        return None
