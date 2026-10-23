"""Bystander photos — encrypted in the database, auto-deleted after 30 days."""

from __future__ import annotations

from sqlalchemy.orm import deferred

from ..extensions import db
from ..services.encryption import EncryptedBytes
from .base import utcnow


class Media(db.Model):
    __tablename__ = "media"

    id = db.Column(db.Integer, primary_key=True)
    emergency_id = db.Column(db.Integer, db.ForeignKey("emergencies.id"), nullable=False, index=True)
    # Deferred: listing photos never decrypts the blobs.
    data = deferred(db.Column(EncryptedBytes, nullable=False))
    mime_type = db.Column(db.String(32), nullable=False, default="image/jpeg")
    size_bytes = db.Column(db.Integer, nullable=False)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    sha256 = db.Column(db.String(64), nullable=False)
    consent_given = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    emergency = db.relationship("Emergency", back_populates="media")

    def meta(self) -> dict:
        return {
            "id": self.id,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "created_at": self.created_at.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z",
        }
