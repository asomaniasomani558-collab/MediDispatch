"""End-to-end dispatch workflow across all four applications."""

from __future__ import annotations

import io

from app.extensions import db, socketio
from app.models import AuditLog, Emergency, Hospital, User
from tests.test_civilian import jpeg_bytes

VITALS_CRITICAL = {"respiratory_rate": 32, "heart_rate": 135, "systolic_bp": 75,
                   "temperature": 38.9, "avpu": "V", "spo2": 88, "age": 34}


def test_full_dispatch_flow(app, client, make_user, make_hospital, login, report):
    trauma = make_hospital(name="Trauma Centre", code="TC", latitude=6.70, longitude=-1.63,
                           specialists={"trauma_surgeon": True},
                           facilities={"ct_scanner": True, "blood_bank": True})
    other = make_hospital(name="Other Hospital", code="OH", latitude=6.60, longitude=-1.50)

    civ = client  # the bystander's browser
    data, token = report(situation="accident")
    civ.post("/civilian/api/photo", headers={"X-Civilian-Token": token},
             data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes()), "p.jpg")},
             content_type="multipart/form-data")
    e = Emergency.query.filter_by(reference=data["reference"]).one()

    # --- Paramedic: feed hides PII, claim is atomic ---------------------------
    medic_a = make_user("paramedic", username="medic.a")
    medic_b = make_user("paramedic", username="medic.b")
    pa, pb = app.test_client(), app.test_client()
    login(pa, medic_a)
    login(pb, medic_b)

    feed = pa.get("/paramedic/api/feed?lat=6.69&lon=-1.62").get_json()["reports"]
    assert feed[0]["id"] == e.id and feed[0]["distance_km"] is not None
    assert "reporter_phone" not in feed[0] and "location" not in feed[0]

    assert pb.get(f"/paramedic/case/{e.id}").status_code == 404   # not claimed by B
    assert pa.post(f"/paramedic/api/claim/{e.id}").status_code == 200
    assert pb.post(f"/paramedic/api/claim/{e.id}").status_code == 409  # first wins
    assert pb.get(f"/paramedic/case/{e.id}").status_code == 404

    page = pa.get(f"/paramedic/case/{e.id}").get_data(as_text=True)
    assert "Ama Owusu" in page and "+233241234567" in page

    # --- Triage (AI disabled in tests -> MEWS fallback) ----------------------
    resp = pa.post(f"/paramedic/api/case/{e.id}/triage",
                   json={"vitals": VITALS_CRITICAL, "symptoms": "motorbike crash, confused"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["triage"]["final_severity"] == "CRITICAL"
    assert body["triage"]["ai"]["status"] == "disabled"
    best = body["matching"]["matches"][0]
    assert best["hospital_id"] == trauma.id

    bad = pa.post(f"/paramedic/api/case/{e.id}/triage", json={"vitals": {"heart_rate": 999}})
    assert bad.status_code == 422 and "heart_rate" in bad.get_json()["fields"]

    # --- Assign hospital ------------------------------------------------------
    assert pa.post(f"/paramedic/api/case/{e.id}/assign", json={"hospital_id": trauma.id}).status_code == 200
    db.session.expire_all()
    assert db.session.get(Emergency, e.id).status == "en_route"

    # --- Hospital: only the receiving hospital sees it ------------------------
    staff = make_user("hospital_admin", username="tc.er", hospital=trauma)
    staff_other = make_user("hospital_admin", username="oh.er", hospital=other)
    h1, h2 = app.test_client(), app.test_client()
    login(h1, staff)
    login(h2, staff_other)

    q = h1.get("/hospital/api/queue").get_json()["queue"]
    assert len(q) == 1
    rec = q[0]
    assert rec["reporter_name"] == "Ama Owusu" and rec["reporter_phone"] == "+233241234567"
    assert rec["location"]["lat"] == 6.6885 and rec["severity"] == "CRITICAL"
    assert len(rec["media"]) == 1
    assert h2.get("/hospital/api/queue").get_json()["queue"] == []

    media_id = rec["media"][0]["id"]
    photo = h1.get(f"/api/media/{media_id}")
    assert photo.status_code == 200 and photo.data[:2] == b"\xff\xd8"
    assert photo.headers["Cache-Control"].startswith("no-store")
    assert h2.get(f"/api/media/{media_id}").status_code == 404

    audited = AuditLog.query.filter_by(emergency_id=e.id, username="tc.er").all()
    assert {a.action for a in audited} >= {"VIEW_PATIENT_RECORD", "VIEW_PHOTO"}

    # --- Hospital acknowledges, patient arrives ------------------------------
    assert h1.post(f"/hospital/api/case/{e.id}/acknowledge").status_code == 200
    assert h1.post(f"/hospital/api/case/{e.id}/acknowledge").status_code == 409
    assert h2.post(f"/hospital/api/case/{e.id}/arrived").status_code == 404
    assert h1.post(f"/hospital/api/case/{e.id}/arrived").status_code == 200

    # Civilian sees progress but no staff details.
    status = civ.get("/civilian/api/status", headers={"X-Civilian-Token": token}).get_json()["status"]
    assert status["status"] == "arrived" and status["hospital"] == "Trauma Centre"

    assert h1.post(f"/hospital/api/case/{e.id}/resolve").status_code == 200
    assert h1.get("/hospital/api/queue").get_json()["queue"] == []
    assert audit_chain_ok()


def audit_chain_ok():
    from app.services.audit import verify_chain
    return verify_chain()["ok"]


def test_paramedic_on_scene_case(app, client, make_user, make_hospital, login):
    make_hospital()
    login(client, make_user("paramedic"))
    resp = client.post("/paramedic/case/new", data={"situation": "chest_pain", "name": "Kwame",
                                                    "phone": "0551234567", "lat": "6.69", "lon": "-1.62"})
    assert resp.status_code == 302
    e = Emergency.query.one()
    assert e.source == "paramedic" and e.status == "claimed"
    assert client.get(resp.headers["Location"]).status_code == 200


def test_capacity_update_validation_and_broadcast(app, client, make_user, make_hospital, login):
    h = make_hospital(er_beds_total=10, icu_beds_total=4)
    login(client, make_user("hospital_admin", hospital=h))
    assert client.post("/hospital/api/capacity", json={"er_beds_available": 11}).status_code == 422
    assert client.post("/hospital/api/capacity", json={"er_beds_available": -1}).status_code == 422
    resp = client.post("/hospital/api/capacity", json={
        "er_beds_available": 0, "icu_beds_available": 1, "general_beds_available": 3,
        "specialists": {"neurosurgeon": True, "not_a_real_key": True}})
    assert resp.status_code == 200
    db.session.expire_all()
    h = db.session.get(Hospital, h.id)
    assert h.er_beds_available == 0 and h.specialists["neurosurgeon"] is True
    assert "not_a_real_key" not in h.specialists


def test_admin_crud(app, client, make_user, login):
    admin = make_user("super_admin", username="root.admin")
    login(client, admin)
    form = {"name": "New Polyclinic", "code": "NPC", "region": "Volta", "level": "Polyclinic",
            "latitude": "6.6", "longitude": "0.47", "er_beds_total": "5", "er_beds_available": "3",
            "icu_beds_total": "0", "icu_beds_available": "0", "general_beds_available": "4",
            "spec_obstetrician": "on", "fac_maternity": "on", "is_active": "on"}
    assert client.post("/admin/hospitals/new", data=form).status_code == 302
    h = Hospital.query.filter_by(code="NPC").one()
    assert h.specialists["obstetrician"] and h.facilities["maternity"]

    bad = dict(form, code="NPC2", latitude="51.5")  # London is not in Ghana
    assert client.post("/admin/hospitals/new", data=bad).status_code == 422
    dup = dict(form, name="Another")
    assert client.post("/admin/hospitals/new", data=dup).status_code == 422

    edit = dict(form, er_beds_available="9")
    assert client.post(f"/admin/hospitals/{h.id}/edit", data=edit).status_code == 422  # > total
    edit = dict(form, er_beds_total="12", er_beds_available="9")
    assert client.post(f"/admin/hospitals/{h.id}/edit", data=edit).status_code == 302

    user_form = {"username": "new.medic", "full_name": "New Medic", "role": "paramedic",
                 "password": "a-long-password", "password_confirm": "a-long-password"}
    assert client.post("/admin/users/new", data=user_form).status_code == 302
    u = User.query.filter_by(username="new.medic").one()
    assert u.check_password("a-long-password")
    short = dict(user_form, username="x.y", password="short", password_confirm="short")
    assert client.post("/admin/users/new", data=short).status_code == 422
    staff_no_hosp = dict(user_form, username="h.staff", role="hospital_admin")
    assert client.post("/admin/users/new", data=staff_no_hosp).status_code == 422

    assert client.post(f"/admin/users/{u.id}/toggle").status_code == 302
    assert db.session.get(User, u.id).is_enabled is False
    assert client.post(f"/admin/users/{admin.id}/toggle").status_code == 302
    assert db.session.get(User, admin.id).is_enabled is True  # can't disable self

    assert client.post(f"/admin/hospitals/{h.id}/delete").status_code == 302
    assert Hospital.query.filter_by(code="NPC").count() == 0

    for page in ("/admin/", "/admin/hospitals", "/admin/users", "/admin/audit", "/admin/api/health",
                 "/admin/api/logs", f"/admin/users/{u.id}/edit", "/admin/hospitals/new"):
        assert client.get(page).status_code == 200, page
    assert client.post("/admin/audit/verify").status_code == 302
    actions = {a.action for a in AuditLog.query.all()}
    assert {"HOSPITAL_CREATED", "USER_CREATED", "USER_DISABLED", "HOSPITAL_DELETED"} <= actions


def test_admin_health_reports_ai_offline_without_crash(app, client, make_user, login):
    login(client, make_user("super_admin"))
    health = client.get("/admin/api/health").get_json()["health"]
    assert health["database"]["online"] is True
    assert health["ai"]["online"] is False


def test_socket_rejects_anonymous_and_routes_events(app, make_user, make_hospital, login, report):
    anon = socketio.test_client(app, flask_test_client=app.test_client())
    assert not anon.is_connected()

    h = make_hospital()
    staff = make_user("hospital_admin", hospital=h)
    http = app.test_client()
    login(http, staff)
    sock = socketio.test_client(app, flask_test_client=http)
    assert sock.is_connected()
    sock.get_received()

    medic = make_user("paramedic")
    phttp = app.test_client()
    login(phttp, medic)
    psock = socketio.test_client(app, flask_test_client=phttp)
    psock.get_received()

    data, _ = report()
    events = [m["name"] for m in psock.get_received()]
    assert "report_new" in events
    nearby = [m for m in sock.get_received() if m["name"] == "nearby_report"]
    assert nearby and "reporter_phone" not in nearby[0]["args"][0]  # summaries only
    sock.disconnect()
    psock.disconnect()


def test_unhandled_errors_return_calm_json(app, client, make_user, login, monkeypatch):
    login(client, make_user("paramedic"))
    from app.blueprints import paramedic as pm

    def explode(*a, **k):
        raise RuntimeError("database on fire")

    monkeypatch.setattr(pm, "match_hospitals", explode)
    e = Emergency(reference="MD-TEST-1", situation="other", status="claimed",
                  paramedic_id=User.query.first().id)
    db.session.add(e)
    db.session.commit()
    resp = client.get(f"/paramedic/api/case/{e.id}/matches")
    assert resp.status_code == 500
    assert "112" in resp.get_json()["error"]
    assert "fire" not in resp.get_data(as_text=True)


def test_socket_auth_holds_across_multiple_app_instances():
    """Regression: handlers must bind to every Socket.IO server, not just the first."""
    from app import create_app
    for _ in range(2):
        other = create_app("testing")
        with other.app_context():
            db.create_all()
            anon = socketio.test_client(other, flask_test_client=other.test_client())
            assert not anon.is_connected()
            db.drop_all()
