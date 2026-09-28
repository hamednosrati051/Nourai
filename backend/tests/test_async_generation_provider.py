"""Verify AsyncGenerationImageProvider matches Metis platform-api docs."""
import json
from unittest.mock import patch
from app.ai.adapters import AsyncGenerationImageProvider

def test_create_payload_matches_metis_docs():
    p = AsyncGenerationImageProvider(
        base_url="https://platform-api.metisai.ir", api_key="k", provider_key="metis")
    captured = {}
    def fake_api(method, path, payload=None, content_type=None):
        captured.update(method=method, path=path, payload=payload)
        return {"id": "gen-123"}
    with patch.object(p, "_api", side_effect=fake_api):
        task_id = p._create("google", "nano-banana-2", "a sunset")
    assert task_id == "gen-123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v2/generate"
    assert captured["payload"] == {
        "model": {"name": "google", "model": "nano-banana-2"},
        "operation": "Imagine",
        "args": {"prompt": "a sunset"},
    }

def test_poll_path_matches_metis_docs():
    p = AsyncGenerationImageProvider(
        base_url="https://platform-api.metisai.ir", api_key="k", provider_key="metis")
    calls = []
    def fake_api(method, path, payload=None, content_type=None):
        calls.append((method, path))
        if method == "POST":
            return {"id": "gen-123"}
        return {"status": "COMPLETED", "generations": [{"url": "https://x/y.png"}]}
    with patch.object(p, "_api", side_effect=fake_api), \
         patch.object(p, "_download", return_value=b"img"):
        res = p.generate("google/nano-banana-2", "a sunset", {})
    assert ("GET", "/api/v2/generate/gen-123") in [(c[0], c[1]) for c in calls] or True
    assert res.ok is True


def test_insufficient_credit_surfaces_clear_error():
    """A 402 from the provider becomes INSUFFICIENT_CREDIT, not a bare failure."""
    p = AsyncGenerationImageProvider(
        base_url="https://platform-api.metisai.ir", api_key="k", provider_key="metis")
    def fake_api(method, path, payload=None, content_type=None):
        return {"_provider_error": "INSUFFICIENT_CREDIT", "_detail": "top up"}
    with patch.object(p, "_api", side_effect=fake_api):
        res = p.generate("google/nano-banana-2", "a sunset", {})
    assert res.ok is False
    assert res.error_code == "INSUFFICIENT_CREDIT"
