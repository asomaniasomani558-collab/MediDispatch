"""Civilian PWA API: reporting, GPS pings, consented photos, retention."""

from __future__ import annotations

import io
from datetime import timedelta

from PIL import Image

from app.extensions import db
from app.models import CivilianSession, Emergency, Media
from app.models.base import utcnow
from app.services.media import purge_expired
from app.services.security import normalize_ghana_phone

H = "X-Civilian-Token"


def jpeg_bytes(size=(640, 480), with_gps_exif=False):
    img = Image.new("RGB", size, (200, 30, 40))
    buf = io.BytesIO()
    if with_gps_exif:
        exif = Image.Exif()
        exif[0x010F] = "SecretPhoneMaker"   # Make
        exif[0x8825] = {1: "N", 2: (6.0, 41.0, 18.0)}  # GPSInfo
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def test_page_renders_with_first_aid_and_112(client):
    resp = client.get("/civilian/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Get help" in html and "tel:112" in html
    assert "first-aid-data" in html and "Cool the burn" in html


def test_report_creates_emergency(client, report):
    data, token = report(situation="bleeding")
    assert data["reference"].startswith("MD-")
    assert data["first_aid"] and "Press firmly" in data["first_aid"][0]
    e = Emergency.query.filter_by(reference=data["reference"]).one()
    assert e.status == "reported" and e.situation == "bleeding"
    assert e.reporter_phone == "+233241234567"
    assert e.lat == 6.6885
    # Only a hash of the token is stored.
    assert CivilianSession.query.one().token_hash != token


def test_report_validation(client):
    resp = client.post("/civilian/api/report", json={"name": "", "phone": "12", "situation": "aliens"})
    assert resp.status_code == 422
    assert set(resp.get_json()["fields"]) == {"name", "phone", "situation"}


def test_report_without_gps_still_accepted(client):
    resp = client.post("/civilian/api/report", json={"name": "Kojo", "phone": "0201234567", "situation": "other"})
    assert resp.status_code == 201
    assert Emergency.query.one().location is None


def test_phone_normalisation():
    assert normalize_ghana_phone("024 123 4567") == "+233241234567"
    assert normalize_ghana_phone("+233 24 123 4567") == "+233241234567"
    assert normalize_ghana_phone("233241234567") == "+233241234567"
    assert normalize_ghana_phone("+44 7700 900123") == "+447700900123"
    assert normalize_ghana_phone("0123") is None
    assert normalize_ghana_phone("+2331234") is None


def test_gps_ping_updates_location(client, report):
    _, token = report()
    resp = client.post("/civilian/api/ping", headers={H: token}, json={"lat": 6.7, "lon": -1.61, "acc": 8})
    assert resp.status_code == 200 and resp.get_json()["accepted"] is True
    assert Emergency.query.one().location == {"lat": 6.7, "lon": -1.61, "acc": 8}


def test_gps_ping_rejects_garbage(client, report):
    _, token = report()
    resp = client.post("/civilian/api/ping", headers={H: token}, json={"lat": 999, "lon": "x"})
    assert resp.get_json()["accepted"] is False


def test_ping_requires_token(client, report):
    report()
    assert client.post("/civilian/api/ping", json={"lat": 6.7, "lon": -1.6}).status_code == 401
    assert client.post("/civilian/api/ping", headers={H: "forged"}, json={"lat": 6.7, "lon": -1.6}).status_code == 401


def test_token_expires(client, report):
    _, token = report()
    s = CivilianSession.query.one()
    s.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert client.get("/civilian/api/status", headers={H: token}).status_code == 401


def test_status_shows_no_staff_pii(client, report):
    _, token = report()
    status = client.get("/civilian/api/status", headers={H: token}).get_json()["status"]
    assert status["status"] == "reported"
    assert "paramedic_name" not in status and "reporter_phone" not in status


def test_photo_requires_consent(client, report):
    _, token = report()
    resp = client.post("/civilian/api/photo", headers={H: token},
                       data={"photo": (io.BytesIO(jpeg_bytes()), "p.jpg")}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert Media.query.count() == 0


def test_photo_upload_strips_exif_and_sets_30_day_expiry(client, report):
    _, token = report()
    resp = client.post("/civilian/api/photo", headers={H: token},
                       data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes(with_gps_exif=True)), "p.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    m = Media.query.one()
    stored = Image.open(io.BytesIO(m.data))
    assert stored.format == "JPEG"
    assert len(stored.getexif()) == 0              # GPS + device metadata stripped
    assert abs((m.expires_at - m.created_at) - timedelta(days=30)) < timedelta(seconds=1)
    assert m.consent_given is True


def test_photo_rejects_non_images(client, report):
    _, token = report()
    resp = client.post("/civilian/api/photo", headers={H: token},
                       data={"consent": "yes", "photo": (io.BytesIO(b"<script>alert(1)</script>"), "x.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 422


def test_photo_resized(client, report, app):
    _, token = report()
    client.post("/civilian/api/photo", headers={H: token},
                data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes((4000, 3000))), "p.jpg")},
                content_type="multipart/form-data")
    m = Media.query.one()
    assert max(m.width, m.height) <= app.config["MEDIA_MAX_DIMENSION"]


def test_photo_limit(client, report, app):
    _, token = report()
    for _ in range(app.config["MEDIA_MAX_PER_EMERGENCY"]):
        assert client.post("/civilian/api/photo", headers={H: token},
                           data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes()), "p.jpg")},
                           content_type="multipart/form-data").status_code == 201
    resp = client.post("/civilian/api/photo", headers={H: token},
                       data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes()), "p.jpg")},
                       content_type="multipart/form-data")
    assert resp.status_code == 422


def test_media_auto_deleted_after_retention(client, report):
    _, token = report()
    client.post("/civilian/api/photo", headers={H: token},
                data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes()), "p.jpg")},
                content_type="multipart/form-data")
    assert purge_expired() == 0
    assert purge_expired(now=utcnow() + timedelta(days=29)) == 0
    assert purge_expired(now=utcnow() + timedelta(days=30, minutes=1)) == 1
    assert Media.query.count() == 0
    assert Emergency.query.count() == 1  # the case record itself is kept


def test_expired_media_hidden_before_purge(client, report):
    _, token = report()
    client.post("/civilian/api/photo", headers={H: token},
                data={"consent": "yes", "photo": (io.BytesIO(jpeg_bytes()), "p.jpg")},
                content_type="multipart/form-data")
    m = Media.query.one()
    m.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert Emergency.query.one().live_media() == []


def test_cancel_only_before_claim(client, report):
    _, token = report()
    resp = client.post("/civilian/api/cancel", headers={H: token}, json={})
    assert resp.status_code == 200
    assert Emergency.query.one().status == "cancelled"


def test_rate_limit_on_reports(app, client):
    app.config["CIVILIAN_REPORTS_PER_IP_PER_10MIN"] = 2
    body = {"name": "Kojo", "phone": "0201234567", "situation": "other"}
    assert client.post("/civilian/api/report", json=body).status_code == 201
    assert client.post("/civilian/api/report", json=body).status_code == 201
    assert client.post("/civilian/api/report", json=body).status_code == 429


def test_service_worker_scope_header(client):
    resp = client.get("/civilian/sw.js")
    assert resp.headers["Service-Worker-Allowed"] == "/civilian/"
