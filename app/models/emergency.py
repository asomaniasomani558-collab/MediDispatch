"""Emergencies and the anonymous civilian sessions that report them."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from ..extensions import db
from ..services.encryption import EncryptedJSON, EncryptedText
from .base import utcnow

# Situations a bystander can pick. Order = order on the civilian screen.
SITUATIONS = {
    "accident": "Road Accident",
    "bleeding": "Severe Bleeding",
    "breathing": "Difficulty Breathing",
    "unconscious": "Unconscious / Collapsed",
    "chest_pain": "Chest Pain",
    "seizure": "Seizure / Fits",
    "burns": "Burns",
    "childbirth": "Childbirth / Pregnancy",
    "poisoning": "Poisoning / Overdose",
    "snakebite": "Snake / Animal Bite",
    "drowning": "Drowning",
    "other": "Other Emergency",
}

STATUS_REPORTED = "reported"        # bystander report, not yet claimed
STATUS_CLAIMED = "claimed"          # paramedic has taken it
STATUS_TRIAGED = "triaged"          # vitals entered & triaged
STATUS_EN_ROUTE = "en_route"        # hospital assigned, transporting
STATUS_ACKNOWLEDGED = "acknowledged"  # hospital confirmed it is ready
STATUS_ARRIVED = "arrived"          # patient handed over
STATUS_RESOLVED = "resolved"
STATUS_CANCELLED = "cancelled"

STATUSES = {
    STATUS_REPORTED: "Reported",
    STATUS_CLAIMED: "Claimed",
    STATUS_TRIAGED: "Triaged",
    STATUS_EN_ROUTE: "En Route",
    STATUS_ACKNOWLEDGED: "Hospital Ready",
    STATUS_ARRIVED: "Arrived",
    STATUS_RESOLVED: "Resolved",
    STATUS_CANCELLED: "Cancelled",
}

OPEN_STATUSES = (
    STATUS_REPORTED, STATUS_CLAIMED, STATUS_TRIAGED,
    STATUS_EN_ROUTE, STATUS_ACKNOWLEDGED, STATUS_ARRIVED,
)

SOURCE_CIVILIAN = "civilian"
SOURCE_PARAMEDIC = "paramedic"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CivilianSession(db.Model):
    """A zero-login bystander session.

    Only a SHA-256 hash of the bearer token is stored, so a database leak does
    not let anyone impersonate a reporter.
    """

    __tablename__ = "civilian_sessions"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    ip_hash = db.Column(db.String(64), nullable=True)

    emergencies = db.relationship("Emergency", back_populates="civilian_session")

    @classmethod
    def issue(cls, hours: int, ip: str | None = None) -> tuple["CivilianSession", str]:
        token = secrets.token_urlsafe(32)
        session = cls(
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=hours),
            ip_hash=hashlib.sha256((ip or "").encode()).hexdigest() if ip else None,
        )
        return session, token

    @classmethod
    def from_token(cls, token: str | None) -> "CivilianSession | None":
        if not token or len(token) > 128:
            return None
        found = cls.query.filter_by(token_hash=hash_token(token)).first()
        if not found or found.revoked or found.expires_at < utcnow():
            return None
        return found


class Emergency(db.Model):
    __tablename__ = "emergencies"

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(24), unique=True, nullable=False, index=True)
    source = db.Column(db.String(16), nullable=False, default=SOURCE_CIVILIAN)
    situation = db.Column(db.String(24), nullable=False, default="other")
    status = db.Column(db.String(16), nullable=False, default=STATUS_REPORTED, index=True)

    # --- Encrypted personal / clinical data (Act 843) -----------------------
    reporter_name = db.Column(EncryptedText, nullable=True)
    reporter_phone = db.Column(EncryptedText, nullable=True)
    location = db.Column(EncryptedJSON, nullable=True)   # {lat, lon, acc}
    vitals = db.Column(EncryptedJSON, nullable=True)
    symptoms = db.Column(EncryptedText, nullable=True)
    triage = db.Column(EncryptedJSON, nullable=True)     # full triage result
    notes = db.Column(EncryptedText, nullable=True)

    # --- Non-identifying triage summary (needed for sorting / dashboards) ---
    mews_score = db.Column(db.Integer, nullable=True)
    mews_severity = db.Column(db.String(12), nullable=True)
    severity = db.Column(db.String(12), nullable=True, index=True)   # final
    severity_rank = db.Column(db.Integer, nullable=False, default=0)
    ai_status = db.Column(db.String(16), nullable=False, default="not_run")

    # --- Relations ----------------------------------------------------------
    civilian_session_id = db.Column(db.Integer, db.ForeignKey("civilian_sessions.id"), nullable=True)
    paramedic_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey("hospitals.id"), nullable=True)

    civilian_session = db.relationship("CivilianSession", back_populates="emergencies")
    paramedic = db.relationship("User", foreign_keys=[paramedic_id])
    hospital = db.relationship("Hospital", foreign_keys=[hospital_id])
    media = db.relationship(
        "Media", back_populates="emergency", cascade="all, delete-orphan", lazy="selectin",
    )

    # --- Timeline -----------------------------------------------------------
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    location_updated_at = db.Column(db.DateTime, nullable=True)
    claimed_at = db.Column(db.DateTime, nullable=True)
    triaged_at = db.Column(db.DateTime, nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    arrived_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def new_reference() -> str:
        stamp = utcnow().strftime("%y%m%d")
        return f"MD-{stamp}-{secrets.token_hex(3).upper()}"

    @property
    def situation_label(self) -> str:
        return SITUATIONS.get(self.situation, self.situation)

    @property
    def status_label(self) -> str:
        return STATUSES.get(self.status, self.status)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def lat(self) -> float | None:
        return (self.location or {}).get("lat")

    @property
    def lon(self) -> float | None:
        return (self.location or {}).get("lon")

    def live_media(self):
        now = utcnow()
        return [m for m in self.media if m.expires_at > now]

    def public_summary(self) -> dict:
        """Non-identifying summary safe for broadcast feeds."""
        return {
            "id": self.id,
            "reference": self.reference,
            "situation": self.situation,
            "situation_label": self.situation_label,
            "status": self.status,
            "status_label": self.status_label,
            "severity": self.severity,
            "mews_score": self.mews_score,
            "source": self.source,
            "hospital_id": self.hospital_id,
            "paramedic_id": self.paramedic_id,
            "photo_count": len(self.live_media()),
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }

    def full_record(self) -> dict:
        """Complete record including decrypted personal data.

        Callers MUST write an audit entry (``services.audit.record_view``)
        before returning this to anyone.
        """
        data = self.public_summary()
        data.update({
            "reporter_name": self.reporter_name,
            "reporter_phone": self.reporter_phone,
            "location": self.location,
            "location_updated_at": self.location_updated_at.isoformat() + "Z" if self.location_updated_at else None,
            "vitals": self.vitals,
            "symptoms": self.symptoms,
            "triage": self.triage,
            "notes": self.notes,
            "ai_status": self.ai_status,
            "mews_severity": self.mews_severity,
            "hospital_name": self.hospital.name if self.hospital else None,
            "paramedic_name": self.paramedic.full_name if self.paramedic else None,
            "media": [m.meta() for m in self.live_media()],
        })
        return data
