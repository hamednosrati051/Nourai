"""Shared API helpers: envelope, error codes, auth decorators, pagination,
rate limiting and CSRF protection."""
from __future__ import annotations

import functools
import hashlib
import secrets
from datetime import datetime

from flask import Response, g, jsonify, request

from app.auth.sessions import (
    ADMIN_CSRF_COOKIE,
    USER_CSRF_COOKIE,
    decode_token,
)
from app.config import config
from app.extensions import db, redis_client

# ---------------------------------------------------------------------------
# Error codes (Persian user-facing messages, per spec section 17)
# ---------------------------------------------------------------------------
ERROR_MESSAGES: dict[str, str] = {
    "VALIDATION_ERROR": "ورودی نامعتبر است.",
    "UNAUTHORIZED": "احراز هویت لازم است. لطفاً دوباره وارد شوید.",
    "FORBIDDEN": "دسترسی مجاز نیست.",
    "USER_DISABLED": "حساب کاربری شما غیرفعال شده است.",
    "RATE_LIMITED": "تعداد درخواست‌ها بیش از حد مجاز است. لطفاً کمی بعد تلاش کنید.",
    "INSUFFICIENT_BALANCE": "موجودی کیف پول کافی نیست.",
    "MODEL_UNAVAILABLE": "مدل در دسترس نیست.",
    "FILE_TOO_LARGE": "حجم فایل بیش از حد مجاز است.",
    "IMAGE_DIMENSIONS_EXCEEDED": "ابعاد تصویر بیش از حد مجاز است.",
    "UNSUPPORTED_IMAGE_TYPE": "نوع تصویر پشتیبانی نمی‌شود.",
    "IMAGE_PROCESSING_FAILED": "پردازش تصویر ناموفق بود.",
    "PRICING_RULE_UNAVAILABLE": "تعرفه‌ای برای این مدل یافت نشد.",
    "TOKENIZER_UNAVAILABLE": "توکنایزر در دسترس نیست.",
    "PAYMENT_VERIFICATION_FAILED": "تأیید پرداخت ناموفق بود.",
    "PAYMENT_AMOUNT_MISMATCH": "مبلغ پرداخت با رکورد داخلی مطابقت ندارد.",
    "PROVIDER_ERROR": "خطای سرویس‌دهنده. لطفاً بعداً تلاش کنید.",
    "OTP_INVALID": "کد واردشده صحیح نیست.",
    "OTP_EXPIRED": "کد منقضی شده است. لطفاً کد جدید درخواست کنید.",
    "CSRF_INVALID": "توکن امنیتی نامعتبر است.",
    "PAYMENT_REQUIRED": "پرداخت لازم است.",
    "PLAN_LIMIT_EXCEEDED": "سقف مصرف دوره‌ای پلن شما به پایان رسیده است.",
    "NOT_FOUND": "یافت نشد.",
    "CONFLICT": "رکورد تکراری است.",
    "METHOD_NOT_ALLOWED": "روش درخواست مجاز نیست.",
    "INTERNAL_ERROR": "خطای داخلی سرور.",
}


def success_response(data=None, meta: dict | None = None, status: int = 200):
    payload = {
        "data": data,
        "meta": meta or {},
        "request_id": g.get("request_id", ""),
    }
    # Return a real Response (not a tuple) so callers can set cookies on it
    # before returning (login / refresh / CSRF flows).
    resp = jsonify(payload)
    resp.status_code = status
    return resp


def error_response(code: str, message: str | None = None, status: int = 400):
    payload = {
        "error": {"code": code, "message": message or ERROR_MESSAGES.get(code, "خطا.")},
        "request_id": g.get("request_id", ""),
    }
    return jsonify(payload), status


def validation_error(details: dict | None = None):
    # details are intentionally not echoed back; they may contain raw input.
    return error_response("VALIDATION_ERROR", status=422)


# ---------------------------------------------------------------------------
# Pagination (page / page_size, max 100 everywhere)
# ---------------------------------------------------------------------------
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def pagination_params() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.args.get("page_size", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page, page_size


def paginate_query(query, page: int, page_size: int):
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    meta = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }
    return items, meta


