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


class OpenAICompatImageProvider(ImageAiProvider):
    """Shared OpenAI-compatible image client — provider-agnostic.

    ``generate`` POSTs JSON to ``{base_url}/images/generations``;
    ``edit`` POSTs multipart/form-data to ``{base_url}/images/edits``.
    The ``model`` sent is the catalog's ``provider_model_name`` verbatim.
    Works with any OpenAI-compatible image endpoint (selected per model
    via ``provider_type=openai_compat`` in the admin form).
    """

    def __init__(self, base_url: str, api_key: str, provider_key: str,
                 timeout_seconds: int = 180):
        if not base_url or not api_key:
            raise ValueError("base_url and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_key = provider_key
        self.timeout_seconds = timeout_seconds

    def _headers(self, content_type: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _post_json(self, path: str, payload: dict) -> dict | None:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=body, method="POST",
            headers=self._headers("application/json"),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001
                pass
            log.warning("openai-compat image provider %s http %s: %s",
                        self.provider_key, exc.code, detail)
        except Exception as exc:  # noqa: BLE001 - network/timeout/etc.
            log.warning("openai-compat image provider %s failed: %s",
                        self.provider_key, exc)
        return None

    def _result_from_data(self, data: dict | None, task_label: str) -> ImageResult:
        if not data:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="provider request failed")
        items = data.get("data") or []
        first = items[0] if items else {}
        b64 = first.get("b64_json")
        url = first.get("url")
        image_bytes = b""
        if b64:
            try:
                import base64
                image_bytes = base64.b64decode(b64)
            except Exception:  # noqa: BLE001
                pass
        elif url:
            image_bytes = self._download(url)
        if not image_bytes:
            log.warning("openai-compat image %s: empty result payload", task_label)
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="empty image result")
        width, height = _probe_dimensions(image_bytes)
        return ImageResult(
            ok=True, image_bytes=image_bytes, mime_type="image/png",
            width=width, height=height,
            provider_request_id=str(data.get("id")) if data.get("id") else None,
            revised_prompt=(first.get("revised_prompt") or None),
        )

    def _download(self, url: str) -> bytes:
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("openai-compat image download failed: %s", exc)
            return b""

    @staticmethod
    def _size(options: dict) -> str:
        w = int(options.get("width") or 1024)
        h = int(options.get("height") or 1024)
        return f"{w}x{h}"

    def generate(self, model: str, prompt: str, options: dict) -> ImageResult:
        data = self._post_json("/images/generations", {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": self._size(options),
            "response_format": "b64_json",
        })
        return self._result_from_data(data, "generate")

    def edit(self, model: str, prompt: str, input_image_key: str, options: dict) -> ImageResult:
        from app.services.storage import storage  # lazy: avoids import cycles

        try:
            image_bytes = storage.get_bytes(input_image_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("image edit: failed to read input %s: %s", input_image_key, exc)
            return ImageResult(ok=False, error_code="STORAGE_ERROR",
                               error_message="could not read input image")
        if not image_bytes:
            return ImageResult(ok=False, error_code="EMPTY_IMAGE",
                               error_message="input image is empty")
        filename = input_image_key.rsplit("/", 1)[-1] or "image.png"
        body, content_type = _encode_multipart(
            {"model": model, "prompt": prompt, "n": "1", "size": self._size(options),
             "response_format": "b64_json"},
            "image", filename, "image/png", image_bytes,
        )
        req = urllib.request.Request(
            f"{self.base_url}/images/edits", data=body, method="POST",
            headers=self._headers(content_type),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            log.warning("openai-compat image edit %s http %s", self.provider_key, exc.code)
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message=f"provider http {exc.code}")
        except Exception as exc:  # noqa: BLE001
            log.warning("openai-compat image edit %s failed: %s", self.provider_key, exc)
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message=str(exc)[:200])
        return self._result_from_data(data, "edit")


