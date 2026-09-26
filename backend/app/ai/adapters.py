"""Deterministic fake AI adapters (development/test doubles).

Real provider credentials and endpoints come from the project owner later;
business code must only depend on the interfaces in providers/base.py.
Fakes are never selected in production (see providers/__init__.py guards).
"""
from __future__ import annotations

import hashlib
import io
import logging
import uuid

from PIL import Image

from app.config import config
from app.providers.base import (
    AudioResult,
    ImageAiProvider,
    ImageResult,
    SpeechToTextProvider,
    TextAiProvider,
    TextResult,
    TextToSpeechProvider,
    TranscriptResult,
)

log = logging.getLogger(__name__)


def _guard_not_production() -> None:
    if config.is_production:
        raise RuntimeError("Fake AI adapters must never be used in production")


class FakeTextProvider(TextAiProvider):
    """Documented chat framing overhead for the fake adapter.

    Real adapters must document their own overhead constants; the
    TokenCounter takes them explicitly and never guesses.
    """

    OVERHEAD_PER_MESSAGE = 4
    OVERHEAD_TOTAL = 2

    def __init__(self):
        _guard_not_production()

    def generate(self, model: str, messages: list[dict], options: dict) -> TextResult:
        last_user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                last_user = content if isinstance(content, str) else str(content)
                break
        digest = hashlib.sha256(last_user.encode()).hexdigest()[:8]
        text = f"[نورا • پاسخ آزمایشی مدل {model}] {last_user[:120]}… (#{digest})"
        return TextResult(
            ok=True,
            text=text,
            provider_request_id=f"fake-txt-{uuid.uuid4().hex[:12]}",
            input_tokens=None,  # caller counts with tiktoken
            output_tokens=None,
            usage_source=None,
        )


class FakeSttProvider(SpeechToTextProvider):
    def __init__(self):
        _guard_not_production()

    def transcribe(self, model: str, audio_key: str, options: dict) -> TranscriptResult:
        return TranscriptResult(
            ok=True,
            text="این یک رونوشت آزمایشی است.",
            provider_request_id=f"fake-stt-{uuid.uuid4().hex[:12]}",
            duration_seconds=int(options.get("duration_seconds") or 5),
        )


class FakeTtsProvider(TextToSpeechProvider):
    def __init__(self):
        _guard_not_production()

    def synthesize(self, model: str, text: str, options: dict) -> AudioResult:
        # Deterministic placeholder payload (not real audio).
        payload = f"FAKE-AUDIO:{hashlib.sha256(text.encode()).hexdigest()[:16]}".encode()
        return AudioResult(
            ok=True,
            audio_bytes=payload,
            mime_type="audio/mpeg",
            provider_request_id=f"fake-tts-{uuid.uuid4().hex[:12]}",
            duration_seconds=max(1, len(text) // 15),
        )


class FakeImageProvider(ImageAiProvider):
    def __init__(self):
        _guard_not_production()

    def _placeholder(self, prompt: str, width: int, height: int) -> ImageResult:
        digest = hashlib.sha256(prompt.encode()).digest()
        color = (digest[0], digest[1], digest[2])
        image = Image.new("RGB", (width, height), color)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=80)
        return ImageResult(
            ok=True,
            image_bytes=buf.getvalue(),
            mime_type="image/jpeg",
            width=width,
            height=height,
            provider_request_id=f"fake-img-{uuid.uuid4().hex[:12]}",
        )

    def generate(self, model: str, prompt: str, options: dict) -> ImageResult:
        width = int(options.get("width") or 1024)
        height = int(options.get("height") or 1024)
        return self._placeholder(prompt, width, height)

    def edit(self, model: str, prompt: str, input_image_key: str, options: dict) -> ImageResult:
        width = int(options.get("width") or 1024)
        height = int(options.get("height") or 1024)
        return self._placeholder(f"edit:{prompt}", width, height)


def get_text_provider() -> TextAiProvider:
    name = (config.ai_text_provider or "fake").lower()
    if name == "fake":
        return FakeTextProvider()
    raise ValueError(f"unknown AI_TEXT_PROVIDER: {name}")


def get_stt_provider() -> SpeechToTextProvider:
    name = (config.ai_audio_provider or "fake").lower()
    if name == "fake":
        return FakeSttProvider()
    raise ValueError(f"unknown AI_AUDIO_PROVIDER: {name}")


def get_tts_provider() -> TextToSpeechProvider:
    name = (config.ai_audio_provider or "fake").lower()
    if name == "fake":
        return FakeTtsProvider()
    raise ValueError(f"unknown AI_AUDIO_PROVIDER: {name}")


def get_image_provider() -> ImageAiProvider:
    name = (config.ai_image_provider or "fake").lower()
    if name == "fake":
        return FakeImageProvider()
    raise ValueError(f"unknown AI_IMAGE_PROVIDER: {name}")
