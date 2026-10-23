"""Shared JSON API: health check, audited patient record and photo access."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, make_response
from flask_login import current_user
from sqlalchemy import text

from ..extensions import db
from ..models.emergency import Emergency
from ..models.media import Media
from ..models.base import utcnow
from ..models.user import ROLE_HOSPITAL_ADMIN, ROLE_PARAMEDIC, ROLE_SUPER_ADMIN
from ..services import audit
from ..services.access import can_view_emergency
from ..services.security import role_required

bp = Blueprint("api", __name__, url_prefix="/api")

STAFF = (ROLE_PARAMEDIC, ROLE_HOSPITAL_ADMIN, ROLE_SUPER_ADMIN)


@bp.route("/health")
def health():
    """Liveness/readiness probe for Docker and load balancers (no details)."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok", time=utcnow().isoformat() + "Z")
    except Exception:  # noqa: BLE001
        db.session.rollback()
        return jsonify(status="degraded", db=False), 503


@bp.route("/emergencies/<int:emergency_id>")
@role_required(*STAFF)
def emergency_detail(emergency_id: int):
    emergency = db.session.get(Emergency, emergency_id)
    if emergency is None or not can_view_emergency(current_user, emergency):
        abort(404)
    try:
        audit.record_view(emergency, resource="api.emergency")
    except audit.AuditWriteError:
        return jsonify(error="Access could not be logged; record withheld."), 503
    return jsonify(emergency=emergency.full_record())


@bp.route("/media/<int:media_id>")
@role_required(*STAFF)
def media(media_id: int):
    item = db.session.get(Media, media_id)
    if item is None or item.expires_at <= utcnow():
        abort(404)
    emergency = item.emergency
    if not can_view_emergency(current_user, emergency):
        abort(404)
    try:
        audit.record("VIEW_PHOTO", emergency=emergency, resource=f"media:{item.id}")
    except audit.AuditWriteError:
        abort(503)
    payload = item.data
    if payload is None:
        current_app.logger.error("Photo %s could not be decrypted", item.id)
        abort(410)
    resp = make_response(payload)
    resp.headers["Content-Type"] = item.mime_type
    resp.headers["Cache-Control"] = "no-store, private"
    resp.headers["Content-Disposition"] = f'inline; filename="{emergency.reference}-{item.id}.jpg"'
    return resp