def _probe_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    """Read (width, height) from image bytes; (None, None) on failure."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001
        return None, None


class AsyncGenerationImageProvider(ImageAiProvider):
    """Async generation API client (create -> poll -> download).

    Generic adapter for providers with an asynchronous generation protocol
    (e.g. MetisAI): ``POST {base_url}/api/v2/generate`` with
    ``{"model": {"name": vendor, "model": name}, "operation": "Imagine",
    "args": {"prompt": ...}}``; result via ``GET {base_url}/api/v2/generate/{id}``
    polling until ``COMPLETED``. ``edit`` uploads the input image to
    ``{base_url}/api/v1/storage`` first and passes its URL as ``image_input``.

    The catalog's ``provider_model_name`` uses the ``vendor/model`` format
    (e.g. ``google/nano-banana``), matching the API's model object.
    """

    POLL_INTERVAL_SECONDS = 5
    POLL_DEADLINE_SECONDS = 600

    def __init__(self, base_url: str, api_key: str, provider_key: str,
                 timeout_seconds: int = 60):
        if not base_url or not api_key:
            raise ValueError("base_url and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_key = provider_key
        self.timeout_seconds = timeout_seconds

    def _headers(self, content_type: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def _split_model(model: str) -> tuple[str, str] | None:
        if "/" in model:
            vendor, name = model.split("/", 1)
            if vendor.strip() and name.strip():
                return vendor.strip(), name.strip()
        return None

    def _api(self, method: str, path: str, payload: dict | None = None,
             content_type: str | None = None) -> dict | None:
        body = None
        if payload is not None:
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=body, method=method,
            headers=self._headers(content_type or "application/json"),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001
                pass
            log.warning("async-generation image provider %s %s http %s: %s",
                        self.provider_key, path, exc.code, detail)
        except Exception as exc:  # noqa: BLE001 - network/timeout/etc.
            log.warning("async-generation image provider %s %s failed: %s",
                        self.provider_key, path, exc)
        return None

    def _create(self, vendor: str, name: str, prompt: str,
                image_input: str | None = None) -> str | None:
        args: dict = {"prompt": prompt}
        if image_input:
            args["image_input"] = image_input
        data = self._api("POST", "/api/v2/generate", {
            "model": {"name": vendor, "model": name},
            "operation": "Imagine",
            "args": args,
        })
        task_id = (data or {}).get("id")
        return str(task_id) if task_id else None

    def _poll(self, task_id: str) -> dict | None:
        import time
        deadline = time.monotonic() + self.POLL_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            data = self._api("GET", f"/api/v2/generate/{task_id}")
            if not data:
                return None
            status = (data.get("status") or "").upper()
            if status == "COMPLETED":
                return data
            if status in ("ERROR", "CANCELLED"):
                log.warning("async generation %s ended with %s: %s",
                            task_id, status, str(data.get("error"))[:200])
                return None
            time.sleep(self.POLL_INTERVAL_SECONDS)
        log.warning("async generation %s polling timed out", task_id)
        return None

    def _download(self, url: str) -> bytes:
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("async image download failed: %s", exc)
            return b""

    def _finish(self, task_id: str) -> ImageResult:
        data = self._poll(task_id)
        if not data:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="generation failed or timed out")
        generations = data.get("generations") or []
        url = (generations[0].get("url") if generations else None)
        if not url:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="empty generation result")
        image_bytes = self._download(url)
        if not image_bytes:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="could not download result image")
        width, height = _probe_dimensions(image_bytes)
        usage = data.get("usage") or {}
        if usage.get("cost") is not None:
            log.info("async generation %s cost=%s cents", task_id, usage.get("cost"))
        mime = "image/jpeg"
        if url.lower().endswith(".png"):
            mime = "image/png"
        elif url.lower().endswith(".webp"):
            mime = "image/webp"
        return ImageResult(
            ok=True, image_bytes=image_bytes, mime_type=mime,
            width=width, height=height, provider_request_id=task_id,
        )

    def _upload(self, image_bytes: bytes, filename: str) -> str | None:
        body, content_type = _encode_multipart({}, "files", filename, "image/png", image_bytes)
        data = self._api("POST", "/api/v1/storage", body, content_type)
        files = (data or {}).get("files") or []
        url = files[0].get("url") if files else None
        return url

    def generate(self, model: str, prompt: str, options: dict) -> ImageResult:
        split = self._split_model(model)
        if not split:
            return ImageResult(
                ok=False, error_code="MODEL_MISCONFIGURED",
                error_message="provider_model_name must be 'vendor/model' (e.g. google/nano-banana)",
            )
        vendor, name = split
        task_id = self._create(vendor, name, prompt)
        if not task_id:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="could not create generation")
        return self._finish(task_id)

    def edit(self, model: str, prompt: str, input_image_key: str, options: dict) -> ImageResult:
        from app.services.storage import storage  # lazy: avoids import cycles

        split = self._split_model(model)
        if not split:
            return ImageResult(
                ok=False, error_code="MODEL_MISCONFIGURED",
                error_message="provider_model_name must be 'vendor/model' (e.g. google/nano-banana)",
            )
        try:
            image_bytes = storage.get_bytes(input_image_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("async edit: failed to read input %s: %s", input_image_key, exc)
            return ImageResult(ok=False, error_code="STORAGE_ERROR",
                               error_message="could not read input image")
        if not image_bytes:
            return ImageResult(ok=False, error_code="EMPTY_IMAGE",
                               error_message="input image is empty")
        filename = input_image_key.rsplit("/", 1)[-1] or "image.png"
        image_url = self._upload(image_bytes, filename)
        if not image_url:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="could not upload input image")
        vendor, name = split
        task_id = self._create(vendor, name, prompt, image_input=image_url)
        if not task_id:
            return ImageResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="could not create generation")
        return self._finish(task_id)


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
    is the catalog row, used for form-stored credentials (env is fallback)
    and for the per-model ``provider_type`` (env is fallback).
    """
    name = ((getattr(model, "provider_type", None) or config.ai_text_provider) or "fake").lower()
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
    is the catalog row, used for form-stored credentials (env is fallback)
    and for the per-model ``provider_type`` (env is fallback).
    """
    name = ((getattr(model, "provider_type", None) or config.ai_audio_provider) or "fake").lower()
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


def get_image_provider(provider_key: str | None = None, model=None) -> ImageAiProvider:
    """Select the image provider.

    Mirrors :func:`get_text_provider`: ``provider_type`` comes from the
    model's catalog row (admin form), credentials from the form-stored
    ``__provider__`` block (env is fallback). ``fake`` keeps the
    deterministic placeholder for dev/test.
    """
    name = ((getattr(model, "provider_type", None) or config.ai_image_provider) or "fake").lower()
    if name == "fake":
        return FakeImageProvider()
    if name in ("openai_compat", "async_generation"):
        base_url, api_key = _resolve_credentials(provider_key, model)
        if not base_url or not api_key:
            raise ValueError(
                f"missing credentials for provider {provider_key!r}: "
                f"set them in the admin model form or via "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_BASE_URL / "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_API_KEY"
            )
        if name == "openai_compat":
            return OpenAICompatImageProvider(
                base_url=base_url, api_key=api_key,
                provider_key=provider_key or "default",
            )
        return AsyncGenerationImageProvider(
            base_url=base_url, api_key=api_key,
            provider_key=provider_key or "default",
        )
    raise ValueError(f"unknown AI_IMAGE_PROVIDER: {name}")
