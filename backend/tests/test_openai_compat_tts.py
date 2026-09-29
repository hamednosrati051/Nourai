"""OpenAI-compatible TTS provider: model-driven selection + synthesize."""
from __future__ import annotations

import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ai.adapters import (
    FakeTtsProvider,
    OpenAICompatTtsProvider,
    get_tts_provider,
)


def _model(provider_type, base_url=None, api_key=None):
    cfg = {}
    if base_url or api_key:
        cfg["__provider__"] = {"base_url": base_url, "api_key": api_key}
    return SimpleNamespace(provider_type=provider_type, config_json=cfg)


def test_get_tts_provider_fake_from_model():
    assert isinstance(get_tts_provider("k", _model("fake")), FakeTtsProvider)


def test_get_tts_provider_openai_compat_from_model_form():
    p = get_tts_provider("k", _model("openai_compat", "https://tts.example/v1", "tok"))
    assert isinstance(p, OpenAICompatTtsProvider)
    assert p.base_url == "https://tts.example/v1"


def test_get_tts_provider_openai_compat_missing_credentials():
    with pytest.raises(ValueError):
        get_tts_provider("k", _model("openai_compat"))


def test_get_tts_provider_unknown():
    with pytest.raises(ValueError):
        get_tts_provider("k", _model("nope"))


def _mock_response(payload: bytes, content_type="audio/mpeg"):
    resp = MagicMock()
    resp.read.return_value = payload
    resp.headers = {"Content-Type": content_type}
    resp.__enter__.return_value = resp
    return resp


def test_synthesize_posts_audio_speech_and_returns_bytes():
    provider = OpenAICompatTtsProvider("https://tts.example/v1", "tok", "k")
    with patch("urllib.request.urlopen", return_value=_mock_response(b"AUDIO")) as urlopen:
        result = provider.synthesize("my-voice-model", "سلام", {})
    assert result.ok
    assert result.audio_bytes == b"AUDIO"
    assert result.mime_type == "audio/mpeg"
    (req,), kwargs = urlopen.call_args
    assert req.full_url == "https://tts.example/v1/audio/speech"
    assert req.get_header("Authorization") == "Bearer tok"
    import json

    body = json.loads(req.data.decode())
    assert body["model"] == "my-voice-model"
    assert body["input"] == "سلام"
    assert body["voice"] == "alloy"  # default voice; no voice selection UI yet


def test_synthesize_http_error():
    provider = OpenAICompatTtsProvider("https://tts.example/v1", "tok", "k")
    err = urllib.error.HTTPError("https://tts.example/v1/audio/speech", 500, "err", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        result = provider.synthesize("m", "hi", {})
    assert not result.ok
    assert result.error_code == "PROVIDER_ERROR"
