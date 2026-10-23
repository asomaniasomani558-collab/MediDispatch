"""Staff accounts: super admins, hospital admins and paramedics."""

from __future__ import annotations

import secrets
from datetime import timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from .base import utcnow

ROLE_SUPER_ADMIN = "super_admin"
ROLE_HOSPITAL_ADMIN = "hospital_admin"
ROLE_PARAMEDIC = "paramedic"

ROLES = {
    ROLE_SUPER_ADMIN: "Super Admin",
    ROLE_HOSPITAL_ADMIN: "Hospital Staff",
    ROLE_PARAMEDIC: "Paramedic",
}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(32), nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey("hospitals.id"), nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)

    # Rotated on password change / deactivation so existing sessions die.
    session_nonce = db.Column(db.String(32), nullable=False, default=lambda: secrets.token_hex(16))

    failed_logins = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    hospital = db.relationship("Hospital", back_populates="staff")

    # --- Flask-Login --------------------------------------------------------
    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return bool(self.is_enabled)

    def get_id(self) -> str:
        return f"{self.id}:{self.session_nonce}"

    # --- Password handling --------------------------------------------------
    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw, method="scrypt")
        self.rotate_sessions()

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    def rotate_sessions(self) -> None:
        self.session_nonce = secrets.token_hex(16)

    # --- Lockout ------------------------------------------------------------
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > utcnow())

    def register_failure(self, max_failures: int, lockout_minutes: int) -> None:
        self.failed_logins = (self.failed_logins or 0) + 1
        if self.failed_logins >= max_failures:
            self.locked_until = utcnow() + timedelta(minutes=lockout_minutes)
            self.failed_logins = 0

    def register_success(self) -> None:
        self.failed_logins = 0
        self.locked_until = None
        self.last_login_at = utcnow()

    # --- Roles --------------------------------------------------------------
    @property
    def role_label(self) -> str:
        return ROLES.get(self.role, self.role)

    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"
