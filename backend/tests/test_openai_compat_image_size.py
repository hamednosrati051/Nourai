"""OpenAICompatImageProvider: `size` is only sent when dimensions are explicit.

Some OpenAI-compatible providers (e.g. AvalAI qwen-image) reject the
request with 400 when `size` is present; omitting it makes the call work.
"""
from unittest.mock import patch

from app.ai.adapters import OpenAICompatImageProvider


def _provider():
    return OpenAICompatImageProvider(
        base_url="https://api.avalai.ir/v1", api_key="k", provider_key="avalai"
    )


def test_generate_omits_size_without_dimensions():
    p = _provider()
    captured = {}

    def fake_post(path, payload):
        captured["payload"] = payload
        return {"data": [{"url": "https://x/y.png"}]}

    with patch.object(p, "_post_json", side_effect=fake_post), patch.object(
        p, "_download", return_value=b"img"
    ):
        res = p.generate("qwen-image", "a sunset", {})
    assert res.ok is True
    assert "size" not in captured["payload"]


def test_generate_includes_size_with_dimensions():
    p = _provider()
    captured = {}

    def fake_post(path, payload):
        captured["payload"] = payload
        return {"data": [{"url": "https://x/y.png"}]}

    with patch.object(p, "_post_json", side_effect=fake_post), patch.object(
        p, "_download", return_value=b"img"
    ):
        res = p.generate("qwen-image", "a sunset", {"width": 512, "height": 768})
    assert res.ok is True
    assert captured["payload"]["size"] == "512x768"
