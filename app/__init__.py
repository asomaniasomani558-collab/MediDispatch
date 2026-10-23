"""MediDispatch GH - application factory."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import click
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import CONFIG_BY_NAME, ProductionConfig
from .extensions import csrf, db, login_manager, socketio

log = logging.getLogger(__name__)
_socket_handlers_registered = False


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    config_name = config_name or os.environ.get("APP_ENV", "development")
    if config_name not in CONFIG_BY_NAME:
        raise ValueError(f"Unknown config '{config_name}'")
    config_cls = CONFIG_BY_NAME[config_name]
    if config_cls is ProductionConfig:
        ProductionConfig.validate()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_cls)
    app.config["ENV_NAME"] = config_name
    if overrides:
        app.config.update(overrides)
    os.makedirs(app.instance_path, exist_ok=True)

    from .services.logbuffer import configure_logging
    configure_logging(app)

    if config_name == "production":
        # Trust exactly one proxy hop (Nginx) for client IP / scheme.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _init_extensions(app)
    _register_blueprints(app)
    _register_security_headers(app)
    _register_error_handlers(app)
    _register_template_helpers(app)
    _register_cli(app)

    log.info("MediDispatch GH started (%s)", config_name)
    return app


def _init_extensions(app: Flask) -> None:
    from . import models  # noqa: F401 - registers tables
    from .services import ai, encryption
    from .services.security import limiter

    encryption.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    # Handlers must be registered BEFORE the first init_app: Flask-SocketIO
    # keeps pre-registered handlers and re-attaches them to every server it
    # creates, whereas handlers added later bind only to the current server.
    global _socket_handlers_registered
    if not _socket_handlers_registered:
        from .services.realtime import register_handlers
        register_handlers()
        _socket_handlers_registered = True
    socketio.init_app(
        app,
        message_queue=app.config.get("REDIS_URL") or None,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE"),
        cors_allowed_origins=None,  # same-origin only
        manage_session=False,       # share Flask-Login's session
    )
    ai.init_app(app)
    limiter.init_app(app)

    from .models.user import User

    @login_manager.user_loader
    def _load_user(user_id: str):
        try:
            raw_id, nonce = user_id.split(":", 1)
            user = db.session.get(User, int(raw_id))
        except (ValueError, TypeError):
            return None
        if user is None or not user.is_enabled or user.session_nonce != nonce:
            return None
        return user


def _register_blueprints(app: Flask) -> None:
    from .blueprints.admin import bp as admin_bp
    from .blueprints.api import bp as api_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.civilian import bp as civilian_bp
    from .blueprints.hospital import bp as hospital_bp
    from .blueprints.paramedic import bp as paramedic_bp

    for bp in (auth_bp, civilian_bp, paramedic_bp, hospital_bp, admin_bp, api_bp):
        app.register_blueprint(bp)

    @app.route("/")
    def index():
        return render_template("landing.html")


def _register_security_headers(app: Flask) -> None:
    csp = "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "connect-src 'self' ws: wss:",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "manifest-src 'self'",
        "worker-src 'self'",
    ])

    @app.after_request
    def _headers(response):
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Never let browsers or proxies cache anything carrying patient data.
        if not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _wants_json() -> bool:
    return (request.path.startswith("/api/") or "/api/" in request.path
            or request.is_json or request.accept_mimetypes.best == "application/json")


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def _csrf_error(err):
        if _wants_json():
            return jsonify(error="Security token expired - reload the page.", code="csrf"), 400
        return render_template("errors/error.html", code=400,
                               message="Your security token expired. Please go back and try again."), 400

    @app.errorhandler(HTTPException)
    def _http_error(err):
        if _wants_json():
            return jsonify(error=err.description or err.name), err.code
        return render_template("errors/error.html", code=err.code, message=err.description), err.code

    @app.errorhandler(Exception)
    def _unhandled(err):
        # Last line of defence: log it, roll back, show a calm error - never crash.
        log.exception("Unhandled error on %s %s", request.method, request.path)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        if _wants_json():
            return jsonify(error="Internal error - the incident has been logged. If urgent, call 112."), 500
        return render_template("errors/error.html", code=500,
                               message="Something went wrong. If this is an emergency, call 112 now."), 500


def _register_template_helpers(app: Flask) -> None:
    from .models.base import utcnow
    from .models.emergency import SITUATIONS, STATUSES

    @app.context_processor
    def _globals():
        return {
            "APP_NAME": app.config["APP_NAME"],
            "EMERGENCY_NUMBER": app.config["EMERGENCY_NUMBER"],
            "SITUATIONS": SITUATIONS,
            "STATUSES": STATUSES,
        }

    @app.template_filter("dt")
    def _dt(value: datetime | None, fmt: str = "%d %b %H:%M"):
        return value.strftime(fmt) if value else "-"

    @app.template_filter("ago")
    def _ago(value: datetime | None):
        if not value:
            return "-"
        secs = int((utcnow() - value).total_seconds())
        if secs < 60:
            return f"{max(secs, 0)}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"

    @app.template_filter("sevclass")
    def _sevclass(severity: str | None):
        return f"sev-{(severity or 'none').lower()}"


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create all tables (and the PostgreSQL audit trigger)."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("purge-media")
    def purge_media_cmd():
        """Delete photos older than MEDIA_RETENTION_DAYS."""
        from .services.media import purge_expired
        click.echo(f"Purged {purge_expired()} expired photo(s).")

    @app.cli.command("generate-key")
    def generate_key_cmd():
        """Print a new Fernet key for FIELD_ENCRYPTION_KEYS."""
        from .services.encryption import generate_key
        click.echo(generate_key())

    @app.cli.command("verify-audit")
    def verify_audit_cmd():
        """Verify the audit-log hash chain."""
        from .services.audit import verify_chain
        result = verify_chain()
        click.echo(result)
        if not result["ok"]:
            raise SystemExit(1)


def start_background_jobs(app: Flask) -> None:
    """Start periodic jobs (media retention). Called by run.py / wsgi.py."""
    if not app.config.get("BACKGROUND_JOBS_ENABLED"):
        return
    from .services.media import start_purge_loop
    start_purge_loop(app, socketio)
