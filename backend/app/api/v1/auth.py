"""User authentication: OTP request/verify, session refresh/logout, /me."""
from __future__ import annotations

import logging
from datetime import timedelta

from flask import Blueprint, g, request
from pydantic import BaseModel, ValidationError

from app.api.deps import (
    client_ip,
    ensure_csrf_cookie,
    error_response,
    ip_hash,
    login_required,
    rate_limited,
    success_response,
    utcnow,
    validation_error,
)
from app.auth.otp import generate_code, hash_code, mask_mobile, normalize_mobile, verify_code
from app.auth.sessions import (
    TokenError,
    clear_session_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_refresh_token,
    set_session_cookies,
)
from app.billing.ledger import get_wallet_for_update
from app.config import config
from app.extensions import db
from app.models import OtpChallenge, User
from app.providers import get_sms_provider
from app.services.audit import audit

log = logging.getLogger(__name__)

bp = Blueprint("auth", __name__)


class OtpRequestSchema(BaseModel):
    mobile: str


class OtpVerifySchema(BaseModel):
    mobile: str
    code: str


def _parse(schema_cls, payload: dict):
    try:
        return schema_cls(**payload), None
    except ValidationError:
        return None, validation_error()


@bp.get("/csrf")
def get_csrf():
    response = success_response({"csrf": True})
    return ensure_csrf_cookie(response)


@bp.post("/auth/otp/request")
def otp_request():
    data, err = _parse(OtpRequestSchema, request.get_json(silent=True) or {})
    if err:
        return err
    try:
        mobile = normalize_mobile(data.mobile)
    except ValueError:
        return validation_error()

    ip = client_ip()
    if rate_limited(f"otp:req:{mobile}", config.rate_limit_otp_request, config.rate_limit_otp_request_window):
        return error_response("RATE_LIMITED", status=429)
    if rate_limited(f"otp:req:ip:{ip_hash(ip)}", config.rate_limit_otp_request * 4, config.rate_limit_otp_request_window):
        return error_response("RATE_LIMITED", status=429)

    # Cooldown between two codes for the same mobile.
    recent = (
        db.session.query(OtpChallenge)
        .filter_by(mobile_normalized=mobile, consumed_at=None)
        .order_by(OtpChallenge.created_at.desc())
        .first()
    )
    if recent and (utcnow() - recent.created_at) < timedelta(seconds=config.otp_request_cooldown_seconds):
        return error_response("RATE_LIMITED", status=429)

    code = generate_code(config.otp_length)
    challenge = OtpChallenge(
        mobile_normalized=mobile,
        purpose="login",
        code_hash=hash_code(code),
        expires_at=utcnow() + timedelta(seconds=config.otp_ttl_seconds),
        max_attempts=config.otp_max_attempts,
        request_ip_hash=ip_hash(ip),
    )
    db.session.add(challenge)
    db.session.commit()

    # NOTE: the raw code is never logged and never stored.
    try:
        result = get_sms_provider().send_otp(mobile, code)
    except Exception:  # noqa: BLE001 - provider misconfiguration etc.
        log.exception("sms provider failed for %s", mask_mobile(mobile))
        return error_response("PROVIDER_ERROR", status=502)
    if not result.ok:
        log.warning("sms send failed for %s: %s", mask_mobile(mobile), result.error_code)
        return error_response("PROVIDER_ERROR", status=502)

    log.info("otp requested for %s", mask_mobile(mobile))
    payload = {"sent": True}
    if (not config.is_production or config.allow_fake_sms) and result.dev_code:
        payload["dev_code"] = result.dev_code
    response = success_response(payload)
    return ensure_csrf_cookie(response)


