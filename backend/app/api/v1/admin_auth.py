"""Admin authentication: username/password login with Argon2id."""
from __future__ import annotations

import logging

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError

from app.api.deps import (
    client_ip,
    ensure_csrf_cookie,
    error_response,
    ip_hash,
    admin_required,
    rate_limited,
    success_response,
    utcnow,
    validation_error,
)
from app.auth.sessions import (
    TokenError,
    clear_session_cookies,
    decode_token,
    revoke_refresh_token,
    set_session_cookies,
)
from app.config import config
from app.extensions import db
from app.models import AdminUser
from app.services.audit import audit

log = logging.getLogger(__name__)
_ph = PasswordHasher()

bp = Blueprint("admin_auth", __name__)


class AdminLoginSchema(BaseModel):
    username: str
    password: str


@bp.post("/admin/auth/login")
def admin_login():
    try:
        data = AdminLoginSchema(**(request.get_json(silent=True) or {}))
    except ValidationError:
        return validation_error()

    ip = client_ip()
    if rate_limited(f"admin:login:{ip_hash(ip)}", config.rate_limit_admin_login,
                    config.rate_limit_admin_login_window):
        return error_response("RATE_LIMITED", status=429)

    admin = db.session.query(AdminUser).filter_by(username=data.username.strip()).one_or_none()
    ok = False
    if admin is not None and admin.is_active:
        try:
            ok = _ph.verify(admin.password_hash, data.password)
        except VerifyMismatchError:
            ok = False
        except Exception:  # noqa: BLE001 - corrupt hash etc.
            log.exception("password hash verification failed")
            ok = False

    audit(
        db.session,
        actor_type="admin",
        actor_id=admin.id if admin else None,
        action="admin.login.success" if ok and admin else "admin.login.failed",
        metadata={"username": data.username.strip()},
        ip_hash=ip_hash(ip),
    )
    db.session.commit()

    if not ok or admin is None:
        # Neutral timing/response: do not reveal which part failed.
        return error_response("UNAUTHORIZED", status=401)

    admin.last_login_at = utcnow()
    db.session.commit()
    log.info("admin login: %s", admin.username)
    response = success_response({"id": admin.id, "username": admin.username})
    set_session_cookies(response, admin.id, "admin")
    return ensure_csrf_cookie(response, admin=True)


@bp.post("/admin/auth/refresh")
def admin_refresh():
    from app.auth.sessions import ADMIN_REFRESH_COOKIE

    token = request.cookies.get(ADMIN_REFRESH_COOKIE)
    if not token:
        return error_response("UNAUTHORIZED", status=401)
    try:
        claims = decode_token(token, expected_type="refresh", expected_kind="admin")
    except TokenError:
        return error_response("UNAUTHORIZED", status=401)
    admin = db.session.get(AdminUser, claims["sub"])
    if admin is None or not admin.is_active:
        return error_response("UNAUTHORIZED", status=401)
    revoke_refresh_token("admin", claims["jti"])
    response = success_response({"refreshed": True})
    set_session_cookies(response, admin.id, "admin")
    return ensure_csrf_cookie(response, admin=True)


@bp.post("/admin/auth/logout")
def admin_logout():
    from app.auth.sessions import ADMIN_REFRESH_COOKIE

    token = request.cookies.get(ADMIN_REFRESH_COOKIE)
    if token:
        try:
            claims = decode_token(token, expected_type="refresh", expected_kind="admin")
            revoke_refresh_token("admin", claims["jti"])
        except TokenError:
            pass
    response = success_response({"logged_out": True})
    return clear_session_cookies(response, "admin")


@bp.get("/admin/me")
@admin_required
def admin_me():
    admin = g.current_admin
    return success_response({"id": admin.id, "username": admin.username})
