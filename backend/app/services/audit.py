"""Audit log helper.

Every admin action and every sensitive user action is recorded with actor,
action, target and sanitised metadata. Secrets (passwords, OTP codes, API
keys, tokens) are stripped before anything is written.
"""
from __future__ import annotations

import logging

from app.models.audit import AuditLog

log = logging.getLogger(__name__)

_SENSITIVE_SUBSTRINGS = (
    "password", "secret", "token", "otp", "code", "api_key", "apikey",
    "merchant", "authorization",
)


def sanitise_metadata(metadata: dict | None) -> dict | None:
    if not metadata:
        return None
    clean: dict = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if any(s in lowered for s in _SENSITIVE_SUBSTRINGS):
            clean[key] = "***"
        else:
            clean[key] = value
    return clean


def audit(
    session,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict | None = None,
    ip_hash: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        metadata_json=sanitise_metadata(metadata),
        ip_hash=ip_hash,
    )
    session.add(entry)
    log.info(
        "audit actor=%s:%s action=%s target=%s:%s",
        actor_type, actor_id, action, target_type, target_id,
    )
    return entry
