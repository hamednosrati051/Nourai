"""Token counting on top of tiktoken.

Rules (spec section 12):
- the encoding comes from ``ai_models.tokenizer_encoding`` and is validated
  with ``tiktoken.get_encoding()`` when the model is saved;
- there is NO silent runtime fallback: an unknown/unavailable encoding raises
  TokenizerUnavailable;
- chat-message overhead (role markers, message framing) is documented per
  provider adapter and passed in explicitly — never guessed inside the
  counter;
- the exact Unicode string sent to the provider (after the final payload is
  built) is what gets counted; the frontend is never the source of truth.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from functools import lru_cache

from app.config import config

log = logging.getLogger(__name__)

os.environ.setdefault("TIKTOKEN_CACHE_DIR", config.tiktoken_cache_dir)


# BPE data bundled with the repo so tiktoken works fully offline.
# tiktoken downloads the encoding file on first use; where the download host
# is unreachable the request would hang (or fail) instead of validating.
# The bundled files are copied into TIKTOKEN_CACHE_DIR on import, using the
# exact cache keys tiktoken itself uses, so no download is ever attempted.
_BUNDLED_ENCODINGS = {
    # encoding_name: (bpe_url, bundled_filename)
    "cl100k_base": (
        "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
        "cl100k_base.tiktoken",
    ),
}


def _seed_bundled_encodings() -> None:
    cache_dir = os.environ.get("TIKTOKEN_CACHE_DIR") or config.tiktoken_cache_dir
    if not cache_dir:
        return
    src_dir = os.path.join(os.path.dirname(__file__), "encodings")
    for _name, (url, filename) in _BUNDLED_ENCODINGS.items():
        src = os.path.join(src_dir, filename)
        if not os.path.isfile(src):
            continue
        # Same cache key tiktoken's read_file_cached() uses for this URL.
        dest = os.path.join(cache_dir, hashlib.sha1(url.encode()).hexdigest())
        if os.path.exists(dest):
            continue
        try:
            os.makedirs(cache_dir, exist_ok=True)
            shutil.copyfile(src, dest)
            log.info("seeded bundled tiktoken encoding: %s", filename)
        except OSError as exc:
            log.warning("could not seed bundled tiktoken encoding %s: %s", filename, exc)


_seed_bundled_encodings()


class TokenizerUnavailable(Exception):
    pass


@lru_cache(maxsize=32)
def _get_encoding(encoding_name: str):
    import tiktoken

    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception as exc:  # noqa: BLE001
        raise TokenizerUnavailable(
            f"tiktoken encoding not available: {encoding_name}"
        ) from exc


def validate_encoding(encoding_name: str) -> str:
    """Validate an encoding name at model-save time. Raises on failure."""
    if not encoding_name or not isinstance(encoding_name, str):
        raise TokenizerUnavailable("tokenizer_encoding is required for text models")
    _get_encoding(encoding_name.strip())
    return encoding_name.strip()


def suggest_encoding_for_model(model_name: str) -> str | None:
    """Best-effort suggestion for the admin UI only.

    Uses tiktoken's own mapping as a *suggestion* when the admin creates a
    model; the saved value is what the runtime uses, with no fallback.
    """
    try:
        import tiktoken

        return tiktoken.encoding_for_model(model_name).name
    except Exception:  # noqa: BLE001 - unknown model -> no suggestion
        return None


class TokenCounter:
    """Counts tokens for one fixed, validated encoding."""

    def __init__(self, encoding_name: str):
        self.encoding_name = validate_encoding(encoding_name)
        self._encoding = _get_encoding(self.encoding_name)

    def count_text(self, text: str) -> int:
        return len(self._encoding.encode(text or ""))

    def count_chat_messages(
        self,
        messages: list[dict],
        overhead_per_message: int,
        overhead_total: int = 0,
    ) -> int:
        """Count a chat payload including provider framing overhead.

        ``overhead_per_message`` / ``overhead_total`` are documented on the
        provider adapter in use (e.g. FakeTextProvider.OVERHEAD_*). When the
        real provider's framing is unknown, do NOT guess: reserve
        conservatively from max_output_tokens and settle with the provider's
        reported usage.
        """
        total = overhead_total
        for message in messages:
            total += overhead_per_message
            role = message.get("role", "")
            content = message.get("content", "")
            total += self.count_text(role)
            if isinstance(content, str):
                total += self.count_text(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += self.count_text(part.get("text", ""))
        return total
