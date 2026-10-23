"""Configuration classes for MediDispatch GH.

Three environments are supported:

* ``DevelopmentConfig`` – SQLite, no Redis required, verbose logging.
* ``ProductionConfig``  – PostgreSQL + Redis, secure cookies, refuses to boot
  without real secrets.
* ``TestingConfig``     – in-memory SQLite, AI disabled by default, background
  jobs off.

Every value can be overridden with an environment variable of the same name.
"""

from __future__ import annotations

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class BaseConfig:
    """Settings shared by every environment."""

    APP_NAME = "MediDispatch GH"

    # --- Core secrets -------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    # Comma-separated list of Fernet keys. The FIRST key encrypts; all keys
    # decrypt, which allows zero-downtime key rotation.
    FIELD_ENCRYPTION_KEYS = os.environ.get("FIELD_ENCRYPTION_KEYS", "")

    # --- Database -----------------------------------------------------------
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Sessions / cookies -------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(hours=12)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # --- CSRF ---------------------------------------------------------------
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # tied to session lifetime instead

    # --- Real-time ----------------------------------------------------------
    REDIS_URL = os.environ.get("REDIS_URL", "")
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE") or None

    # --- AI harness (Ollama, Qwen 2.5 3B) ----------------------------------
    AI_ENABLED = _env_bool("AI_ENABLED", True)
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    OLLAMA_CONNECT_TIMEOUT = float(os.environ.get("OLLAMA_CONNECT_TIMEOUT", 2.0))
    OLLAMA_READ_TIMEOUT = float(os.environ.get("OLLAMA_READ_TIMEOUT", 12.0))
    # After this many consecutive failures, skip the AI for the cooldown
    # window so an outage never adds latency to every triage.
    AI_CIRCUIT_FAILURE_THRESHOLD = _env_int("AI_CIRCUIT_FAILURE_THRESHOLD", 3)
    AI_CIRCUIT_COOLDOWN_SECONDS = _env_int("AI_CIRCUIT_COOLDOWN_SECONDS", 60)

    # --- Media --------------------------------------------------------------
    MEDIA_RETENTION_DAYS = _env_int("MEDIA_RETENTION_DAYS", 30)
    MEDIA_MAX_BYTES = _env_int("MEDIA_MAX_BYTES", 6 * 1024 * 1024)
    MEDIA_MAX_PER_EMERGENCY = _env_int("MEDIA_MAX_PER_EMERGENCY", 5)
    MEDIA_MAX_DIMENSION = _env_int("MEDIA_MAX_DIMENSION", 1600)
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # hard request ceiling
    MEDIA_PURGE_INTERVAL_SECONDS = _env_int("MEDIA_PURGE_INTERVAL_SECONDS", 3600)
    BACKGROUND_JOBS_ENABLED = _env_bool("BACKGROUND_JOBS_ENABLED", True)

    # --- Civilian app -------------------------------------------------------
    CIVILIAN_TOKEN_HOURS = _env_int("CIVILIAN_TOKEN_HOURS", 24)
    CIVILIAN_PING_MIN_SECONDS = _env_int("CIVILIAN_PING_MIN_SECONDS", 4)
    CIVILIAN_REPORTS_PER_IP_PER_10MIN = _env_int("CIVILIAN_REPORTS_PER_IP_PER_10MIN", 6)
    EMERGENCY_NUMBER = os.environ.get("EMERGENCY_NUMBER", "112")

    # --- Auth ---------------------------------------------------------------
    LOGIN_MAX_FAILURES = _env_int("LOGIN_MAX_FAILURES", 5)
    LOGIN_LOCKOUT_MINUTES = _env_int("LOGIN_LOCKOUT_MINUTES", 15)
    PASSWORD_MIN_LENGTH = _env_int("PASSWORD_MIN_LENGTH", 10)

    # --- Privacy ------------------------------------------------------------
    # Super admins run the system; by default they cannot open patient records
    # (data minimisation under the Ghana Data Protection Act, 2012 – Act 843).
    ADMIN_CAN_VIEW_PATIENT_DATA = _env_bool("ADMIN_CAN_VIEW_PATIENT_DATA", False)
    # Hospitals see non-identifying summaries of unassigned reports within
    # this radius so they can prepare.
    HOSPITAL_NEARBY_RADIUS_KM = float(os.environ.get("HOSPITAL_NEARBY_RADIUS_KM", 60))

    # --- Logging ------------------------------------------------------------
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))
    LOG_TO_FILE = _env_bool("LOG_TO_FILE", True)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "medidispatch_dev.db")
    )
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")
    # The dev server is not monkey-patched, so never let Socket.IO auto-pick
    # eventlet here. Production sets SOCKETIO_ASYNC_MODE=eventlet explicitly.
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE") or "threading"


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    # A fixed, valid Fernet key used only by the test-suite.
    FIELD_ENCRYPTION_KEYS = "q3m5pQ0r9nJc4o5pX8yQ1uS0h7mVnW2bZ3cD4eF5gH0="
    # Set TEST_DATABASE_URL to run the suite against PostgreSQL.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False  # individual tests switch it back on
    AI_ENABLED = False
    BACKGROUND_JOBS_ENABLED = False
    LOG_TO_FILE = False
    LOGIN_LOCKOUT_MINUTES = 15
    CIVILIAN_PING_MIN_SECONDS = 0
    CIVILIAN_REPORTS_PER_IP_PER_10MIN = 1000
    SOCKETIO_ASYNC_MODE = "threading"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280, "pool_size": 10}
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PREFERRED_URL_SCHEME = "https"

    @classmethod
    def validate(cls) -> None:
        """Refuse to start production with missing or placeholder secrets."""
        problems = []
        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32 or "change-me" in cls.SECRET_KEY:
            problems.append("SECRET_KEY must be set to a real random value (>= 32 chars)")
        if not cls.FIELD_ENCRYPTION_KEYS:
            problems.append("FIELD_ENCRYPTION_KEYS must be set (Fernet key)")
        if not cls.SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
            problems.append("DATABASE_URL must point at PostgreSQL in production")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}