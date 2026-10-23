"""Super Admin / Dev Portal.

* CRUD for hospitals (incl. beds & facilities) and staff accounts.
* System health: DB, Redis, Ollama model status/uptime, live WebSocket clients.
* System logs (in-memory ring buffer) and the append-only audit log viewer.

Admins manage the system but, by default, cannot open patient records
(``ADMIN_CAN_VIEW_PATIENT_DATA``).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user
from sqlalchemy import func, text

from ..extensions import db
from ..models.audit import AuditLog
from ..models.base import utcnow
from ..models.emergency import OPEN_STATUSES, Emergency
from ..models.hospital import FACILITIES, GHANA_REGIONS, LEVELS, SPECIALISTS, Hospital
from ..models.media import Media
from ..models.user import ROLE_HOSPITAL_ADMIN, ROLE_SUPER_ADMIN, ROLES, User
from ..services import audit, realtime
from ..services.ai import get_harness
from ..services.logbuffer import ring_buffer
from ..services.security import role_required
from ..services.triage import SEVERITY_ORDER

log = logging.getLogger(__name__)
bp = Blueprint("admin", __name__, url_prefix="/admin")

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")
_STARTED_AT = time.time()


@bp.before_request
@role_required(ROLE_SUPER_ADMIN)
def _guard():
    return None


# --- Health -----------------------------------------------------------------
def _redis_status() -> dict:
    url = current_app.config.get("REDIS_URL")
    if not url:
        return {"configured": False, "online": None}
    try:
        import redis  # noqa: PLC0415

        client = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
        started = time.monotonic()
        client.ping()
        return {"configured": True, "online": True, "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "online": False, "error": str(exc)[:160]}


def _db_status() -> dict:
    try:
        started = time.monotonic()
        db.session.execute(text("SELECT 1"))
        return {"online": True, "dialect": db.engine.dialect.name,
                "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return {"online": False, "error": str(exc)[:160]}


def system_health() -> dict:
    return {
        "app": {"uptime_seconds": int(time.time() - _STARTED_AT), "env": current_app.config["ENV_NAME"]},
        "database": _db_status(),
        "redis": _redis_status(),
        "ai": get_harness().check_health(),
        "websockets": {"count": realtime.connection_count(), "clients": realtime.active_connections()},
    }


def _stats() -> dict:
    open_q = Emergency.query.filter(Emergency.status.in_(OPEN_STATUSES))
    by_severity = dict(
        db.session.query(Emergency.severity, func.count(Emergency.id))
        .filter(Emergency.status.in_(OPEN_STATUSES)).group_by(Emergency.severity).all()
    )
    since = utcnow() - timedelta(hours=24)
    return {
        "open": open_q.count(),
        "unclaimed": Emergency.query.filter_by(status="reported").count(),
        "last_24h": Emergency.query.filter(Emergency.created_at >= since).count(),
        "by_severity": {s: by_severity.get(s, 0) for s in SEVERITY_ORDER},
        "untriaged": by_severity.get(None, 0),
        "hospitals_active": Hospital.query.filter_by(is_active=True).count(),
        "hospitals_full": Hospital.query.filter(Hospital.is_active.is_(True),
                                                Hospital.er_beds_available <= 0).count(),
        "staff_active": User.query.filter_by(is_enabled=True).count(),
        "photos_stored": Media.query.count(),
        "audit_entries": AuditLog.query.count(),
    }


@bp.route("/")
def dashboard():
    return render_template("admin/dashboard.html", health=system_health(), stats=_stats(),
                           logs=ring_buffer.recent(60, "INFO"))


@bp.route("/api/health")
def api_health():
    return jsonify(health=system_health(), stats=_stats())


@bp.route("/api/logs")
def api_logs():
    level = request.args.get("level", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    return jsonify(logs=ring_buffer.recent(300, level))


# --- Hospitals --------------------------------------------------------------
@bp.route("/hospitals")
def hospitals():
    items = Hospital.query.order_by(Hospital.region, Hospital.name).all()
    return render_template("admin/hospitals.html", hospitals=items)


def _hospital_from_form(h: Hospital) -> dict[str, str]:
    f = request.form
    errors: dict[str, str] = {}
    h.name = " ".join((f.get("name") or "").split())[:160]
    h.code = (f.get("code") or "").strip().upper()[:16]
    h.region = f.get("region") or ""
    h.district = (f.get("district") or "").strip()[:80] or None
    h.level = f.get("level") or "District"
    h.phone = (f.get("phone") or "").strip()[:32] or None
    if len(h.name) < 3:
        errors["name"] = "Name is required."
    if not re.fullmatch(r"[A-Z0-9-]{2,16}", h.code or ""):
        errors["code"] = "Code: 2-16 letters, digits or dashes."
    if h.region not in GHANA_REGIONS:
        errors["region"] = "Choose a region."
    if h.level not in LEVELS:
        errors["level"] = "Choose a level."
    for key, lo, hi in (("latitude", 4.5, 11.3), ("longitude", -3.4, 1.4)):
        try:
            value = float(f.get(key, ""))
            if not lo <= value <= hi:
                raise ValueError
            setattr(h, key, value)
        except ValueError:
            errors[key] = f"{key.title()} must be inside Ghana ({lo} to {hi})."
    for key in ("er_beds_total", "er_beds_available", "icu_beds_total", "icu_beds_available",
                "general_beds_available"):
        try:
            value = int(f.get(key, "0") or 0)
            if not 0 <= value <= 5000:
                raise ValueError
            setattr(h, key, value)
        except ValueError:
            errors[key] = "Must be a whole number 0-5000."
    if not errors:
        if h.er_beds_available > h.er_beds_total:
            errors["er_beds_available"] = "Cannot exceed ER total."
        if h.icu_beds_available > h.icu_beds_total:
            errors["icu_beds_available"] = "Cannot exceed ICU total."
    h.specialists = {k: f.get(f"spec_{k}") == "on" for k in SPECIALISTS}
    h.facilities = {k: f.get(f"fac_{k}") == "on" for k in FACILITIES}
    h.is_active = f.get("is_active") == "on"
    return errors


def _hospital_form(hospital, errors=None, status=200):
    return render_template("admin/hospital_form.html", h=hospital, errors=errors or {},
                           regions=GHANA_REGIONS, levels=LEVELS, specialists=SPECIALISTS,
                           facilities=FACILITIES), status


@bp.route("/hospitals/new", methods=["GET", "POST"])
def hospital_new():
    h = Hospital(is_active=True, specialists={}, facilities={}, latitude=None, longitude=None)
    if request.method == "POST":
        errors = _hospital_from_form(h)
        if not errors and Hospital.query.filter(
                (Hospital.code == h.code) | (Hospital.name == h.name)).first():
            errors["code"] = "A hospital with this name or code already exists."
        if errors:
            return _hospital_form(h, errors, 422)
        h.capacity_updated_at = utcnow()
        h.capacity_updated_by = current_user.username
        db.session.add(h)
        db.session.commit()
        audit.record("HOSPITAL_CREATED", resource=f"hospital:{h.id}", detail=h.code)
        realtime.notify_capacity(h)
        flash(f"Hospital {h.name} created.", "success")
        return redirect(url_for("admin.hospitals"))
    return _hospital_form(h)


@bp.route("/hospitals/<int:hospital_id>/edit", methods=["GET", "POST"])
def hospital_edit(hospital_id: int):
    h = db.session.get(Hospital, hospital_id) or abort(404)
    if request.method == "POST":
        errors = _hospital_from_form(h)
        if not errors:
            with db.session.no_autoflush:
                clash = Hospital.query.filter(Hospital.id != h.id,
                                              (Hospital.code == h.code) | (Hospital.name == h.name)).first()
            if clash:
                errors["code"] = "Another hospital already uses this name or code."
        if errors:
            db.session.rollback()
            return _hospital_form(h, errors, 422)
        h.capacity_updated_at = utcnow()
        h.capacity_updated_by = current_user.username
        db.session.commit()
        audit.record("HOSPITAL_UPDATED", resource=f"hospital:{h.id}", detail=h.code)
        realtime.notify_capacity(h)
        flash(f"Hospital {h.name} updated.", "success")
        return redirect(url_for("admin.hospitals"))
    return _hospital_form(h)


@bp.route("/hospitals/<int:hospital_id>/delete", methods=["POST"])
def hospital_delete(hospital_id: int):
    h = db.session.get(Hospital, hospital_id) or abort(404)
    in_use = Emergency.query.filter_by(hospital_id=h.id).count() or User.query.filter_by(hospital_id=h.id).count()
    if in_use:
        h.is_active = False
        db.session.commit()
        audit.record("HOSPITAL_DEACTIVATED", resource=f"hospital:{h.id}", detail=h.code)
        flash(f"{h.name} has linked cases or staff, so it was deactivated instead of deleted.", "warning")
    else:
        code = h.code
        db.session.delete(h)
        db.session.commit()
        audit.record("HOSPITAL_DELETED", resource=f"hospital:{hospital_id}", detail=code)
        flash("Hospital deleted.", "success")
    return redirect(url_for("admin.hospitals"))


# --- Staff accounts ---------------------------------------------------------
@bp.route("/users")
def users():
    items = User.query.order_by(User.role, User.username).all()
    return render_template("admin/users.html", users=items, roles=ROLES)


def _user_form(user, errors=None, status=200, is_new=False):
    hospitals_list = Hospital.query.filter_by(is_active=True).order_by(Hospital.name).all()
    return render_template("admin/user_form.html", u=user, errors=errors or {}, roles=ROLES,
                           hospitals=hospitals_list, is_new=is_new,
                           min_len=current_app.config["PASSWORD_MIN_LENGTH"]), status


def _apply_user_form(u: User, is_new: bool) -> dict[str, str]:
    f = request.form
    errors: dict[str, str] = {}
    if is_new:
        u.username = (f.get("username") or "").strip().lower()
        if not USERNAME_RE.fullmatch(u.username or ""):
            errors["username"] = "3-64 chars: lowercase letters, digits, . _ -"
        elif User.query.filter_by(username=u.username).first():
            errors["username"] = "Username already taken."
    u.full_name = " ".join((f.get("full_name") or "").split())[:120]
    if len(u.full_name) < 2:
        errors["full_name"] = "Full name is required."
    role = f.get("role")
    if role not in ROLES:
        errors["role"] = "Choose a role."
    elif u.id == current_user.id and role != ROLE_SUPER_ADMIN:
        errors["role"] = "You cannot remove your own super admin role."
    else:
        u.role = role
    hospital_id = f.get("hospital_id") or None
    u.hospital_id = int(hospital_id) if hospital_id and hospital_id.isdigit() else None
    if u.role == ROLE_HOSPITAL_ADMIN and not u.hospital_id:
        errors["hospital_id"] = "Hospital staff must be linked to a hospital."
    if u.role != ROLE_HOSPITAL_ADMIN:
        u.hospital_id = None
    password = f.get("password") or ""
    if is_new or password:
        if len(password) < current_app.config["PASSWORD_MIN_LENGTH"]:
            errors["password"] = f"At least {current_app.config['PASSWORD_MIN_LENGTH']} characters."
        elif password != (f.get("password_confirm") or ""):
            errors["password"] = "Passwords do not match."
        else:
            u.set_password(password)
    return errors


@bp.route("/users/new", methods=["GET", "POST"])
def user_new():
    u = User(is_enabled=True, role="paramedic", username="", full_name="", password_hash="!")
    if request.method == "POST":
        errors = _apply_user_form(u, is_new=True)
        if errors:
            return _user_form(u, errors, 422, is_new=True)
        db.session.add(u)
        db.session.commit()
        audit.record("USER_CREATED", resource=f"user:{u.id}", detail=f"{u.username} ({u.role})")
        flash(f"Account {u.username} created.", "success")
        return redirect(url_for("admin.users"))
    return _user_form(u, is_new=True)


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def user_edit(user_id: int):
    u = db.session.get(User, user_id) or abort(404)
    if request.method == "POST":
        errors = _apply_user_form(u, is_new=False)
        if errors:
            db.session.rollback()
            u = db.session.get(User, user_id)
            return _user_form(u, errors, 422)
        db.session.commit()
        audit.record("USER_UPDATED", resource=f"user:{u.id}", detail=f"{u.username} ({u.role})")
        flash(f"Account {u.username} updated.", "success")
        return redirect(url_for("admin.users"))
    return _user_form(u)


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def user_toggle(user_id: int):
    u = db.session.get(User, user_id) or abort(404)
    if u.id == current_user.id:
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("admin.users"))
    u.is_enabled = not u.is_enabled
    u.rotate_sessions()  # kill any live sessions immediately
    if u.is_enabled:
        u.locked_until = None
        u.failed_logins = 0
    db.session.commit()
    audit.record("USER_ENABLED" if u.is_enabled else "USER_DISABLED", resource=f"user:{u.id}",
                 detail=u.username)
    flash(f"{u.username} {'enabled' if u.is_enabled else 'disabled'}.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id: int):
    u = db.session.get(User, user_id) or abort(404)
    if u.id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.users"))
    if Emergency.query.filter_by(paramedic_id=u.id).count():
        u.is_enabled = False
        u.rotate_sessions()
        db.session.commit()
        audit.record("USER_DISABLED", resource=f"user:{u.id}", detail=f"{u.username} (has case history)")
        flash(f"{u.username} has case history, so the account was disabled instead of deleted.", "warning")
    else:
        name = u.username
        db.session.delete(u)
        db.session.commit()
        audit.record("USER_DELETED", resource=f"user:{user_id}", detail=name)
        flash("Account deleted.", "success")
    return redirect(url_for("admin.users"))


# --- Audit log --------------------------------------------------------------
@bp.route("/audit")
def audit_log():
    q = AuditLog.query
    username = (request.args.get("user") or "").strip().lower()
    action = (request.args.get("action") or "").strip().upper()
    reference = (request.args.get("ref") or "").strip().upper()
    day = (request.args.get("day") or "").strip()
    if username:
        q = q.filter(AuditLog.username == username)
    if action:
        q = q.filter(AuditLog.action == action)
    if reference:
        q = q.filter(AuditLog.emergency_reference == reference)
    if day:
        try:
            start = datetime.strptime(day, "%Y-%m-%d")
            q = q.filter(AuditLog.created_at >= start, AuditLog.created_at < start + timedelta(days=1))
        except ValueError:
            flash("Date must be YYYY-MM-DD.", "error")
    page = max(1, request.args.get("page", 1, type=int))
    pagination = q.order_by(AuditLog.id.desc()).paginate(page=page, per_page=50, error_out=False)
    actions = [a for (a,) in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    return render_template("admin/audit.html", page=pagination, actions=actions,
                           filters={"user": username, "action": action, "ref": reference, "day": day},
                           verify=None)


@bp.route("/audit/verify", methods=["POST"])
def audit_verify():
    result = audit.verify_chain()
    audit.record("AUDIT_VERIFIED", detail=f"ok={result['ok']} checked={result['checked']}")
    if result["ok"]:
        flash(f"Audit chain intact - {result['checked']} entries verified.", "success")
    else:
        log.critical("AUDIT CHAIN BROKEN at entry %s", result["first_bad_id"])
        flash(f"TAMPERING DETECTED: chain breaks at entry #{result['first_bad_id']}.", "error")
    return redirect(url_for("admin.audit_log"))
