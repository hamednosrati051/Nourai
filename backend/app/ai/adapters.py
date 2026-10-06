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
import os
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


class SherpaSttProvider(SpeechToTextProvider):
    """Local sherpa-onnx speech-to-text — no API calls, no cost.

    Runs a NeMo/CTC ONNX model (e.g. Shenava Persian ASR) via sherpa-onnx.
    Configuration comes from the AiModel row's ``config_json``::

        {
            "sherpa_model": "/opt/nourai/stt-models/shenava-koochik/model.int8.onnx",
            "sherpa_tokens": "/opt/nourai/stt-models/shenava-koochik/tokens.txt",
            "sherpa_threads": 2
        }

    Audio is fetched from the app's storage backend by ``audio_key`` and
    decoded to 16kHz mono float32 (via ffmpeg when available, else WAV).
    """

    _recognizer_cache: dict = {}

    def __init__(self, model_path: str, tokens_path: str, num_threads: int = 2):
        self.model_path = model_path
        self.tokens_path = tokens_path
        self.num_threads = num_threads

    @classmethod
    def from_model(cls, model) -> "SherpaSttProvider":
        cfg = {}
        try:
            raw = getattr(model, "config_json", None)
            cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:  # noqa: BLE001
            cfg = {}
        cfg = cfg.get("__provider__", cfg)
        return cls(
            model_path=cfg.get("sherpa_model") or "/opt/nourai/stt-models/shenava-koochik/model.int8.onnx",
            tokens_path=cfg.get("sherpa_tokens") or "/opt/nourai/stt-models/shenava-koochik/tokens.txt",
            num_threads=int(cfg.get("sherpa_threads") or 2),
        )

    def _get_recognizer(self):
        key = f"{self.model_path}:{self.tokens_path}"
        if key in SherpaSttProvider._recognizer_cache:
            return SherpaSttProvider._recognizer_cache[key]
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError("sherpa-onnx is not installed") from exc
        if not os.path.isfile(self.model_path):
            raise ValueError(f"sherpa model not found: {self.model_path}")
        if not os.path.isfile(self.tokens_path):
            raise ValueError(f"sherpa tokens not found: {self.tokens_path}")
        recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=self.model_path,
            tokens=self.tokens_path,
            num_threads=self.num_threads,
        )
        SherpaSttProvider._recognizer_cache[key] = recognizer
        return recognizer

    def _decode_audio(self, audio_bytes: bytes, mime_type: str) -> tuple:
        """Return (samples_float32_mono, sample_rate)."""
        import io
        import wave
        import subprocess
        import tempfile

        # Fast path: WAV files
        if mime_type in ("audio/wav", "audio/x-wav") or audio_bytes[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                    n_channels = wav.getnchannels()
                    sampwidth = wav.getsampwidth()
                    sample_rate = wav.getframerate()
                    frames = wav.readframes(wav.getnframes())
                import numpy as np
                if sampwidth == 2:
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
                else:
                    raise ValueError(f"unsupported WAV bit depth: {sampwidth * 8}")
                if n_channels > 1:
                    audio = audio.reshape(-1, n_channels).mean(axis=1)
                return audio, sample_rate
            except Exception:
                pass  # fall through to ffmpeg

        # General path: ffmpeg to 16kHz mono WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", "pipe:0",
                 "-ar", "16000", "-ac", "1", "-f", "wav", tmp_path],
                input=audio_bytes, capture_output=True, timeout=120,
            )
            if proc.returncode != 0:
                raise ValueError("ffmpeg failed to decode audio")
            with wave.open(tmp_path, "rb") as wav:
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
            import numpy as np
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            return audio, sample_rate
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def transcribe(self, model: str, audio_key: str, options: dict) -> TranscriptResult:
        from app.services.storage import storage  # lazy: avoids import cycles

        try:
            audio_bytes = storage.get_bytes(audio_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("sherpa stt: failed to read audio %s: %s", audio_key, exc)
            return TranscriptResult(ok=False, error_code="STORAGE_ERROR",
                                    error_message="could not read input audio")
        if not audio_bytes:
            return TranscriptResult(ok=False, error_code="EMPTY_AUDIO",
                                    error_message="input audio is empty")
        try:
            import numpy as np
            recognizer = self._get_recognizer()
            mime_type = options.get("mime_type") or "audio/wav"
            audio, sample_rate = self._decode_audio(audio_bytes, mime_type)
            if sample_rate != 16000:
                # Resample to 16kHz
                duration = len(audio) / sample_rate
                num_samples = int(duration * 16000)
                audio = np.interp(
                    np.linspace(0, len(audio), num_samples),
                    np.arange(len(audio)), audio,
                ).astype(np.float32)
                sample_rate = 16000
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, audio)
            recognizer.decode_stream(stream)
            text = (stream.result.text or "").strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("sherpa stt failed: %s", exc)
            return TranscriptResult(ok=False, error_code="PROVIDER_ERROR",
                                    error_message=str(exc)[:200])
        return TranscriptResult(
            ok=True,
            text=text,
            duration_seconds=int(options.get("duration_seconds") or 0) or None,
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


class PiperTtsProvider(TextToSpeechProvider):
    """Local Piper neural TTS — no API calls, no cost.

    Voice models are ONNX files on disk. Configuration comes from the
    AiModel row's ``config_json``::

        {
            "piper_voices_dir": "/opt/nourai/piper-voices",
            "piper_voices": [
                {"key": "raham", "file": "fa_IR-amir-medium.onnx", "label": "رهام (مرد)"},
                {"key": "hana",  "file": "fa_IR-mana-medium.onnx", "label": "حنا (زن)"}
            ],
            "default_voice": "raham"
        }

    ``piper_voices`` is an ordered list (a plain dict is also accepted for
    backward compatibility, but MySQL JSON columns do not preserve key
    order). The requested voice comes from ``options["voice"]`` (the TTS
    job's ``voice`` parameter); falls back to ``default_voice``. Output is
    a WAV byte stream.
    """

    _voice_cache: dict = {}

    def __init__(self, voices_dir: str, voices: dict, default_voice: str | None = None):
        self.voices_dir = voices_dir
        self.voices = voices or {}
        self.default_voice = default_voice or (next(iter(self.voices), None))

    @staticmethod
    def _normalize_voices(raw) -> dict:
        """Accept an ordered list of {key, file, label} or a legacy dict."""
        if isinstance(raw, list):
            out = {}
            for spec in raw:
                if isinstance(spec, dict) and spec.get("key") and spec.get("file"):
                    out[spec["key"]] = {"file": spec["file"], "label": spec.get("label") or spec["key"]}
            return out
        return raw if isinstance(raw, dict) else {}

    @classmethod
    def from_model(cls, model) -> "PiperTtsProvider":
        cfg = {}
        try:
            raw = getattr(model, "config_json", None)
            cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:  # noqa: BLE001
            cfg = {}
        cfg = cfg.get("__provider__", cfg)
        return cls(
            voices_dir=cfg.get("piper_voices_dir") or "/opt/nourai/piper-voices",
            voices=cls._normalize_voices(cfg.get("piper_voices")),
            default_voice=cfg.get("default_voice"),
        )

    def _load_voice(self, voice_name: str):
        key = f"{self.voices_dir}:{voice_name}"
        if key in PiperTtsProvider._voice_cache:
            return PiperTtsProvider._voice_cache[key]
        spec = self.voices.get(voice_name)
        if not spec:
            raise ValueError(f"unknown piper voice: {voice_name}")
        model_path = os.path.join(self.voices_dir, spec["file"])
        if not os.path.isfile(model_path):
            raise ValueError(f"piper voice model not found: {model_path}")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise RuntimeError("piper-tts is not installed") from exc
        voice = PiperVoice.load(model_path)
        PiperTtsProvider._voice_cache[key] = voice
        return voice

    def synthesize(self, model: str, text: str, options: dict) -> AudioResult:
        voice_name = options.get("voice") or self.default_voice
        if not voice_name or voice_name not in self.voices:
            return AudioResult(
                ok=False, error_code="PROVIDER_ERROR",
                error_message=f"unknown piper voice: {voice_name}",
            )
        try:
            voice = self._load_voice(voice_name)
            chunks = list(voice.synthesize(text))
        except Exception as exc:  # noqa: BLE001
            log.warning("piper tts failed voice=%s: %s", voice_name, exc)
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message=str(exc)[:200])
        if not chunks:
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="empty piper output")
        import wave
        import io
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(chunks[0].sample_rate)
            for chunk in chunks:
                wav.writeframes(chunk.audio_int16_bytes)
        return AudioResult(
            ok=True,
            audio_bytes=buf.getvalue(),
            mime_type="audio/wav",
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


class OpenAICompatTtsProvider(TextToSpeechProvider):
    """Shared OpenAI-compatible text-to-speech client — provider-agnostic.

    POSTs JSON to ``{base_url}/audio/speech`` with ``model``, ``input``,
    ``voice`` and ``response_format``. The endpoint returns raw audio bytes
    (not JSON). ``model`` is the catalog's ``provider_model_name`` verbatim;
    ``voice`` comes from ``options["voice"]`` or defaults to ``"alloy"``
    (no voice selection UI yet).
    """

    def __init__(self, base_url: str, api_key: str, provider_key: str,
                 timeout_seconds: int = 180):
        if not base_url or not api_key:
            raise ValueError("base_url and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_key = provider_key
        self.timeout_seconds = timeout_seconds

    def synthesize(self, model: str, text: str, options: dict) -> AudioResult:
        payload = json.dumps({
            "model": model,
            "input": text,
            "voice": options.get("voice") or "alloy",
            "response_format": options.get("response_format") or "mp3",
        }).encode("utf-8")
        url = f"{self.base_url}/audio/speech"
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                audio_bytes = resp.read()
                mime_type = resp.headers.get("Content-Type", "audio/mpeg")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001
                pass
            log.warning("openai-compat tts provider %s http %s: %s",
                        self.provider_key, exc.code, detail)
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message=f"provider http {exc.code}")
        except Exception as exc:  # noqa: BLE001 - network/timeout/etc.
            log.warning("openai-compat tts provider %s failed: %s",
                        self.provider_key, exc)
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message=str(exc)[:200])
        if not audio_bytes:
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="empty provider response")
        return AudioResult(
            ok=True,
            audio_bytes=audio_bytes,
            mime_type=mime_type.split(";")[0].strip() or "audio/mpeg",
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
    def _size(options: dict) -> str | None:
        # Some OpenAI-compatible providers reject the request when `size`
        # is present (e.g. AvalAI qwen-image answers 400); only send it
        # when the caller explicitly asked for dimensions.
        w, h = options.get("width"), options.get("height")
        if w is None and h is None:
            return None
        return f"{int(w or 1024)}x{int(h or 1024)}"

    def generate(self, model: str, prompt: str, options: dict) -> ImageResult:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        size = self._size(options)
        if size:
            payload["size"] = size
        data = self._post_json("/images/generations", payload)
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
        fields = {"model": model, "prompt": prompt, "n": "1",
                  "response_format": "b64_json"}
        size = self._size(options)
        if size:
            fields["size"] = size
        body, content_type = _encode_multipart(
            fields, "image", filename, "image/png", image_bytes,
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


class _ProviderError(Exception):
    """Raised when the provider API itself rejects the call (auth/credit)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def _probe_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    """Read (width, height) from image bytes; (None, None) on failure."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001
        return None, None


def _metis_usage_cost_to_cents(usage: dict) -> int | None:
    """Convert Metis ``usage.cost`` (US dollars) to integer cents.

    Docs example: ``"usage": {"cost": 0.14}`` means $0.14 = 14 cents.
    Returns None when the payload has no parseable cost.
    """
    raw = (usage or {}).get("cost")
    if raw is None:
        return None
    try:
        return int(round(float(raw) * 100))
    except (TypeError, ValueError):
        return None


class _AsyncGenerationBase:
    """Shared create -> poll -> download client for async generation APIs
    (e.g. MetisAI): ``POST {base_url}/api/v2/generate`` with
    ``{"model": {"name": vendor, "model": name}, "operation": ..., "args": ...}``;
    result via ``GET {base_url}/api/v2/generate/{id}`` polling until
    ``COMPLETED``.

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
            # Surface provider-side failures (e.g. 402 insufficient credit)
            # instead of a bare None.
            if exc.code == 402:
                return {"_provider_error": "INSUFFICIENT_CREDIT", "_detail": detail}
            if exc.code == 401:
                return {"_provider_error": "INVALID_CREDENTIALS", "_detail": detail}
        except Exception as exc:  # noqa: BLE001 - network/timeout/etc.
            log.warning("async-generation image provider %s %s failed: %s",
                        self.provider_key, path, exc)
        return None

    def _create_task(self, vendor: str, name: str, operation: str,
                     args: dict) -> str | None:
        data = self._api("POST", "/api/v2/generate", {
            "model": {"name": vendor, "model": name},
            "operation": operation,
            "args": args,
        })
        if data and data.get("_provider_error"):
            raise _ProviderError(data["_provider_error"], data.get("_detail") or "")
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
            log.warning("async download failed: %s", exc)
            return b""


class AsyncGenerationImageProvider(_AsyncGenerationBase, ImageAiProvider):
    """Async image generation (create -> poll -> download).

    ``operation`` is ``"Imagine"``; ``args`` carries ``prompt`` and,
    for edits, ``image_input`` (a URL — ``edit`` uploads the input image
    to ``{base_url}/api/v1/storage`` first).
    """

    def _create(self, vendor: str, name: str, prompt: str,
                image_input: str | None = None) -> str | None:
        args: dict = {"prompt": prompt}
        if image_input:
            args["image_input"] = image_input
        return self._create_task(vendor, name, "Imagine", args)

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
        provider_cost_cents = _metis_usage_cost_to_cents(usage)
        log.info("async generation %s cost=$%s (%s cents)", task_id, usage.get("cost"), provider_cost_cents)
        mime = "image/jpeg"
        if url.lower().endswith(".png"):
            mime = "image/png"
        elif url.lower().endswith(".webp"):
            mime = "image/webp"
        return ImageResult(
            ok=True, image_bytes=image_bytes, mime_type=mime,
            width=width, height=height, provider_request_id=task_id,
            provider_cost_cents=provider_cost_cents,
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
        try:
            task_id = self._create(vendor, name, prompt)
        except _ProviderError as exc:
            return ImageResult(ok=False, error_code=exc.code,
                               error_message=str(exc) or exc.code)
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


def _guess_audio_mime(url: str) -> str:
    lower = (url or "").lower().split("?")[0]
    if lower.endswith(".wav"):
        return "audio/wav"
    if lower.endswith(".ogg") or lower.endswith(".oga"):
        return "audio/ogg"
    if lower.endswith(".webm"):
        return "audio/webm"
    if lower.endswith(".m4a"):
        return "audio/mp4"
    return "audio/mpeg"


class AsyncGenerationTtsProvider(_AsyncGenerationBase, TextToSpeechProvider):
    """Async text-to-speech (create -> poll -> download).

    ``operation`` is ``"TTS"``; ``args`` carries ``prompt`` (the text)
    and, when given, ``voice``. The finished generation's
    ``generations[0].url`` is downloaded as the audio file.
    """

    def synthesize(self, model: str, text: str, options: dict) -> AudioResult:
        split = self._split_model(model)
        if not split:
            return AudioResult(
                ok=False, error_code="MODEL_MISCONFIGURED",
                error_message="provider_model_name must be 'vendor/model' (e.g. openai/tts-1)",
            )
        vendor, name = split
        args: dict = {"prompt": text}
        voice = (options or {}).get("voice")
        if voice:
            args["voice"] = voice
        try:
            task_id = self._create_task(vendor, name, "TTS", args)
        except _ProviderError as exc:
            return AudioResult(ok=False, error_code=exc.code,
                               error_message=str(exc) or exc.code)
        if not task_id:
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="could not create tts generation")
        data = self._poll(task_id)
        if not data:
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="tts generation failed or timed out")
        generations = data.get("generations") or []
        url = (generations[0].get("url") if generations else None)
        if not url:
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="empty tts result")
        audio_bytes = self._download(url)
        if not audio_bytes:
            return AudioResult(ok=False, error_code="PROVIDER_ERROR",
                               error_message="could not download tts audio")
        return AudioResult(
            ok=True, audio_bytes=audio_bytes,
            mime_type=_guess_audio_mime(url),
            provider_request_id=task_id,
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
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:  # noqa: BLE001
                cfg = {}
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
    if name == "sherpa":
        # Local sherpa-onnx STT: no credentials needed; model paths come
        # from the model row's config_json (see SherpaSttProvider).
        if model is None:
            raise ValueError("sherpa provider requires a model row with config_json")
        return SherpaSttProvider.from_model(model)
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


def get_tts_provider(provider_key: str | None = None, model=None) -> TextToSpeechProvider:
    """Select the text-to-speech provider.

    ``provider_key`` is the model's catalog key; ``model`` is the catalog
    row, used for form-stored credentials (env is fallback) and for the
    per-model ``provider_type`` (env is fallback). Same pattern as the
    text and STT selectors.
    """
    name = ((getattr(model, "provider_type", None) or config.ai_audio_provider) or "fake").lower()
    if name == "fake":
        return FakeTtsProvider()
    if name == "piper":
        # Local Piper TTS: no credentials needed; voices come from the
        # model row's config_json (see PiperTtsProvider).
        if model is None:
            raise ValueError("piper provider requires a model row with config_json")
        return PiperTtsProvider.from_model(model)
    if name in ("openai_compat", "async_generation"):
        base_url, api_key = _resolve_credentials(provider_key, model)
        if not base_url or not api_key:
            raise ValueError(
                f"missing credentials for provider {provider_key!r}: "
                f"set them in the admin model form or via "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_BASE_URL / "
                f"AI_PROVIDER_{(provider_key or 'default').upper()}_API_KEY"
            )
        cls = (
            OpenAICompatTtsProvider
            if name == "openai_compat"
            else AsyncGenerationTtsProvider
        )
        return cls(
            base_url=base_url, api_key=api_key,
            provider_key=provider_key or "default",
        )
    raise ValueError(f"unknown AI_AUDIO_PROVIDER: {name}")


# ---------------------------------------------------------------------------
# Image provider selection (model-driven).
#
# ``get_image_provider`` reads ``provider_type`` from the AiModel row
# (``fake`` | ``openai_compat`` | ``async_generation``), the same pattern
# as the text/STT/TTS selectors. Provider credentials come from the admin
# model form (env is fallback).
# ---------------------------------------------------------------------------
def get_image_provider(provider_key: str | None = None, model=None) -> ImageAiProvider:
    """Select the image provider from the model row."""
    name = ((getattr(model, "provider_type", None)) or "fake").lower()
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
        cls = (
            OpenAICompatImageProvider
            if name == "openai_compat"
            else AsyncGenerationImageProvider
        )
        return cls(
            base_url=base_url, api_key=api_key,
            provider_key=provider_key or "default",
        )
    raise ValueError(f"unknown image provider_type: {name}")
