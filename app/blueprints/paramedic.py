"""Paramedic app - mobile-first clinical UI.

Features: bystander-report feed with atomic claim, new on-scene cases,
vitals entry, MEWS + AI triage, hospital matching and hand-over.
"""

from __future__ import annotations

import logging

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request,
                   url_for)
from flask_login import current_user
from sqlalchemy import update

from ..extensions import db
from ..models.base import utcnow
from ..models.emergency import (SITUATIONS, SOURCE_PARAMEDIC, STATUS_ARRIVED, STATUS_CANCELLED,
                                STATUS_CLAIMED, STATUS_EN_ROUTE, STATUS_REPORTED,
                                STATUS_RESOLVED, STATUS_TRIAGED, OPEN_STATUSES, Emergency)
from ..models.hospital import Hospital
from ..models.user import ROLE_PARAMEDIC
from ..services import audit, realtime
from ..services.access import can_view_emergency
from ..services.ai import get_harness
from ..services.matching import haversine_km, match_hospitals
from ..services.security import clean_name, normalize_ghana_phone, parse_coords, role_required
from ..services.triage import VitalsError, run_triage, severity_rank

log = logging.getLogger(__name__)
bp = Blueprint("paramedic", __name__, url_prefix="/paramedic")


@bp.before_request
@role_required(ROLE_PARAMEDIC)
def _guard():
    """Every paramedic route requires the paramedic role."""
    return None


def _own_case_or_404(case_id: int) -> Emergency:
    emergency = db.session.get(Emergency, case_id)
    if emergency is None or not can_view_emergency(current_user, emergency):
        abort(404)
    return emergency


# --- Pages ------------------------------------------------------------------
@bp.route("/")
def feed():
    my_cases = (Emergency.query.filter(Emergency.paramedic_id == current_user.id,
                                       Emergency.status.in_(OPEN_STATUSES))
                .order_by(Emergency.severity_rank.desc(), Emergency.created_at.desc()).all())
    return render_template("paramedic/feed.html", my_cases=my_cases)


@bp.route("/case/new", methods=["GET", "POST"])
def new_case():
    if request.method == "POST":
        situation = request.form.get("situation")
        if situation not in SITUATIONS:
            flash("Choose a situation.", "error")
            return render_template("paramedic/new_case.html"), 422
        phone_raw = request.form.get("phone")
        phone = normalize_ghana_phone(phone_raw) if phone_raw else None
        if phone_raw and not phone:
            flash("Phone number is not valid.", "error")
            return render_template("paramedic/new_case.html"), 422
        now = utcnow()
        location = parse_coords(request.form.get("lat"), request.form.get("lon"), request.form.get("acc"))
        emergency = Emergency(
            reference=Emergency.new_reference(),
            source=SOURCE_PARAMEDIC,
            situation=situation,
            status=STATUS_CLAIMED,
            reporter_name=clean_name(request.form.get("name")),
            reporter_phone=phone,
            location=location,
            location_updated_at=now if location else None,
            paramedic_id=current_user.id,
            claimed_at=now,
        )
        db.session.add(emergency)
        db.session.commit()
        try:
            audit.record("CASE_CREATED", emergency=emergency, detail=f"situation={situation}")
        except audit.AuditWriteError:
            pass
        realtime.notify_emergency_updated(emergency)
        return redirect(url_for("paramedic.case", case_id=emergency.id))
    return render_template("paramedic/new_case.html")


@bp.route("/case/<int:case_id>")
def case(case_id: int):
    emergency = _own_case_or_404(case_id)
    try:
        audit.record_view(emergency, resource="paramedic.case")
    except audit.AuditWriteError:
        abort(503, "Access could not be logged; record withheld. Try again.")
    return render_template("paramedic/case.html", e=emergency)


# --- JSON API ---------------------------------------------------------------
@bp.route("/api/feed")
def api_feed():
    """Unclaimed bystander reports. No PII: distance only, never coordinates."""
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    rows = (Emergency.query.filter(Emergency.status == STATUS_REPORTED,
                                   Emergency.paramedic_id.is_(None))
            .order_by(Emergency.created_at.asc()).limit(100).all())
    items = []
    for e in rows:
        item = e.public_summary()
        item["age_seconds"] = int((utcnow() - e.created_at).total_seconds())
        item["has_gps"] = e.lat is not None
        item["distance_km"] = None
        if lat is not None and lon is not None and e.lat is not None:
            item["distance_km"] = round(haversine_km(lat, lon, e.lat, e.lon), 1)
        items.append(item)
    if lat is not None and lon is not None:
        items.sort(key=lambda i: (i["distance_km"] is None, i["distance_km"] or 0))
    return jsonify(reports=items)


@bp.route("/api/claim/<int:case_id>", methods=["POST"])
def api_claim(case_id: int):
    """Atomically claim a bystander report (first paramedic wins)."""
    now = utcnow()
    result = db.session.execute(
        update(Emergency)
        .where(Emergency.id == case_id,
               Emergency.status == STATUS_REPORTED,
               Emergency.paramedic_id.is_(None))
        .values(paramedic_id=current_user.id, status=STATUS_CLAIMED, claimed_at=now, updated_at=now)
    )
    if result.rowcount != 1:
        db.session.rollback()
        return jsonify(error="Already claimed by another crew or no longer available."), 409
    db.session.commit()
    emergency = db.session.get(Emergency, case_id)
    db.session.refresh(emergency)
    try:
        audit.record("CASE_CLAIMED", emergency=emergency)
    except audit.AuditWriteError:
        pass
    realtime.notify_emergency_updated(emergency)
    return jsonify(ok=True, url=url_for("paramedic.case", case_id=case_id))


