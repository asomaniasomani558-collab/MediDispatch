"""Hospitals and their live capacity."""

from __future__ import annotations

from ..extensions import db
from .base import utcnow

# Specialists a hospital can flag as "on duty right now".
SPECIALISTS = {
    "trauma_surgeon": "Trauma Surgeon",
    "general_surgeon": "General Surgeon",
    "neurosurgeon": "Neurosurgeon",
    "obstetrician": "Obstetrician",
    "cardiologist": "Cardiologist",
    "paediatrician": "Paediatrician",
    "burns_specialist": "Burns / Plastics",
    "anaesthetist": "Anaesthetist",
}

# Facilities that change less often.
FACILITIES = {
    "ct_scanner": "CT Scanner",
    "blood_bank": "Blood Bank",
    "burns_unit": "Burns Unit",
    "maternity": "Maternity",
    "cath_lab": "Cath Lab",
}

LEVELS = ["Teaching", "Regional", "District", "Military", "Private", "Polyclinic"]

GHANA_REGIONS = [
    "Greater Accra", "Ashanti", "Western", "Western North", "Central", "Eastern",
    "Volta", "Oti", "Northern", "Savannah", "North East", "Upper East",
    "Upper West", "Bono", "Bono East", "Ahafo",
]


class Hospital(db.Model):
    __tablename__ = "hospitals"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    code = db.Column(db.String(16), nullable=False, unique=True)
    region = db.Column(db.String(40), nullable=False)
    district = db.Column(db.String(80), nullable=True)
    level = db.Column(db.String(20), nullable=False, default="District")
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    phone = db.Column(db.String(32), nullable=True)

    er_beds_total = db.Column(db.Integer, nullable=False, default=0)
    er_beds_available = db.Column(db.Integer, nullable=False, default=0)
    icu_beds_total = db.Column(db.Integer, nullable=False, default=0)
    icu_beds_available = db.Column(db.Integer, nullable=False, default=0)
    general_beds_available = db.Column(db.Integer, nullable=False, default=0)

    specialists = db.Column(db.JSON, nullable=False, default=dict)
    facilities = db.Column(db.JSON, nullable=False, default=dict)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    capacity_updated_at = db.Column(db.DateTime, nullable=True)
    capacity_updated_by = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    staff = db.relationship("User", back_populates="hospital")

    def specialist_on(self, key: str) -> bool:
        return bool((self.specialists or {}).get(key))

    def facility_on(self, key: str) -> bool:
        return bool((self.facilities or {}).get(key))

    def to_matching_dict(self) -> dict:
        """Plain dict consumed by the (pure) matching service."""
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "level": self.level,
            "region": self.region,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "phone": self.phone,
            "is_active": self.is_active,
            "er_beds_available": self.er_beds_available,
            "icu_beds_available": self.icu_beds_available,
            "general_beds_available": self.general_beds_available,
            "specialists": dict(self.specialists or {}),
            "facilities": dict(self.facilities or {}),
            "capacity_updated_at": self.capacity_updated_at.isoformat() + "Z" if self.capacity_updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Hospital {self.code}>"
