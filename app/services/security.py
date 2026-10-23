"""RBAC decorators, civilian-token auth, rate limiting and input helpers."""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, g, jsonify, request
from flask_login import current_user

from ..models.emergency import CivilianSession

CIVILIAN_TOKEN_HEADER = "X-Civilian-Token"


# --- Role-based access control --------------------------------------------
def role_required(*roles: str):
    """Allow only signed-in staff whose role is in ``roles``.

    Anonymous users are sent to the login page; signed-in users with the wrong
    role get 403. A civilian token is never a login, so it can't pass.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path.startswith("/api/") or request.is_json \
                        or request.accept_mimetypes.best == "application/json":
                    return jsonify(error="authentication required"), 401
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def civilian_required(view):
    """Require a valid bystander bearer token (``X-Civilian-Token``)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        token = request.headers.get(CIVILIAN_TOKEN_HEADER, "")
        session = CivilianSession.from_token(token)
        if session is None:
            return jsonify(error="Your report session has expired. Please call 112."), 401
        g.civilian_session = session
        return view(*args, **kwargs)

    return wrapped


# --- Rate limiting ----------------------------------------------------------
class RateLimiter:
    """Sliding-window limiter. Uses Redis when configured, memory otherwise."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._redis = None

    def init_app(self, app) -> None:
        url = app.config.get("REDIS_URL")
        if url:
            try:
                import redis  # noqa: PLC0415

                self._redis = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
            except Exception:  # noqa: BLE001
                self._redis = None

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        if self._redis is not None:
            try:
                bucket = f"rl:{key}:{int(time.time() // window_seconds)}"
                pipe = self._redis.pipeline()
                pipe.incr(bucket)
                pipe.expire(bucket, window_seconds)
                count = pipe.execute()[0]
                return int(count) <= limit
            except Exception:  # noqa: BLE001 - Redis down: fall back to memory
                pass
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


limiter = RateLimiter()


# --- Input helpers ----------------------------------------------------------
_PHONE_CLEAN = re.compile(r"[\s\-().]")


def normalize_ghana_phone(raw: str | None) -> str | None:
    """Return E.164 (+233XXXXXXXXX) for a Ghanaian number, else ``None``.

    Accepts 0XXXXXXXXX, 233XXXXXXXXX and +233XXXXXXXXX. Foreign numbers in
    E.164 (+<country><number>, 8-15 digits) are accepted unchanged so visitors
    can still report.
    """
    if not raw:
        return None
    phone = _PHONE_CLEAN.sub("", raw.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if re.fullmatch(r"0[2-5]\d{8}", phone):
        return "+233" + phone[1:]
    if re.fullmatch(r"233[2-5]\d{8}", phone):
        return "+" + phone
    if re.fullmatch(r"\+233[2-5]\d{8}", phone):
        return phone
    if re.fullmatch(r"\+[1-9]\d{7,14}", phone) and not phone.startswith("+233"):
        return phone
    return None


def clean_name(raw: str | None, max_len: int = 80) -> str | None:
    if not raw:
        return None
    name = " ".join(str(raw).split())
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:max_len] or None


def parse_coords(lat, lon, acc=None) -> dict | None:
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return None
    loc = {"lat": round(lat_f, 6), "lon": round(lon_f, 6)}
    try:
        if acc is not None:
            loc["acc"] = max(0, min(100000, int(float(acc))))
    except (TypeError, ValueError):
        pass
    return loc
