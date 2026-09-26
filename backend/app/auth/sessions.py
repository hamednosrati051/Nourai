"""JWT session management.

- Short-lived access tokens + long-lived refresh tokens, both in HttpOnly,
  Secure, SameSite cookies. Tokens are never stored in localStorage.
- User and admin sessions use separate cookie names.
- Refresh token ids (jti) are tracked in Redis so logout/revocation works.
- Disabling a user/admin bumps ``session_invalidated_at``; access tokens
  issued before that instant are rejected (see api/deps.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import config
from app.extensions import redis_client

ALGORITHM = "HS256"

USER_ACCESS_COOKIE = "nourai_at"
USER_REFRESH_COOKIE = "nourai_rt"
USER_CSRF_COOKIE = "nourai_csrf"

ADMIN_ACCESS_COOKIE = "nourai_admin_at"
ADMIN_REFRESH_COOKIE = "nourai_admin_rt"
ADMIN_CSRF_COOKIE = "nourai_admin_csrf"


class TokenError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_jti() -> str:
    return uuid.uuid4().hex


def create_access_token(subject: str, kind: str) -> str:
    """kind: "user" | "admin"."""
    now = _now()
    payload = {
        "sub": subject,
        "kind": kind,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=config.jwt_access_ttl_seconds),
        "jti": _new_jti(),
    }
    return jwt.encode(payload, config.secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str, kind: str) -> tuple[str, str]:
    """Returns (token, jti). The jti is registered in Redis for revocation."""
    now = _now()
    jti = _new_jti()
    payload = {
        "sub": subject,
        "kind": kind,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(seconds=config.jwt_refresh_ttl_seconds),
        "jti": jti,
    }
    token = jwt.encode(payload, config.secret_key, algorithm=ALGORITHM)
    redis_client.setex(
        f"refresh:{kind}:{jti}", config.jwt_refresh_ttl_seconds, subject
    )
    return token, jti


def decode_token(token: str, expected_type: str, expected_kind: str) -> dict:
    try:
        claims = jwt.decode(token, config.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid") from exc
    if claims.get("type") != expected_type or claims.get("kind") != expected_kind:
        raise TokenError("type/kind mismatch")
    if expected_type == "refresh":
        stored = redis_client.get(f"refresh:{expected_kind}:{claims.get('jti')}")
        if stored is None or stored != claims.get("sub"):
            raise TokenError("revoked")
    return claims


def revoke_refresh_token(kind: str, jti: str) -> None:
    redis_client.delete(f"refresh:{kind}:{jti}")


def _cookie_kwargs(max_age: int, http_only: bool = True) -> dict:
    kwargs: dict = {
        "httponly": http_only,
        "secure": config.cookie_secure,
        "samesite": "Lax",
        "path": "/",
        "max_age": max_age,
    }
    if config.cookie_domain:
        kwargs["domain"] = config.cookie_domain
    return kwargs


def set_session_cookies(response, subject: str, kind: str):
    """Issue a fresh access+refresh pair and set the session cookies."""
    access = create_access_token(subject, kind)
    refresh, _jti = create_refresh_token(subject, kind)
    if kind == "admin":
        access_cookie, refresh_cookie = ADMIN_ACCESS_COOKIE, ADMIN_REFRESH_COOKIE
    else:
        access_cookie, refresh_cookie = USER_ACCESS_COOKIE, USER_REFRESH_COOKIE
    response.set_cookie(access_cookie, access, **_cookie_kwargs(config.jwt_access_ttl_seconds))
    response.set_cookie(refresh_cookie, refresh, **_cookie_kwargs(config.jwt_refresh_ttl_seconds))
    return response


def clear_session_cookies(response, kind: str):
    cookies = (
        (ADMIN_ACCESS_COOKIE, ADMIN_REFRESH_COOKIE, ADMIN_CSRF_COOKIE)
        if kind == "admin"
        else (USER_ACCESS_COOKIE, USER_REFRESH_COOKIE, USER_CSRF_COOKIE)
    )
    for name in cookies:
        response.delete_cookie(name, path="/", domain=config.cookie_domain or None)
    return response
