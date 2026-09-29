"""ElevenLabs TTS adapter: request shape and response handling."""
import io
import json
import urllib.error
from unittest.mock import patch

from app.ai.adapters import ElevenLabsTtsProvider


class _FakeResp:
    def __init__(self, payload: bytes):
        self._buf = io.BytesIO(payload)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _capture_request(payload: bytes):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp(payload)

    return fake_urlopen, captured


def test_synthesize_posts_voice_and_text():
    provider = ElevenLabsTtsProvider("test-key")
    fake_urlopen, captured = _capture_request(b"ID3fake-mp3")
    with patch("urllib.request.urlopen", fake_urlopen):
        result = provider.synthesize("voice-abc", "سلام دنیا", {})
    assert result.ok
    assert result.audio_bytes == b"ID3fake-mp3"
    assert result.mime_type == "audio/mpeg"
    assert captured["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice-abc"
    assert captured["headers"]["Xi-api-key"] == "test-key"
    assert captured["body"]["text"] == "سلام دنیا"
    assert captured["body"]["model_id"] == "eleven_v3"


def test_synthesize_http_error():
    provider = ElevenLabsTtsProvider("bad-key")

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))

    with patch("urllib.request.urlopen", fake_urlopen):
        result = provider.synthesize("voice-abc", "hi", {})
    assert not result.ok
    assert result.error_code == "PROVIDER_ERROR"


def test_synthesize_missing_voice_id():
    provider = ElevenLabsTtsProvider("test-key")
    result = provider.synthesize("", "hi", {})
    assert not result.ok


def test_get_tts_provider_from_model_form():
    """TTS provider type + credentials come from the admin model row (like STT)."""
    from types import SimpleNamespace

    from app.ai.adapters import FakeTtsProvider, get_tts_provider

    model = SimpleNamespace(
        provider_type="elevenlabs",
        provider_key="elevenlabs",
        config_json={"__provider__": {
            "base_url": "https://api.elevenlabs.io",
            "api_key": "k",
        }},
    )
    provider = get_tts_provider("elevenlabs", model)
    assert isinstance(provider, ElevenLabsTtsProvider)
    assert provider.base_url == "https://api.elevenlabs.io"

    fake_model = SimpleNamespace(provider_type="fake", provider_key="x", config_json={})
    assert isinstance(get_tts_provider("x", fake_model), FakeTtsProvider)
