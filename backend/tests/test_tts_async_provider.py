"""Async TTS provider (Metis-style generations API): selector + synthesize flow."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.ai.adapters import AsyncGenerationTtsProvider, get_tts_provider


def _model(provider_type):
    return SimpleNamespace(
        provider_type=provider_type,
        config_json={"__provider__": {"base_url": "https://x", "api_key": "k"}},
    )


def test_get_tts_provider_metis():
    p = get_tts_provider("k", _model("metis_tts"))
    assert isinstance(p, AsyncGenerationTtsProvider)


def test_get_tts_provider_async_generation():
    p = get_tts_provider("k", _model("async_generation"))
    assert isinstance(p, AsyncGenerationTtsProvider)


def test_synthesize_create_poll_download():
    p = AsyncGenerationTtsProvider(
        base_url="https://platform-api.metisai.ir", api_key="k", provider_key="t",
    )
    calls = []

    def fake_api(method, path, payload=None, content_type=None):
        calls.append((method, path, payload))
        if method == "POST":
            assert payload["operation"] == "TTS"
            assert payload["model"] == {"name": "openai", "model": "tts-1"}
            assert payload["args"]["prompt"] == "hello"
            return {"id": "task-1"}
        return {"status": "COMPLETED",
                "generations": [{"url": "https://cdn.test/a.mp3"}]}

    with patch.object(p, "_api", side_effect=fake_api):
        with patch.object(p, "_download", return_value=b"MP3BYTES") as dl:
            res = p.synthesize("openai/tts-1", "hello", {})
    assert res.ok
    assert res.audio_bytes == b"MP3BYTES"
    assert res.mime_type == "audio/mpeg"
    assert res.provider_request_id == "task-1"
    dl.assert_called_once_with("https://cdn.test/a.mp3")
    assert calls[0][0] == "POST" and calls[1] == ("GET", "/api/v2/generate/task-1", None)


def test_synthesize_bad_model_name():
    p = AsyncGenerationTtsProvider(
        base_url="https://x", api_key="k", provider_key="t",
    )
    res = p.synthesize("no-slash", "hi", {})
    assert not res.ok
    assert res.error_code == "MODEL_MISCONFIGURED"
