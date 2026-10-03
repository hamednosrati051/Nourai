"""Worker must not forward job width/height to the image provider as `size`.

Regression: job creation always stores width/height (from the processing
profile, e.g. 1024x1024) in parameters_json. The worker used to copy them
into provider options, and OpenAICompatImageProvider turned them into
`size=1024x1024` — which AvalAI's qwen image models reject with
400 invalid_request_format. The worker now strips dimensions; the
provider only sends `size` when explicitly dimensioned options arrive.
"""
from __future__ import annotations

from app.ai.adapters import OpenAICompatImageProvider
from app.tasks.image_tasks import _provider_options


def test_provider_options_exclude_dimensions():
    # Real-flow params: job creation always sets these from the profile.
    params = {"width": 1024, "height": 1024, "quality": None, "model_id": "m1"}
    options = _provider_options(params)
    assert "width" not in options
    assert "height" not in options
    # ... so the provider cannot build a `size` parameter from them.
    assert OpenAICompatImageProvider._size(options) is None


def test_provider_options_keep_quality():
    options = _provider_options({"width": 512, "height": 512, "quality": "hd"})
    assert options == {"quality": "hd"}
