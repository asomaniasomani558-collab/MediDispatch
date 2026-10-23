"""Civilian (bystander) PWA - zero login.

Flow: big red button -> name & phone -> situation -> report sent.
After reporting, the browser holds a bearer token (``X-Civilian-Token``) that
lets it ping GPS every 10 s, optionally upload photos it explicitly took, and
read its own report status. The token grants access to nothing else.
"""

from __future__ import annotations

import logging

from flask import (Blueprint, current_app, g, jsonify, render_template, request,
                   send_from_directory)
from flask_wtf.csrf import generate_csrf

from ..extensions import db
from ..models.base import utcnow
from ..models.emergency import (OPEN_STATUSES, SITUATIONS, SOURCE_CIVILIAN, STATUS_CANCELLED,
                                STATUS_REPORTED, CivilianSession, Emergency)
from ..models.hospital import Hospital
from ..services import audit, realtime
from ..services.first_aid import FIRST_AID, GENERAL_STEPS, steps_for
from ..services.media import MediaError, store_photo
from ..services.security import (civilian_required, clean_name, limiter, normalize_ghana_phone,
                                 parse_coords)

log = logging.getLogger(__name__)
bp = Blueprint("civilian", __name__, url_prefix="/civilian")


def _current_emergency() -> Emergency | None:
    session: CivilianSession = g.civilian_session
    return (Emergency.query.filter_by(civilian_session_id=session.id)
            .order_by(Emergency.id.desc()).first())


def _status_payload(emergency: Emergency) -> dict:
    """What a bystander may see about their own report (no staff PII)."""
    return {
        "reference": emergency.reference,
        "status": emergency.status,
        "status_label": emergency.status_label,
        "situation": emergency.situation,
        "help_assigned": emergency.paramedic_id is not None,
        "hospital": emergency.hospital.name if emergency.hospital else None,
        "photo_count": len(emergency.live_media()),
        "max_photos": current_app.config["MEDIA_MAX_PER_EMERGENCY"],
        "open": emergency.is_open,
    }


# --- Pages ------------------------------------------------------------------
@bp.route("/")
def index():
    return render_template(
        "civilian/index.html",
        first_aid=FIRST_AID,
        general_steps=GENERAL_STEPS,
        situations=SITUATIONS,
    )


@bp.route("/manifest.webmanifest")
def manifest():
    resp = send_from_directory(current_app.static_folder, "manifest.webmanifest",
                               mimetype="application/manifest+json")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@bp.route("/sw.js")
def service_worker():
    resp = send_from_directory(current_app.static_folder + "/js", "sw.js",
                               mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/civilian/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# --- JSON API ---------------------------------------------------------------
@bp.route("/api/csrf")
def refresh_csrf():
    return jsonify(csrf_token=generate_csrf())


@bp.route("/api/report", methods=["POST"])
def create_report():
    ip = request.remote_addr or "unknown"
    if not limiter.allow(f"report:{ip}", current_app.config["CIVILIAN_REPORTS_PER_IP_PER_10MIN"], 600):
        return jsonify(error="Too many reports from this device. Please call 112 directly."), 429

    data = request.get_json(silent=True) or {}
    name = clean_name(data.get("name"))
    phone = normalize_ghana_phone(data.get("phone"))
    situation = data.get("situation")
    errors = {}
    if not name or len(name) < 2:
        errors["name"] = "Please enter your name."
    if not phone:
        errors["phone"] = "Enter a valid phone number, e.g. 024 123 4567."
    if situation not in SITUATIONS:
        errors["situation"] = "Choose what is happening."
    if errors:
        return jsonify(error="Please check the form.", fields=errors), 422

    location = parse_coords(data.get("lat"), data.get("lon"), data.get("acc"))

    session, token = CivilianSession.issue(current_app.config["CIVILIAN_TOKEN_HOURS"], ip)
    emergency = Emergency(
        reference=Emergency.new_reference(),
        source=SOURCE_CIVILIAN,
        situation=situation,
        status=STATUS_REPORTED,
        reporter_name=name,
        reporter_phone=phone,
        location=location,
        location_updated_at=utcnow() if location else None,
        civilian_session=session,
    )
    db.session.add_all([session, emergency])
    db.session.commit()
    log.info("Bystander report %s created (situation=%s, gps=%s)",
             emergency.reference, situation, bool(location))
    try:
        audit.record("REPORT_CREATED", emergency=emergency, detail=f"situation={situation}")
    except audit.AuditWriteError:
        pass  # never block an emergency report on audit failure

    hospitals = Hospital.query.filter_by(is_active=True).all()
    realtime.notify_new_report(emergency, hospitals, current_app.config["HOSPITAL_NEARBY_RADIUS_KM"])

    return jsonify(
        token=token,
        reference=emergency.reference,
        first_aid=steps_for(situation),
        status=_status_payload(emergency),
    ), 201


@bp.route("/api/ping", methods=["POST"])
@civilian_required
def ping():
    emergency = _current_emergency()
    if emergency is None:
        return jsonify(error="No active report."), 404
    data = request.get_json(silent=True) or {}
    location = parse_coords(data.get("lat"), data.get("lon"), data.get("acc"))
    min_gap = current_app.config["CIVILIAN_PING_MIN_SECONDS"]
    now = utcnow()
    accepted = False
    if location and emergency.is_open:
        last = emergency.location_updated_at
        if last is None or (now - last).total_seconds() >= min_gap:
            emergency.location = location
            emergency.location_updated_at = now
            db.session.commit()
            accepted = True
    return jsonify(accepted=accepted, status=_status_payload(emergency))


@bp.route("/api/status")
@civilian_required
def status():
    emergency = _current_emergency()
    if emergency is None:
        return jsonify(error="No active report."), 404
    return jsonify(status=_status_payload(emergency))


@bp.route("/api/photo", methods=["POST"])
@civilian_required
def upload_photo():
    emergency = _current_emergency()
    if emergency is None or not emergency.is_open:
        return jsonify(error="This report is closed."), 409
    if request.form.get("consent") != "yes":
        return jsonify(error="Photo consent is required."), 400
    upload = request.files.get("photo")
    if upload is None:
        return jsonify(error="No photo received."), 400
    raw = upload.read(current_app.config["MEDIA_MAX_BYTES"] + 1)
    try:
        media = store_photo(emergency, raw, current_app.config)
        db.session.commit()
    except MediaError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 422
    try:
        audit.record("PHOTO_UPLOADED", emergency=emergency, resource=f"media:{media.id}")
    except audit.AuditWriteError:
        pass
    realtime.notify_emergency_updated(emergency)
    return jsonify(ok=True, media_id=media.id, status=_status_payload(emergency)), 201


@bp.route("/api/cancel", methods=["POST"])
@civilian_required
def cancel():
    emergency = _current_emergency()
    if emergency is None:
        return jsonify(error="No active report."), 404
    if emergency.status == STATUS_REPORTED:
        emergency.status = STATUS_CANCELLED
        emergency.closed_at = utcnow()
        db.session.commit()
        realtime.notify_emergency_updated(emergency)
        try:
            audit.record("REPORT_CANCELLED", emergency=emergency, detail="by reporter")
        except audit.AuditWriteError:
            pass
        return jsonify(ok=True, status=_status_payload(emergency))
    if emergency.status in OPEN_STATUSES:
        return jsonify(error="A responder is already on the way. Call 112 to cancel."), 409
    return jsonify(ok=True, status=_status_payload(emergency))
