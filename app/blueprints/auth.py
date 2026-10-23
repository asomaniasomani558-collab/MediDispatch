"""Staff sign-in / sign-out with lockout and session rotation."""

from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models.user import ROLE_HOSPITAL_ADMIN, ROLE_PARAMEDIC, ROLE_SUPER_ADMIN, User
from ..services import audit
from ..services.security import limiter

bp = Blueprint("auth", __name__, url_prefix="/auth")

HOME_BY_ROLE = {
    ROLE_SUPER_ADMIN: "admin.dashboard",
    ROLE_HOSPITAL_ADMIN: "hospital.dashboard",
    ROLE_PARAMEDIC: "paramedic.feed",
}


def home_for(user) -> str:
    return url_for(HOME_BY_ROLE.get(user.role, "index"))


def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()[:64]
        password = request.form.get("password") or ""
        ip = request.remote_addr or "unknown"

        if not limiter.allow(f"login:{ip}", limit=20, window_seconds=600):
            flash("Too many sign-in attempts from this device. Wait 10 minutes.", "error")
            return render_template("auth/login.html", username=username), 429

        user = User.query.filter_by(username=username).first()
        generic = "Invalid username or password."

        if user is None:
            flash(generic, "error")
            return render_template("auth/login.html", username=username), 401
        if not user.is_enabled:
            flash("This account is disabled. Contact your administrator.", "error")
            return render_template("auth/login.html", username=username), 403
        if user.is_locked():
            flash("Account temporarily locked after repeated failures. Try again later.", "error")
            return render_template("auth/login.html", username=username), 423
        if not user.check_password(password):
            user.register_failure(current_app.config["LOGIN_MAX_FAILURES"],
                                  current_app.config["LOGIN_LOCKOUT_MINUTES"])
            db.session.commit()
            try:
                audit.record("LOGIN_FAILED", user=user, detail="bad password")
            except audit.AuditWriteError:
                pass
            flash(generic, "error")
            return render_template("auth/login.html", username=username), 401

        user.register_success()
        db.session.commit()
        login_user(user, remember=False)
        try:
            audit.record("LOGIN", user=user)
        except audit.AuditWriteError:
            pass
        return redirect(_safe_next(request.args.get("next")) or home_for(user))

    return render_template("auth/login.html", username="")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    try:
        audit.record("LOGOUT")
    except audit.AuditWriteError:
        pass
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("auth.login"))