@bp.post("/auth/otp/verify")
def otp_verify():
    data, err = _parse(OtpVerifySchema, request.get_json(silent=True) or {})
    if err:
        return err
    try:
        mobile = normalize_mobile(data.mobile)
    except ValueError:
        return validation_error()

    ip = client_ip()
    if rate_limited(f"otp:verify:{mobile}", config.rate_limit_otp_verify, config.rate_limit_otp_verify_window):
        return error_response("RATE_LIMITED", status=429)
    if rate_limited(f"otp:verify:ip:{ip_hash(ip)}", config.rate_limit_otp_verify * 4, config.rate_limit_otp_verify_window):
        return error_response("RATE_LIMITED", status=429)

    challenge = (
        db.session.query(OtpChallenge)
        .filter_by(mobile_normalized=mobile)
        .order_by(OtpChallenge.created_at.desc())
        .first()
    )
    now = utcnow()
    valid = (
        challenge is not None
        and challenge.consumed_at is None
        and challenge.expires_at > now
        and challenge.attempt_count < challenge.max_attempts
        and verify_code(data.code, challenge.code_hash)
    )
    if challenge is not None and challenge.consumed_at is None:
        challenge.attempt_count = (challenge.attempt_count or 0) + 1

    if not valid:
        db.session.commit()
        if challenge is not None and challenge.expires_at <= now and challenge.consumed_at is None:
            return error_response("OTP_EXPIRED", status=401)
        # Neutral: do not reveal whether the mobile exists.
        return error_response("OTP_INVALID", status=401)

    challenge.consumed_at = now

    user = db.session.query(User).filter_by(mobile_normalized=mobile).one_or_none()
    if user is None:
        user = User(mobile_normalized=mobile, mobile_verified_at=now)
        db.session.add(user)
        db.session.flush()
    if not user.is_active:
        db.session.commit()
        return error_response("USER_DISABLED", status=403)
    user.mobile_verified_at = user.mobile_verified_at or now
    user.last_login_at = now
    get_wallet_for_update(db.session, user.id)  # ensure wallet exists
    audit(
        db.session, actor_type="user", actor_id=user.id, action="user.login",
        metadata={"mobile": mask_mobile(mobile)}, ip_hash=ip_hash(ip),
    )
    db.session.commit()

    log.info("otp verified for %s", mask_mobile(mobile))
    response = success_response(_user_payload(user))
    set_session_cookies(response, user.id, "user")
    return ensure_csrf_cookie(response)


@bp.post("/auth/refresh")
def refresh():
    from app.auth.sessions import USER_REFRESH_COOKIE

    token = request.cookies.get(USER_REFRESH_COOKIE)
    if not token:
        return error_response("UNAUTHORIZED", status=401)
    try:
        claims = decode_token(token, expected_type="refresh", expected_kind="user")
    except TokenError:
        return error_response("UNAUTHORIZED", status=401)

    from app.models import User as UserModel

    user = db.session.get(UserModel, claims["sub"])
    if user is None or not user.is_active:
        return error_response("UNAUTHORIZED", status=401)

    revoke_refresh_token("user", claims["jti"])  # rotate
    response = success_response({"refreshed": True})
    set_session_cookies(response, user.id, "user")
    return ensure_csrf_cookie(response)


@bp.post("/auth/logout")
def logout():
    from app.auth.sessions import USER_REFRESH_COOKIE

    token = request.cookies.get(USER_REFRESH_COOKIE)
    if token:
        try:
            claims = decode_token(token, expected_type="refresh", expected_kind="user")
            revoke_refresh_token("user", claims["jti"])
        except TokenError:
            pass
    if hasattr(g, "current_user_id"):
        audit(db.session, actor_type="user", actor_id=g.current_user_id,
              action="user.logout", ip_hash=ip_hash(client_ip()))
        db.session.commit()
    response = success_response({"logged_out": True})
    return clear_session_cookies(response, "user")


@bp.get("/me")
@login_required
def me():
    return success_response(_user_payload(g.current_user))


def _user_payload(user: User) -> dict:
    from app.models.wallet import WalletAccount

    wallet = db.session.query(WalletAccount).filter_by(user_id=user.id).one_or_none()
    return {
        "id": user.id,
        "mobile_masked": mask_mobile(user.mobile_normalized),
        "is_active": user.is_active,
        "balance_irr": wallet.balance_irr if wallet else 0,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# Re-export for tests that decode tokens.
__all__ = ["bp", "create_access_token", "create_refresh_token"]
