"""Prompt blocklist matching.

- Persian text is normalized first (Arabic kaf/yeh/teh-marbuta -> Persian,
  ZWNJ/tatweel/diacritics stripped, whitespace collapsed) so trivial
  obfuscation (extra spaces, ZWNJ, Arabic letters) does not bypass it.
- ASCII phrases match case-insensitively as substrings (``sex`` also hits
  ``sexy``/``sexual``).
- Non-ASCII phrases match on word boundaries so innocent Persian words
  containing a blocked substring are not flagged.
"""
from __future__ import annotations

import re
import unicodedata

# Arabic -> Persian character map.
_FA_MAP = str.maketrans({
    "ك": "ک",  # Arabic kaf
    "ي": "ی",  # Arabic yeh
    "ى": "ی",  # Alef maksura
    "ة": "ه",  # Teh marbuta
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "آ": "ا",
})

# ZWNJ (U+200C), tatweel (U+0640), Arabic diacritics (U+064B-U+0652, U+0670).
_STRIP_RE = re.compile("[\u200c\u0640\u064b-\u0652\u0670]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_FA_MAP)
    text = _STRIP_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text.casefold()


def _phrase_pattern(phrase: str) -> "re.Pattern[str]":
    norm = normalize_text(phrase)
    escaped = re.escape(norm)
    if norm.isascii():
        return re.compile(escaped)
    # Word-boundary match for non-ASCII (Persian etc.).
    return re.compile(r"(?<!\w)" + escaped + r"(?!\w)")


def find_blocked_phrase(session, prompt: str) -> str | None:
    """Return the first active blocklisted phrase found in prompt, else None.

    Returns None immediately when the global kill switch is off.
    """
    from app.models.moderation import ModerationSettings, PromptBlocklist

    settings = (
        session.query(ModerationSettings)
        .order_by(ModerationSettings.created_at)
        .first()
    )
    if settings is not None and not settings.prompt_filter_enabled:
        return None

    phrases = (
        session.query(PromptBlocklist)
        .filter_by(is_active=True)
        .order_by(PromptBlocklist.created_at)
        .all()
    )
    if not phrases:
        return None
    text = normalize_text(prompt)
    for row in phrases:
        if not row.phrase or not row.phrase.strip():
            continue
        if _phrase_pattern(row.phrase).search(text):
            return row.phrase
    return None
