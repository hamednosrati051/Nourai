"""Application factory for the Nourai backend."""
from __future__ import annotations

import logging
import uuid

from flask import Flask, g, request
from flask_cors import CORS

from app.api.deps import csrf_protect, error_response, success_response
from app.api.v1 import bp as api_v1_bp
from app.config import config
from app.extensions import db, redis_client


def _configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s"
        )
    )
    # request_id is injected via a logging adapter below; default to "-".
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        try:
            record.request_id = g.get("request_id", "-")
        except Exception:  # noqa: BLE001 - outside request context
            record.request_id = "-"
        return record

    logging.setLogRecordFactory(record_factory)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if config.is_production else logging.DEBUG)
    app.logger.handlers = [handler]


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = config.sqlalchemy_database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # MySQL: utf8mb4 + UTC. SQLite (tests): default.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    if test_config:
        app.config.update(test_config)

    config.validate()
    _configure_logging(app)
    app.logger.info("startup config: redis_url=%s db=%s", config.redis_url, config.database_url.split("@")[-1])
    redis_client.init(config.redis_url)

    db.init_app(app)

    CORS(
        app,
        resources={r"/api/*": {"origins": [config.frontend_origin]}},
        supports_credentials=True,
    )

    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex

    @app.before_request
    def _csrf() -> object | None:
        return csrf_protect()

    @app.after_request
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.get("/api/v1/health")
    def health():
        return success_response({"status": "ok", "brand": config.brand_name_en})

    app.register_blueprint(api_v1_bp)

    @app.errorhandler(404)
    def not_found(_e):
        return error_response("NOT_FOUND", "یافت نشد.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return error_response("METHOD_NOT_ALLOWED", "روش درخواست مجاز نیست.", 405)

    @app.errorhandler(500)
    def internal_error(_e):
        app.logger.exception("unhandled error")
        return error_response("INTERNAL_ERROR", "خطای داخلی سرور.", 500)

    # Import models so SQLAlchemy registers them; import tasks so Celery sees them.
    # NOTE: use "from app import x" (never "import app.x") here: the latter
    # would rebind the local name `app` to the package module.
    with app.app_context():
        from app import models  # noqa: F401
        from app import tasks  # noqa: F401

    # CLI commands
    from app.cli import register_cli

    register_cli(app)

    return app
