"""Central configuration for the Nourai backend.

Every setting comes from environment variables (see .env.example).
No secrets are hardcoded here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass
class Config:
    # --- runtime ---
    app_env: str = field(default_factory=lambda: _get("APP_ENV", "development"))
    secret_key: str = field(default_factory=lambda: _get("SECRET_KEY", "dev-secret-key"))
    database_url: str = field(
        default_factory=lambda: _get(
            "DATABASE_URL", "sqlite:///:memory:"
        )
    )
    redis_url: str = field(default_factory=lambda: _get("REDIS_URL", "redis://localhost:6379/0"))

    # --- web ---
    frontend_origin: str = field(default_factory=lambda: _get("FRONTEND_ORIGIN", "http://localhost:3000"))
    cookie_domain: str = field(default_factory=lambda: _get("COOKIE_DOMAIN", ""))

    # --- storage (S3-compatible) ---
    storage_endpoint: str = field(default_factory=lambda: _get("STORAGE_ENDPOINT", ""))
    storage_bucket: str = field(default_factory=lambda: _get("STORAGE_BUCKET", "nourai"))
    storage_region: str = field(default_factory=lambda: _get("STORAGE_REGION", "us-east-1"))
    storage_access_key: str = field(default_factory=lambda: _get("STORAGE_ACCESS_KEY", ""))
    storage_secret_key: str = field(default_factory=lambda: _get("STORAGE_SECRET_KEY", ""))

    # --- sms ---
    sms_provider: str = field(default_factory=lambda: _get("SMS_PROVIDER", "fake"))
    smsir_api_key: str = field(default_factory=lambda: _get("SMSIR_API_KEY", ""))
    smsir_template_id: str = field(default_factory=lambda: _get("SMSIR_TEMPLATE_ID", ""))
    smsir_api_base_url: str = field(default_factory=lambda: _get("SMSIR_API_BASE_URL", ""))
    # Name of the OTP placeholder inside the sms.ir pattern (e.g. "Code" for #CODE#).
    smsir_param_name: str = field(default_factory=lambda: _get("SMSIR_PARAM_NAME", "Code"))

    # --- payments ---
    payment_provider: str = field(default_factory=lambda: _get("PAYMENT_PROVIDER", "fake"))
    zibal_merchant: str = field(default_factory=lambda: _get("ZIBAL_MERCHANT", ""))
    zibal_api_base_url: str = field(default_factory=lambda: _get("ZIBAL_API_BASE_URL", ""))
    zibal_callback_url: str = field(default_factory=lambda: _get("ZIBAL_CALLBACK_URL", ""))

    # --- ai providers ---
    ai_text_provider: str = field(default_factory=lambda: _get("AI_TEXT_PROVIDER", "fake"))
    ai_audio_provider: str = field(default_factory=lambda: _get("AI_AUDIO_PROVIDER", "fake"))
    ai_image_provider: str = field(default_factory=lambda: _get("AI_IMAGE_PROVIDER", "fake"))

    def ai_provider_credentials(self, provider_key: str | None) -> tuple[str, str]:
        """Return ``(base_url, api_key)`` for a provider key like ``"metis"``.

        Provider-agnostic: credentials come from
        ``AI_PROVIDER_<KEY>_BASE_URL`` / ``AI_PROVIDER_<KEY>_API_KEY``,
        falling back to the generic ``AI_TEXT_BASE_URL`` / ``AI_TEXT_API_KEY``.
        Adding a new provider is env-only — no code change.
        """
        key = (provider_key or "").strip().upper()
        base_url = _get(f"AI_PROVIDER_{key}_BASE_URL") if key else ""
        api_key = _get(f"AI_PROVIDER_{key}_API_KEY") if key else ""
        if not base_url:
            base_url = _get("AI_TEXT_BASE_URL")
        if not api_key:
            api_key = _get("AI_TEXT_API_KEY")
        return base_url, api_key
    ai_provider_api_key: str = field(default_factory=lambda: _get("AI_PROVIDER_API_KEY", ""))

    # --- image hard ceilings (security; admin settings can never exceed these) ---
    image_upload_hard_max_bytes: int = field(default_factory=lambda: _get_int("IMAGE_UPLOAD_HARD_MAX_BYTES", 10 * 1024 * 1024))
    image_input_hard_max_pixels: int = field(default_factory=lambda: _get_int("IMAGE_INPUT_HARD_MAX_PIXELS", 16 * 1024 * 1024))
    image_input_hard_max_width: int = field(default_factory=lambda: _get_int("IMAGE_INPUT_HARD_MAX_WIDTH", 8192))
    image_input_hard_max_height: int = field(default_factory=lambda: _get_int("IMAGE_INPUT_HARD_MAX_HEIGHT", 8192))
    image_processing_timeout_seconds: int = field(default_factory=lambda: _get_int("IMAGE_PROCESSING_TIMEOUT_SECONDS", 120))

    # --- misc ---
    tiktoken_cache_dir: str = field(default_factory=lambda: _get("TIKTOKEN_CACHE_DIR", "/tmp/tiktoken-cache"))
    admin_bootstrap_username: str = field(default_factory=lambda: _get("ADMIN_BOOTSTRAP_USERNAME", ""))
    admin_bootstrap_password: str = field(default_factory=lambda: _get("ADMIN_BOOTSTRAP_PASSWORD", ""))

    # --- derived / operational defaults (not secret) ---
    brand_name_fa: str = "نورا"
    brand_name_en: str = "Nourai"

    otp_length: int = 5
    otp_ttl_seconds: int = 180
    otp_max_attempts: int = 5
    otp_request_cooldown_seconds: int = 60

    jwt_access_ttl_seconds: int = 900          # 15 minutes
    jwt_refresh_ttl_seconds: int = 30 * 24 * 3600  # 30 days

    rate_limit_otp_request: int = 5            # per window
    rate_limit_otp_request_window: int = 600   # 10 minutes
    rate_limit_otp_verify: int = 10
    rate_limit_otp_verify_window: int = 600
    rate_limit_admin_login: int = 10
    rate_limit_admin_login_window: int = 600
    rate_limit_ai_request: int = 60
    rate_limit_ai_request_window: int = 60

    payment_min_irr: int = 100_000            # 10,000 toman
    payment_max_irr: int = 100_000_000        # 10,000,000 toman

    audio_upload_max_bytes: int = 25 * 1024 * 1024
    audio_max_duration_seconds: int = 300
    audio_allowed_mime_types: tuple = ("audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
                                       "audio/ogg", "audio/webm", "audio/mp4", "audio/m4a")

    gallery_public_limit: int = 20
    signed_url_ttl_seconds: int = 3600

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def cookie_secure(self) -> bool:
        # Secure cookies require HTTPS; only enforce in production.
        return self.is_production

    @property
    def sqlalchemy_database_uri(self) -> str:
        return self.database_url

    def validate(self) -> None:
        """Fail fast on dangerous misconfiguration."""
        if self.is_production:
            if not self.secret_key or self.secret_key in {"dev-secret-key", "change-me"}:
                raise RuntimeError("SECRET_KEY must be set to a strong value in production")
            if self.sms_provider == "fake":
                raise RuntimeError("SMS_PROVIDER=fake is not allowed in production")
            if self.payment_provider == "fake":
                raise RuntimeError("PAYMENT_PROVIDER=fake is not allowed in production")


config = Config()