@bp.route("/api/case/<int:case_id>/release", methods=["POST"])
def api_release(case_id: int):
    emergency = _own_case_or_404(case_id)
    if emergency.status != STATUS_CLAIMED or emergency.source != "civilian":
        return jsonify(error="Only an untriaged bystander report can be released."), 409
    emergency.status = STATUS_REPORTED
    emergency.paramedic_id = None
    emergency.claimed_at = None
    db.session.commit()
    try:
        audit.record("CASE_RELEASED", emergency=emergency)
    except audit.AuditWriteError:
        pass
    realtime.notify_new_report(emergency)
    return jsonify(ok=True, url=url_for("paramedic.feed"))


@bp.route("/api/case/<int:case_id>/triage", methods=["POST"])
def api_triage(case_id: int):
    emergency = _own_case_or_404(case_id)
    data = request.get_json(silent=True) or {}
    vitals_in = data.get("vitals") or {}
    symptoms = (data.get("symptoms") or "").strip()[:2000]
    try:
        result = run_triage(vitals_in, symptoms=symptoms, situation=emergency.situation,
                            harness=get_harness())
    except VitalsError as exc:
        return jsonify(error="Some vitals look wrong - please check.", fields=exc.errors), 422

    now = utcnow()
    emergency.vitals = result.vitals
    emergency.symptoms = symptoms or None
    emergency.triage = result.to_dict()
    emergency.mews_score = result.mews.score
    emergency.mews_severity = result.mews.severity
    emergency.severity = result.final_severity
    emergency.severity_rank = severity_rank(result.final_severity)
    emergency.ai_status = result.ai_status
    emergency.triaged_at = now
    if emergency.status == STATUS_CLAIMED:
        emergency.status = STATUS_TRIAGED
    db.session.commit()
    log.info("Triage %s: MEWS=%s baseline=%s final=%s ai=%s", emergency.reference,
             result.mews.score, result.baseline_severity, result.final_severity, result.ai_status)
    try:
        audit.record("TRIAGE_RECORDED", emergency=emergency,
                     detail=f"mews={result.mews.score} final={result.final_severity} ai={result.ai_status}")
    except audit.AuditWriteError:
        pass
    realtime.notify_emergency_updated(emergency)
    return jsonify(triage=result.to_dict(), matching=_match(emergency))


def _match(emergency: Emergency, lat=None, lon=None) -> dict:
    hospitals = [h.to_matching_dict() for h in Hospital.query.filter_by(is_active=True).all()]
    lat = lat if lat is not None else emergency.lat
    lon = lon if lon is not None else emergency.lon
    age = (emergency.vitals or {}).get("age")
    return match_hospitals(hospitals, lat, lon, severity=emergency.severity or "MODERATE",
                           situation=emergency.situation, patient_age=age, limit=4)


@bp.route("/api/case/<int:case_id>/matches")
def api_matches(case_id: int):
    emergency = _own_case_or_404(case_id)
    return jsonify(matching=_match(emergency, request.args.get("lat", type=float),
                                   request.args.get("lon", type=float)))


@bp.route("/api/case/<int:case_id>/assign", methods=["POST"])
def api_assign(case_id: int):
    emergency = _own_case_or_404(case_id)
    if not emergency.is_open:
        return jsonify(error="Case is closed."), 409
    data = request.get_json(silent=True) or {}
    hospital = db.session.get(Hospital, int(data.get("hospital_id") or 0))
    if hospital is None or not hospital.is_active:
        return jsonify(error="Hospital not found."), 404
    previous = emergency.hospital_id
    emergency.hospital_id = hospital.id
    emergency.status = STATUS_EN_ROUTE
    emergency.assigned_at = utcnow()
    emergency.acknowledged_at = None
    db.session.commit()
    try:
        audit.record("HOSPITAL_ASSIGNED", emergency=emergency, resource=f"hospital:{hospital.id}")
    except audit.AuditWriteError:
        pass
    realtime.notify_emergency_updated(emergency, previous_hospital_id=previous)
    return jsonify(ok=True, hospital=hospital.name, status=emergency.status)


@bp.route("/api/case/<int:case_id>/status", methods=["POST"])
def api_status(case_id: int):
    emergency = _own_case_or_404(case_id)
    target = (request.get_json(silent=True) or {}).get("status")
    allowed = {STATUS_ARRIVED, STATUS_RESOLVED, STATUS_CANCELLED}
    if target not in allowed:
        return jsonify(error="Invalid status."), 400
    if not emergency.is_open:
        return jsonify(error="Case already closed."), 409
    if target == STATUS_ARRIVED and not emergency.hospital_id:
        return jsonify(error="Assign a hospital first."), 409
    now = utcnow()
    emergency.status = target
    if target == STATUS_ARRIVED:
        emergency.arrived_at = now
    else:
        emergency.closed_at = now
    db.session.commit()
    try:
        audit.record("STATUS_CHANGED", emergency=emergency, detail=f"-> {target}")
    except audit.AuditWriteError:
        pass
    realtime.notify_emergency_updated(emergency)
    return jsonify(ok=True, status=emergency.status, status_label=emergency.status_label)


@bp.route("/api/hospitals")
def api_hospitals():
    """Live capacity board (no patient data)."""
    hospitals = Hospital.query.filter_by(is_active=True).order_by(Hospital.region, Hospital.name).all()
    return jsonify(hospitals=[h.to_matching_dict() for h in hospitals])

