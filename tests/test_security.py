"""Security & compliance: encryption at rest, RBAC, CSRF, audit log, sessions."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models import AuditLog, AuditLogImmutableError, Emergency
from app.services import audit
from app.services.encryption import decrypt_str, encrypt_str


# ---------------------------------------------------------------------------
# Encryption at rest
# ---------------------------------------------------------------------------
def test_encrypt_roundtrip(app):
    token = encrypt_str("+233241234567")
    assert token != "+233241234567"
    assert decrypt_str(token) == "+233241234567"


def test_personal_and_clinical_data_encrypted_in_database(app, report):
    data, _ = report(phone="0241234567", name="Ama Owusu")
    e = Emergency.query.filter_by(reference=data["reference"]).one()
    e.vitals = {"heart_rate": 123}
    e.symptoms = "head injury"
    db.session.commit()

    row = db.session.execute(text(
        "SELECT reporter_name, reporter_phone, location, vitals, symptoms FROM emergencies WHERE id = :i"
    ), {"i": e.id}).one()
    raw = " ".join(str(v) for v in row)
    for secret in ("233241234567", "Ama Owusu", "6.6885", "123", "head injury"):
        assert secret not in raw
    # ...but the ORM transparently decrypts.
    db.session.expire_all()
    e = db.session.get(Emergency, e.id)
    assert e.reporter_phone == "+233241234567"
    assert e.vitals == {"heart_rate": 123}


def test_photo_bytes_encrypted_in_database(app, client, report):
    import io

    from tests.test_civilian import jpeg_bytes
    _, token = report()
    resp = client.post("/civilian/api/photo", headers={"X-Civilian-Token": token},
                       data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes()), "p.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 201
    raw = db.session.execute(text("SELECT data FROM media")).scalar_one()
    assert not bytes(raw).startswith(b"\xff\xd8")  # not a plain JPEG
    assert bytes(raw).startswith(b"gAAAA")           # Fernet token


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/paramedic/", "/hospital/", "/admin/", "/admin/audit", "/hospital/api/queue"])
def test_anonymous_blocked(client, path):
    resp = client.get(path)
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert "/auth/login" in resp.headers["Location"]


@pytest.mark.parametrize("path", ["/hospital/", "/hospital/api/queue", "/paramedic/", "/admin/", "/api/emergencies/1"])
def test_civilian_token_cannot_access_staff_routes(client, report, path):
    _, token = report()
    resp = client.get(path, headers={"X-Civilian-Token": token, "Authorization": f"Bearer {token}"})
    assert resp.status_code in (302, 401)


def test_paramedic_cannot_access_admin_or_hospital(client, make_user, login):
    login(client, make_user("paramedic"))
    assert client.get("/admin/").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert client.get("/hospital/").status_code == 403
    assert client.get("/paramedic/").status_code == 200


def test_hospital_staff_cannot_access_paramedic_or_admin(client, make_user, make_hospital, login):
    login(client, make_user("hospital_admin", hospital=make_hospital()))
    assert client.get("/paramedic/").status_code == 403
    assert client.get("/admin/").status_code == 403
    assert client.get("/hospital/").status_code == 200


def test_admin_cannot_use_clinical_apps(client, make_user, login):
    login(client, make_user("super_admin"))
    assert client.get("/admin/").status_code == 200
    assert client.get("/paramedic/").status_code == 403
    assert client.get("/hospital/").status_code == 403


def test_admin_cannot_read_patient_record_by_default(client, make_user, login, report):
    data, _ = report()
    e = Emergency.query.filter_by(reference=data["reference"]).one()
    login(client, make_user("super_admin"))
    assert client.get(f"/api/emergencies/{e.id}").status_code == 404


def test_hospital_staff_without_hospital_blocked(client, make_user, login):
    login(client, make_user("hospital_admin"))
    assert client.get("/hospital/").status_code == 403


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
def test_csrf_enforced_when_enabled(app, client, make_user):
    app.config["WTF_CSRF_ENABLED"] = True
    user = make_user("paramedic")
    resp = client.post("/auth/login", data={"username": user.username, "password": "x"})
    assert resp.status_code == 400
    resp = client.post("/civilian/api/report", json={"name": "A B", "phone": "0241234567", "situation": "other"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "csrf"


def test_csrf_token_accepted(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    token = client.get("/civilian/api/csrf").get_json()["csrf_token"]
    resp = client.post("/civilian/api/report", headers={"X-CSRFToken": token},
                       json={"name": "Ama", "phone": "0241234567", "situation": "other"})
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def test_audit_log_is_append_only(app):
    entry = audit.record("TEST_EVENT", detail="x")
    entry.detail = "tampered"
    with pytest.raises(AuditLogImmutableError):
        db.session.commit()
    db.session.rollback()
    with pytest.raises(AuditLogImmutableError):
        db.session.delete(db.session.get(AuditLog, entry.id))
        db.session.commit()
    db.session.rollback()
    with pytest.raises(AuditLogImmutableError):
        AuditLog.query.filter_by(id=entry.id).delete()
    db.session.rollback()
    with pytest.raises(AuditLogImmutableError):
        AuditLog.query.update({"detail": "nope"})
    db.session.rollback()
    assert db.session.get(AuditLog, entry.id).detail == "x"


def test_audit_chain_detects_tampering(app):
    for i in range(5):
        audit.record("EVENT", detail=str(i))
    assert audit.verify_chain() == {"ok": True, "checked": 5, "first_bad_id": None}
    if db.engine.dialect.name == "postgresql":
        # The database trigger blocks even raw SQL from the application role.
        with pytest.raises(Exception, match="append-only"):
            db.session.execute(text("UPDATE audit_logs SET detail = 'forged' WHERE id = 3"))
        db.session.rollback()
        # A table owner / superuser could still disable it; the hash chain catches that.
        db.session.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_mutation"))
    # Simulate a DBA editing a row behind the app's back.
    db.session.execute(text("UPDATE audit_logs SET detail = 'forged' WHERE id = 3"))
    db.session.commit()
    result = audit.verify_chain()
    assert result["ok"] is False and result["first_bad_id"] == 3


def test_patient_view_is_audited(client, make_user, login, report):
    data, _ = report()
    medic = make_user("paramedic")
    login(client, medic)
    e = Emergency.query.filter_by(reference=data["reference"]).one()
    assert client.post(f"/paramedic/api/claim/{e.id}").status_code == 200
    before = AuditLog.query.filter_by(action="VIEW_PATIENT_RECORD").count()
    assert client.get(f"/paramedic/case/{e.id}").status_code == 200
    assert client.get(f"/api/emergencies/{e.id}").status_code == 200
    views = AuditLog.query.filter_by(action="VIEW_PATIENT_RECORD", emergency_id=e.id).all()
    assert len(views) == before + 2
    assert all(v.username == medic.username for v in views)


def test_view_withheld_if_audit_fails(client, make_user, login, report, monkeypatch):
    data, _ = report()
    login(client, make_user("paramedic"))
    e = Emergency.query.filter_by(reference=data["reference"]).one()
    client.post(f"/paramedic/api/claim/{e.id}")

    def boom(*a, **k):
        raise audit.AuditWriteError("db down")

    monkeypatch.setattr(audit, "record_view", boom)
    resp = client.get(f"/api/emergencies/{e.id}")
    assert resp.status_code == 503
    assert b"Ama" not in resp.data


# ---------------------------------------------------------------------------
# Authentication hardening
# ---------------------------------------------------------------------------
def test_lockout_after_repeated_failures(client, make_user):
    user = make_user("paramedic")
    for _ in range(5):
        client.post("/auth/login", data={"username": user.username, "password": "wrong"})
    resp = client.post("/auth/login", data={"username": user.username, "password": "correct-horse-battery"})
    assert resp.status_code == 423


def test_disabling_user_kills_live_session(client, make_user, login):
    user = make_user("paramedic")
    login(client, user)
    assert client.get("/paramedic/").status_code == 200
    user.is_enabled = False
    user.rotate_sessions()
    db.session.commit()
    assert client.get("/paramedic/").status_code == 302


def test_password_change_invalidates_sessions(client, make_user, login):
    user = make_user("paramedic")
    login(client, user)
    user.set_password("a-brand-new-password")
    db.session.commit()
    assert client.get("/paramedic/").status_code == 302


def test_open_redirect_blocked(client, make_user):
    user = make_user("paramedic")
    resp = client.post("/auth/login?next=https://evil.example/", data={
        "username": user.username, "password": "correct-horse-battery"})
    assert resp.headers["Location"].endswith("/paramedic/")


def test_security_headers(client):
    resp = client.get("/civilian/")
    csp = resp.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"] == "no-store"


def test_production_refuses_unsafe_config(monkeypatch):
    from app.config import ProductionConfig
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "change-me")
    with pytest.raises(RuntimeError):
        ProductionConfig.validate()
