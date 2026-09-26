"""Deterministic fake AI adapters (development/test doubles).

Real provider credentials and endpoints come from the project owner later;
business code must only depend on the interfaces in providers/base.py.
Fakes are never selected in production (see providers/__init__.py guards).

The OpenAI-compatible adapter below is provider-agnostic: it serves every
provider (MetisAI, OpenAI, ...) through one HTTP client. Only base_url and
api_key differ, resolved per provider_key from AI_PROVIDER_<KEY>_* env vars.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import urllib.error
import urllib.request
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


class OpenAICompatTextProvider(TextAiProvider):
    """Shared OpenAI-compatible chat client — provider-agnostic.

    Serves every provider (MetisAI, OpenAI, ...) through ``POST
    {base_url}/chat/completions`` with ``Authorization: Bearer <api_key>``.
    The ``model`` sent is the catalog's ``provider_model_name`` verbatim.

    Token overhead for pre-charge estimation follows the OpenAI chat format
    (~4 tokens/message framing, ~2 total priming); the final charge always
    settles on actuals (provider ``usage`` when reported, else tiktoken).
    """

    OVERHEAD_PER_MESSAGE = 4
    OVERHEAD_TOTAL = 2

    def __init__(self, base_url: str, api_key: str, provider_key: str,
                 timeout_seconds: int = 60):
        if not base_url or not api_key:
            raise ValueError("base_url and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_key = provider_key
        self.timeout_seconds = timeout_seconds

    def generate(self, model: str, messages: list[dict], options: dict) -> TextResult:
        url = f"{self.base_url}/chat/completions"
        payload: dict = {
            "model": model,
            "messages": [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages
            ],
        }
        max_output = options.get("max_output_tokens")
        if max_output:
            payload["max_tokens"] = int(max_output)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001
                pass
            log.warning("openai-compat provider %s http %s: %s",
                        self.provider_key, exc.code, detail)
            return TextResult(ok=False, error_code="PROVIDER_ERROR",
                              error_message=f"provider http {exc.code}")
        except Exception as exc:  # noqa: BLE001 - network/timeout/etc.
            log.warning("openai-compat provider %s failed: %s",
                        self.provider_key, exc)
            return TextResult(ok=False, error_code="PROVIDER_ERROR",
                              error_message=str(exc)[:200])
        try:
            data = json.loads(raw)
        except ValueError:
            return TextResult(ok=False, error_code="PROVIDER_ERROR",
                              error_message="invalid provider response")
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices else {}) or {}
        text = message.get("content") or ""
        if not isinstance(text, str):
            text = str(text)
        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        return TextResult(
            ok=True,
            text=text,
            provider_request_id=str(data.get("id")) if data.get("id") else None,
            input_tokens=int(input_tokens) if input_tokens is not None else None,
            output_tokens=int(output_tokens) if output_tokens is not None else None,
            usage_source="provider" if usage else None,
        )


class OpenAICompatSttProvider(SpeechToTextProvider):
    """Shared OpenAI-compatible speech-to-text client — provider-agnostic.

    POSTs multipart/form-data to ``{base_url}/audio/transcriptions`` with
    fields ``file`` (audio bytes), ``model`` and optional ``language``.
    Audio is fetched from the app's storage backend by ``audio_key``.
    """

    def __init__(self, base_url: str, api_key: str, provider_key: str,
                 timeout_seconds: int = 180):
        if not base_url or not api_key:
            raise ValueError("base_url and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_key = provider_key
        self.timeout_seconds = timeout_seconds

    def transcribe(self, model: str, audio_key: str, options: dict) -> TranscriptResult:
        from app.services.storage import storage  # lazy: avoids import cycles

        try:
            audio_bytes = storage.get_bytes(audio_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("stt: failed to read audio %s: %s", audio_key, exc)
            return TranscriptResult(ok=False, error_code="STORAGE_ERROR",
                                    error_message="could not read input audio")
        if not audio_bytes:
            return TranscriptResult(ok=False, error_code="EMPTY_AUDIO",
                                    error_message="input audio is empty")

        filename = audio_key.rsplit("/", 1)[-1] or "audio.wav"
        mime_type = options.get("mime_type") or "audio/wav"
        fields = {"model": model}
        if options.get("language"):
            fields["language"] = str(options["language"])
        body, content_type = _encode_multipart(fields, "file", filename, mime_type, audio_bytes)

        url = f"{self.base_url}/audio/transcriptions"
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": content_type,
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001
                pass
            log.warning("openai-compat stt provider %s http %s: %s",
                        self.provider_key, exc.code, detail)
            return TranscriptResult(ok=False, error_code="PROVIDER_ERROR",
                                    error_message=f"provider http {exc.code}")
        except Exception as exc:  # noqa: BLE001 - network/timeout/etc.
            log.warning("openai-compat stt provider %s failed: %s",
                        self.provider_key, exc)
            return TranscriptResult(ok=False, error_code="PROVIDER_ERROR",
                                    error_message=str(exc)[:200])
        try:
            data = json.loads(raw)
        except ValueError:
            return TranscriptResult(ok=False, error_code="PROVIDER_ERROR",
                                    error_message="invalid provider response")
        text = data.get("text") or ""
        if not isinstance(text, str):
            text = str(text)
        return TranscriptResult(
            ok=True,
            text=text,
            provider_request_id=str(data.get("id")) if data.get("id") else None,
            duration_seconds=int(options.get("duration_seconds") or 0) or None,
        )


def _encode_multipart(fields: dict, file_field: str, filename: str,
                      content_type: str, file_bytes: bytes) -> tuple[bytes, str]:
    """Build a multipart/form-data body with stdlib only."""
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for name, value in fields.items():
        body.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
            f'\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    body.write(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8")
    )
    body.write(file_bytes)
    body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return body.getvalue(), f"multipart/form-data; boundary={boundary}"


def _resolve_credentials(provider_key: str | None, model=None) -> tuple[str, str]:
    """Resolve (base_url, api_key) for a provider.

    Priority: 1) credentials stored on the model via the admin form,
    2) ``AI_PROVIDER_<KEY>_BASE_URL`` / ``AI_PROVIDER_<KEY>_API_KEY`` env,
    3) generic ``AI_TEXT_BASE_URL`` / ``AI_TEXT_API_KEY`` env fallback.
    """
    if model is not None:
        cfg = getattr(model, "config_json", None) or {}
        creds = cfg.get("__provider__") or {}
        base_url = (creds.get("base_url") or "").strip()
        api_key = (creds.get("api_key") or "").strip()
        if base_url or api_key:
            if not (base_url and api_key):
                raise ValueError(
                    f"incomplete credentials stored for provider {provider_key!r}: "
                    "base_url and api_key must both be set"
                )
            return base_url, api_key
    return config.ai_provider_credentials(provider_key)


def get_text_provider(provider_key: str | None = None, model=None) -> TextAiProvider:
    """Select the text provider.

    ``provider_key`` is the model's catalog key (e.g. ``"metis"``); ``model``
    is the catalog row, used for form-stored credentials (env is fallback).
    """
    name = (config.ai_text_provider or "fake").lower()
    if name == "fake":
        return FakeTextProvider()
    if name == "openai_compat":
        base_url, api_key = _resolve_credentials(provider_key, model)
        if not base_url or not api_key:
            raise ValueError(
                f"missing credentials for provider {provider_key!r}: "
                f"set them in the admin model form or via "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_BASE_URL / "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_API_KEY"
            )
        return OpenAICompatTextProvider(
            base_url=base_url, api_key=api_key,
            provider_key=provider_key or "default",
        )
    raise ValueError(f"unknown AI_TEXT_PROVIDER: {name}")


def get_stt_provider(provider_key: str | None = None, model=None) -> SpeechToTextProvider:
    """Select the speech-to-text provider.

    ``provider_key`` is the model's catalog key (e.g. ``"arvan_stt"``); ``model``
    is the catalog row, used for form-stored credentials (env is fallback).
    """
    name = (config.ai_audio_provider or "fake").lower()
    if name == "fake":
        return FakeSttProvider()
    if name == "openai_compat":
        base_url, api_key = _resolve_credentials(provider_key, model)
        if not base_url or not api_key:
            raise ValueError(
                f"missing credentials for provider {provider_key!r}: "
                f"set them in the admin model form or via "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_BASE_URL / "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_API_KEY"
            )
        return OpenAICompatSttProvider(
            base_url=base_url, api_key=api_key,
            provider_key=provider_key or "default",
        )
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