# ---------------------------------------------------------------------------
# Rate limiting (Redis fixed-window, in-memory fallback for tests)
# ---------------------------------------------------------------------------
def rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    count = redis_client.rate_limit_hit(f"rl:{key}", window_seconds)
    return count > limit


def rate_limit(key_fn, limit: int, window_seconds: int):
    """Decorator factory. key_fn() -> str identifies the bucket."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if rate_limited(key_fn(), limit, window_seconds):
                return error_response("RATE_LIMITED", status=429)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def ip_hash(ip: str) -> str:
    return hashlib.sha256(f"{ip}|{config.secret_key}".encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# CSRF: double-submit cookie. Required on state-changing API requests that
# carry a session, except the pre-session OTP endpoints (the login page
# fetches a token first from GET /api/v1/csrf).
# ---------------------------------------------------------------------------
CSRF_EXEMPT_PATHS = {
    "/api/v1/auth/otp/request",
    "/api/v1/auth/otp/verify",
    "/api/v1/admin/auth/login",
}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def ensure_csrf_cookie(response: Response, admin: bool = False) -> Response:
    cookie_name = ADMIN_CSRF_COOKIE if admin else USER_CSRF_COOKIE
    if not request.cookies.get(cookie_name):
        response.set_cookie(
            cookie_name,
            secrets.token_urlsafe(32),
            samesite="Lax",
            secure=config.cookie_secure,
            domain=config.cookie_domain or None,
            path="/",
            max_age=30 * 24 * 3600,
        )
    return response


def csrf_protect():
    if request.method in SAFE_METHODS or not request.path.startswith("/api/"):
        return None
    if request.path in CSRF_EXEMPT_PATHS:
        return None
    cookie_token = request.cookies.get(USER_CSRF_COOKIE) or request.cookies.get(ADMIN_CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token", "")
    # Only enforce when a session cookie is present; token-less public POSTs
    # (none currently) would otherwise be blocked without a way to get a token.
    from app.auth.sessions import (
        ADMIN_ACCESS_COOKIE,
        ADMIN_REFRESH_COOKIE,
        USER_ACCESS_COOKIE,
        USER_REFRESH_COOKIE,
    )

    has_session = any(
        request.cookies.get(c)
        for c in (USER_ACCESS_COOKIE, USER_REFRESH_COOKIE, ADMIN_ACCESS_COOKIE, ADMIN_REFRESH_COOKIE)
    )
    if not has_session:
        return None
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        return error_response("CSRF_INVALID", status=403)
    return None


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------
def _load_token(expected_kind: str):
    from app.auth.sessions import ADMIN_ACCESS_COOKIE, USER_ACCESS_COOKIE

    cookie_name = ADMIN_ACCESS_COOKIE if expected_kind == "admin" else USER_ACCESS_COOKIE
    token = request.cookies.get(cookie_name)
    if not token:
        return None, error_response("UNAUTHORIZED", status=401)
    try:
        claims = decode_token(token, expected_type="access", expected_kind=expected_kind)
    except Exception:  # noqa: BLE001 - any decode problem -> 401
        return None, error_response("UNAUTHORIZED", status=401)
    return claims, None


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        from app.models import User

        claims, err = _load_token("user")
        if err:
            return err
        user = db.session.get(User, claims["sub"])
        if user is None:
            return error_response("UNAUTHORIZED", status=401)
        if not user.is_active:
            return error_response("USER_DISABLED", status=403)
        invalidated_at = user.session_invalidated_at
        if invalidated_at is not None:
            issued_at = datetime.fromtimestamp(claims["iat"])
            if issued_at < invalidated_at:
                return error_response("UNAUTHORIZED", status=401)
        g.current_user = user
        g.current_user_id = user.id
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        from app.models import AdminUser

        claims, err = _load_token("admin")
        if err:
            return err
        admin = db.session.get(AdminUser, claims["sub"])
        if admin is None:
            return error_response("UNAUTHORIZED", status=401)
        if not admin.is_active:
            return error_response("FORBIDDEN", status=403)
        invalidated_at = admin.session_invalidated_at
        if invalidated_at is not None:
            issued_at = datetime.fromtimestamp(claims["iat"])
            if issued_at < invalidated_at:
                return error_response("UNAUTHORIZED", status=401)
        g.current_admin = admin
        g.current_admin_id = admin.id
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)

