"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys

import pytest
from flask import g

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Hospital, User  # noqa: E402
from app.models.base import utcnow  # noqa: E402
from app.services.security import limiter  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture()
def app():
    application = create_app("testing")

    @application.before_request
    def _fresh_login_state():
        # The fixture keeps one app context open for the whole test so tests
        # can use db.session directly. Flask reuses that context for every
        # test-client request, so Flask-Login's per-request user cache in `g`
        # would leak between clients. Production gets a fresh context per
        # request; emulate that here.
        g.pop("_login_user", None)

    with application.app_context():
        db.create_all()
        limiter._hits.clear()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_hospital(app):
    counter = {"n": 0}

    def _make(**kw):
        counter["n"] += 1
        n = counter["n"]
        defaults = dict(
            name=f"Test Hospital {n}", code=f"TH{n}", region="Ashanti", level="Regional",
            latitude=6.69, longitude=-1.62, er_beds_total=10, er_beds_available=5,
            icu_beds_total=4, icu_beds_available=2, general_beds_available=10,
            specialists={}, facilities={}, is_active=True, capacity_updated_at=utcnow(),
        )
        defaults.update(kw)
        h = Hospital(**defaults)
        db.session.add(h)
        db.session.commit()
        return h

    return _make


@pytest.fixture()
def make_user(app):
    def _make(role="paramedic", username=None, hospital=None, password=PASSWORD):
        username = username or f"{role}{User.query.count() + 1}"
        u = User(username=username, full_name=username.title(), role=role,
                 hospital_id=hospital.id if hospital else None, is_enabled=True)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u

    return _make


@pytest.fixture()
def login():
    def _login(client, user, password=PASSWORD):
        resp = client.post("/auth/login", data={"username": user.username, "password": password})
        assert resp.status_code in (302, 303), resp.data[:300]
        return resp

    return _login


@pytest.fixture()
def report(client):
    """Create a bystander report; returns (json, token)."""

    def _report(situation="accident", lat=6.6885, lon=-1.6244, phone="024 123 4567", name="Ama Owusu"):
        resp = client.post("/civilian/api/report", json={
            "name": name, "phone": phone, "situation": situation, "lat": lat, "lon": lon, "acc": 12,
        })
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        return data, data["token"]

    return _report
