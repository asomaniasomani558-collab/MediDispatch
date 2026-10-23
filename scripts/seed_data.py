#!/usr/bin/env python3
"""Seed MediDispatch GH with Ghana hospitals and a Super Admin.

Usage (from the project root):

    python scripts/seed_data.py                    # tables + hospitals + super admin
    python scripts/seed_data.py --demo             # + demo paramedic / hospital staff + sample reports
    APP_ENV=production python scripts/seed_data.py

Passwords come from environment variables when set, otherwise strong random
passwords are generated and printed ONCE:

    SEED_ADMIN_USERNAME  (default: superadmin)
    SEED_ADMIN_PASSWORD
    SEED_DEMO_PASSWORD   (shared by demo accounts, --demo only)

Re-running is safe: hospitals are upserted by code; existing users are left
unchanged (their passwords are never overwritten).

Hospital coordinates are APPROXIMATE and bed / specialist figures are
SAMPLE DATA. Verify every value with each facility before go-live.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Emergency, Hospital, User  # noqa: E402
from app.models.base import utcnow  # noqa: E402
from app.models.user import ROLE_HOSPITAL_ADMIN, ROLE_PARAMEDIC, ROLE_SUPER_ADMIN  # noqa: E402
from app.services import audit  # noqa: E402

ALL_SPEC = ["trauma_surgeon", "general_surgeon", "neurosurgeon", "obstetrician",
            "cardiologist", "paediatrician", "burns_specialist", "anaesthetist"]
ALL_FAC = ["ct_scanner", "blood_bank", "burns_unit", "maternity", "cath_lab"]


def _flags(keys, on):
    return {k: k in on for k in keys}


# (code, name, region, district, level, lat, lon, phone, er_total, er_free, icu_total, icu_free, ward_free, specialists, facilities)
HOSPITALS = [
    ("KBTH", "Korle Bu Teaching Hospital", "Greater Accra", "Korle Klottey", "Teaching", 5.5365, -0.2275, "0302 674 000",
     40, 9, 20, 3, 60, ALL_SPEC, ALL_FAC),
    ("KATH", "Komfo Anokye Teaching Hospital", "Ashanti", "Kumasi Metropolitan", "Teaching", 6.6977, -1.6298, "0322 022 301",
     35, 7, 16, 2, 48, ALL_SPEC, ALL_FAC),
    ("TTH", "Tamale Teaching Hospital", "Northern", "Tamale Metropolitan", "Teaching", 9.4170, -0.8300, "0372 022 454",
     24, 6, 10, 2, 30, ["trauma_surgeon", "general_surgeon", "obstetrician", "paediatrician", "anaesthetist", "cardiologist"],
     ["ct_scanner", "blood_bank", "maternity"]),
    ("CCTH", "Cape Coast Teaching Hospital", "Central", "Cape Coast Metropolitan", "Teaching", 5.1300, -1.2810, "0332 134 870",
     22, 5, 10, 1, 26, ["trauma_surgeon", "general_surgeon", "obstetrician", "paediatrician", "anaesthetist", "neurosurgeon"],
     ["ct_scanner", "blood_bank", "maternity"]),
    ("HTH", "Ho Teaching Hospital", "Volta", "Ho Municipal", "Teaching", 6.6010, 0.4710, "0362 026 900",
     20, 6, 8, 2, 22, ["general_surgeon", "obstetrician", "paediatrician", "anaesthetist", "cardiologist"],
     ["ct_scanner", "blood_bank", "maternity"]),
    ("37MH", "37 Military Hospital", "Greater Accra", "Ayawaso East", "Military", 5.5872, -0.1835, "0302 776 111",
     30, 8, 12, 3, 40, ["trauma_surgeon", "general_surgeon", "neurosurgeon", "obstetrician", "anaesthetist", "burns_specialist"],
     ["ct_scanner", "blood_bank", "burns_unit", "maternity"]),
    ("GARH", "Greater Accra Regional Hospital (Ridge)", "Greater Accra", "Osu Klottey", "Regional", 5.5630, -0.1985, "0302 228 315",
     28, 6, 12, 2, 35, ["general_surgeon", "obstetrician", "paediatrician", "cardiologist", "anaesthetist"],
     ["ct_scanner", "blood_bank", "maternity", "cath_lab"]),
    ("ENRH", "Effia Nkwanta Regional Hospital", "Western", "Sekondi-Takoradi Metropolitan", "Regional", 4.9220, -1.7600, "0312 046 340",
     18, 4, 6, 1, 20, ["trauma_surgeon", "general_surgeon", "obstetrician", "anaesthetist"],
     ["blood_bank", "maternity"]),
    ("ERHK", "Eastern Regional Hospital, Koforidua", "Eastern", "New Juaben South", "Regional", 6.0920, -0.2600, "0342 022 101",
     16, 4, 6, 1, 18, ["general_surgeon", "obstetrician", "paediatrician", "anaesthetist"],
     ["blood_bank", "maternity"]),
    ("BRH", "Bono Regional Hospital, Sunyani", "Bono", "Sunyani Municipal", "Regional", 7.3400, -2.3300, "0352 027 101",
     14, 3, 6, 1, 16, ["general_surgeon", "obstetrician", "anaesthetist"],
     ["blood_bank", "maternity"]),
    ("UERH", "Upper East Regional Hospital, Bolgatanga", "Upper East", "Bolgatanga Municipal", "Regional", 10.7900, -0.8500, "0382 022 101",
     12, 3, 4, 1, 14, ["general_surgeon", "obstetrician", "anaesthetist"],
     ["blood_bank", "maternity"]),
    ("UWRH", "Upper West Regional Hospital, Wa", "Upper West", "Wa Municipal", "Regional", 10.0600, -2.5000, "0392 022 101",
     12, 3, 4, 0, 12, ["general_surgeon", "obstetrician"],
     ["blood_bank", "maternity"]),
    ("TGH", "Tema General Hospital", "Greater Accra", "Tema Metropolitan", "District", 5.6700, -0.0100, "0303 202 711",
     14, 3, 4, 1, 16, ["general_surgeon", "obstetrician", "paediatrician"],
     ["blood_bank", "maternity"]),
    ("KNUSTH", "KNUST University Hospital", "Ashanti", "Oforikrom Municipal", "District", 6.6830, -1.5700, "0322 060 307",
     10, 3, 2, 0, 12, ["general_surgeon", "paediatrician"],
     ["maternity"]),
    ("MGH", "Manhyia Government Hospital", "Ashanti", "Manhyia South", "District", 6.7090, -1.6150, "0322 024 141",
     10, 2, 2, 0, 10, ["general_surgeon", "obstetrician"],
     ["maternity"]),
    ("SGH", "Suntreso Government Hospital", "Ashanti", "Bantama", "District", 6.6990, -1.6450, "0322 027 410",
     10, 2, 2, 0, 10, ["general_surgeon", "obstetrician"],
     ["maternity"]),
]


def _password(env_name: str) -> tuple[str, bool]:
    value = os.environ.get(env_name)
    if value:
        return value, False
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(18)), True


def seed_hospitals() -> int:
    now = utcnow()
    count = 0
    for (code, name, region, district, level, lat, lon, phone, er_t, er_f, icu_t, icu_f,
         ward, spec, fac) in HOSPITALS:
        h = Hospital.query.filter_by(code=code).first() or Hospital(code=code)
        h.name, h.region, h.district, h.level = name, region, district, level
        h.latitude, h.longitude, h.phone = lat, lon, phone
        h.er_beds_total, h.er_beds_available = er_t, er_f
        h.icu_beds_total, h.icu_beds_available = icu_t, icu_f
        h.general_beds_available = ward
        h.specialists = _flags(ALL_SPEC, spec)
        h.facilities = _flags(ALL_FAC, fac)
        h.is_active = True
        h.capacity_updated_at = now
        h.capacity_updated_by = "seed"
        db.session.add(h)
        count += 1
    db.session.commit()
    return count


def ensure_user(username, full_name, role, password, hospital=None) -> bool:
    if User.query.filter_by(username=username).first():
        return False
    user = User(username=username, full_name=full_name, role=role,
                hospital_id=hospital.id if hospital else None, is_enabled=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return True


def seed_demo(demo_password: str) -> list[str]:
    created = []

    # Paramedics (not tied to a hospital)
    for username, name in (
        ("medic.kumasi", "Akosua Mensah (Demo Paramedic)"),
        ("medic.accra", "Kofi Boateng (Demo Paramedic)"),
    ):
        if ensure_user(username, name, ROLE_PARAMEDIC, demo_password):
            created.append(username)

    # One emergency-desk login per active hospital: <code>.er, e.g. kath.er, tth.er, 37mh.er
    for hospital in Hospital.query.filter_by(is_active=True).order_by(Hospital.code).all():
        username = f"{hospital.code.lower()}.er"
        name = f"{hospital.name} Emergency Desk (Demo)"
        if ensure_user(username, name, ROLE_HOSPITAL_ADMIN, demo_password, hospital):
            created.append(username)

    if Emergency.query.count() == 0:
        samples = [
            ("accident", "Ama Owusu", "+233241234567", 6.6885, -1.6244),
            ("bleeding", "Yaw Asante", "+233201112233", 6.7012, -1.6100),
            ("breathing", "Efua Darko", "+233551239876", 5.5560, -0.1969),
        ]
        for situation, name, phone, lat, lon in samples:
            e = Emergency(reference=Emergency.new_reference(), situation=situation, status="reported",
                          reporter_name=name, reporter_phone=phone,
                          location={"lat": lat, "lon": lon, "acc": 15}, location_updated_at=utcnow())
            db.session.add(e)
        db.session.commit()
    return created

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="also create demo staff accounts and sample reports")
    args = parser.parse_args()

    app = create_app(os.environ.get("APP_ENV", "development"))
    with app.app_context():
        db.create_all()
        n = seed_hospitals()
        print(f"[ok] {n} hospitals upserted (coordinates approximate, capacity is sample data)")

        admin_user = os.environ.get("SEED_ADMIN_USERNAME", "superadmin").lower()
        admin_pw, generated = _password("SEED_ADMIN_PASSWORD")
        if ensure_user(admin_user, "System Super Admin", ROLE_SUPER_ADMIN, admin_pw):
            print(f"[ok] super admin created: {admin_user}")
            if generated:
                print(f"     password (shown once - store it securely): {admin_pw}")
            audit.record("SEED_SUPER_ADMIN", user=None, detail=admin_user)
        else:
            print(f"[--] super admin '{admin_user}' already exists (password unchanged)")

        if args.demo:
            demo_pw, generated = _password("SEED_DEMO_PASSWORD")
            created = seed_demo(demo_pw)
            if created:
                print(f"[ok] demo accounts: {', '.join(created)}")
                if generated:
                    print(f"     shared demo password (shown once): {demo_pw}")
            else:
                print("[--] demo accounts already exist")
            print("     demo bystander reports present:", Emergency.query.count())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
