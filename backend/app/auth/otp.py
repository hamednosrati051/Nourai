"""OTP helpers: Iranian mobile normalisation, code generation and hashing.

The raw OTP code is never stored: only its SHA-256 hash lives in the DB.
Codes are never logged; mobile numbers are masked in logs.
"""
from __future__ import annotations

import hashlib
import re
import secrets

# Persian / Arabic-Indic digits -> ASCII
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "0123456789" * 2,
)

_MOBILE_RE = re.compile(r"^09\d{9}$")


def normalize_mobile(raw: str) -> str:
    """Normalise an Iranian mobile number to ``09xxxxxxxxx``.

    - strips whitespace, dashes and other separators
    - converts Persian/Arabic-Indic digits to ASCII
    - converts +98 / 0098 / 98 prefixes to the leading 0

    Raises ValueError for anything that is not a valid Iranian mobile.
    """
    if not raw or not isinstance(raw, str):
        raise ValueError("mobile is required")
    cleaned = raw.translate(_DIGIT_TRANSLATION)
    cleaned = re.sub(r"[\s\-()]", "", cleaned)
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if cleaned.startswith("0098"):
        cleaned = "0" + cleaned[4:]
    elif cleaned.startswith("98") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    if not _MOBILE_RE.match(cleaned):
        raise ValueError("invalid Iranian mobile number")
    return cleaned


def mask_mobile(mobile: str) -> str:
    """Mask a mobile for logs: 09123456789 -> 0912***6789."""
    try:
        mobile = normalize_mobile(mobile)
    except ValueError:
        return "***"
    return f"{mobile[:4]}***{mobile[-4:]}"


def generate_code(length: int = 5) -> str:
    """Cryptographically secure numeric OTP code (returned once, never stored)."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    """Constant-time comparison of a candidate code against the stored hash."""
    if not code or not code_hash:
        return False
    candidate = hash_code(code.strip())
    return secrets.compare_digest(candidate, code_hash)
