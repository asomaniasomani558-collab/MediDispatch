"""Hospital dashboard - desktop command centre.

Live inbound queue (WebSockets push summaries; full records fetched over
audited HTTP), bed / specialist capacity updates, and hand-over actions.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user

from ..extensions import db
from ..models.base import utcnow
from ..models.emergency import (OPEN_STATUSES, STATUS_ACKNOWLEDGED, STATUS_ARRIVED,
                                STATUS_EN_ROUTE, STATUS_REPORTED, STATUS_RESOLVED, Emergency)
from ..models.hospital import FACILITIES, SPECIALISTS, Hospital
from ..models.user import ROLE_HOSPITAL_ADMIN
from ..services import audit, realtime
from ..services.access import can_view_emergency
from ..services.matching import haversine_km
from ..services.security import role_required

bp = Blueprint("hospital", __name__, url_prefix="/hospital")


@bp.before_request
@role_required(ROLE_HOSPITAL_ADMIN)
def _guard():
    if current_user.hospital_id is None:
        abort(403, "Your account is not linked to a hospital. Contact the system administrator.")
    return None


def _my_hospital() -> Hospital:
    hospital = db.session.get(Hospital, current_user.hospital_id)
    if hospital is None:
        abort(403, "Hospital not found.")
    return hospital


@bp.route("/")
def dashboard():
    return render_template("hospital/dashboard.html", hospital=_my_hospital(),
                           specialists=SPECIALISTS, facilities=FACILITIES)


@bp.route("/api/queue")
def api_queue():
    """Inbound patients for this hospital. Every record shown is audited."""
    hospital = _my_hospital()
    rows = (Emergency.query.filter(Emergency.hospital_id == hospital.id,
                                   Emergency.status.in_(OPEN_STATUSES))
            .order_by(Emergency.severity_rank.desc(), Emergency.assigned_at.asc()).all())
    try:
        for e in rows:
            audit.record("VIEW_PATIENT_RECORD", emergency=e, resource="hospital.queue", commit=False)
        db.session.commit()
    except audit.AuditWriteError:
        return jsonify(error="Access could not be logged; records withheld. Retrying..."), 503
    return jsonify(queue=[e.full_record() for e in rows], server_time=utcnow().isoformat() + "Z")


@bp.route("/api/nearby")
def api_nearby():
    """Unassigned bystander reports near this hospital - no identifying data."""
    hospital = _my_hospital()
    radius = current_app.config["HOSPITAL_NEARBY_RADIUS_KM"]
    rows = (Emergency.query.filter(Emergency.status == STATUS_REPORTED)
            .order_by(Emergency.created_at.desc()).limit(200).all())
    items = []
    for e in rows:
        if e.lat is None:
            continue
        dist = haversine_km(hospital.latitude, hospital.longitude, e.lat, e.lon)
        if dist <= radius:
            items.append(dict(e.public_summary(), distance_km=round(dist, 1)))
    items.sort(key=lambda i: i["distance_km"])
    return jsonify(reports=items[:50])


def _int_field(data: dict, key: str, current: int) -> int:
    value = data.get(key, current)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a whole number") from None
    if value < 0 or value > 5000:
        raise ValueError(f"{key} must be between 0 and 5000")
    return value


@bp.route("/api/capacity", methods=["POST"])
def api_capacity():
    hospital = _my_hospital()
    data = request.get_json(silent=True) or {}
    try:
        er = _int_field(data, "er_beds_available", hospital.er_beds_available)
        icu = _int_field(data, "icu_beds_available", hospital.icu_beds_available)
        general = _int_field(data, "general_beds_available", hospital.general_beds_available)
    except ValueError as exc:
        return jsonify(error=str(exc)), 422
    if er > hospital.er_beds_total:
        return jsonify(error=f"ER available cannot exceed total ({hospital.er_beds_total})."), 422
    if icu > hospital.icu_beds_total:
        return jsonify(error=f"ICU available cannot exceed total ({hospital.icu_beds_total})."), 422

    specialists_in = data.get("specialists") or {}
    specialists = dict(hospital.specialists or {})
    for key in SPECIALISTS:
        if key in specialists_in:
            specialists[key] = bool(specialists_in[key])

    hospital.er_beds_available = er
    hospital.icu_beds_available = icu
    hospital.general_beds_available = general
    hospital.specialists = specialists
    hospital.capacity_updated_at = utcnow()
    hospital.capacity_updated_by = current_user.username
    db.session.commit()
    try:
        audit.record("CAPACITY_UPDATED", resource=f"hospital:{hospital.id}",
                     detail=f"er={er} icu={icu} general={general}")
    except audit.AuditWriteError:
        pass
    realtime.notify_capacity(hospital)
    return jsonify(ok=True, hospital=hospital.to_matching_dict())


_TRANSITIONS = {
    "acknowledge": ({STATUS_EN_ROUTE}, STATUS_ACKNOWLEDGED, "acknowledged_at"),
    "arrived": ({STATUS_EN_ROUTE, STATUS_ACKNOWLEDGED}, STATUS_ARRIVED, "arrived_at"),
    "resolve": ({STATUS_EN_ROUTE, STATUS_ACKNOWLEDGED, STATUS_ARRIVED}, STATUS_RESOLVED, "closed_at"),
}


@bp.route("/api/case/<int:case_id>/<action>", methods=["POST"])
def api_case_action(case_id: int, action: str):
    if action not in _TRANSITIONS:
        abort(404)
    emergency = db.session.get(Emergency, case_id)
    if emergency is None or not can_view_emergency(current_user, emergency):
        abort(404)
    allowed_from, target, stamp = _TRANSITIONS[action]
    if emergency.status not in allowed_from:
        return jsonify(error=f"Cannot {action} a case that is {emergency.status_label}."), 409
    emergency.status = target
    setattr(emergency, stamp, utcnow())
    db.session.commit()
    try:
        audit.record("STATUS_CHANGED", emergency=emergency, detail=f"hospital -> {target}")
    except audit.AuditWriteError:
        pass
    realtime.notify_emergency_updated(emergency)
    return jsonify(ok=True, status=emergency.status, status_label=emergency.status_label)
