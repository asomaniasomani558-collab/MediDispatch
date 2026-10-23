"""Audit logging (append-only, hash-chained).

``record_view`` is called before ANY patient-identifying data is returned. It
commits immediately and fails closed: if the access cannot be logged, the
caller gets an ``AuditWriteError`` and must not show the data.
"""

from __future__ import annotations

import hashlib
import logging

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.audit import AuditLog
from ..models.base import utcnow

log = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64
_PG_LOCK_ID = 7_274_274  # arbitrary constant for pg_advisory_xact_lock


class AuditWriteError(RuntimeError):
    """The access could not be recorded - do not reveal the data."""


def _canonical(entry: AuditLog) -> str:
    parts = [
        entry.prev_hash, entry.created_at.isoformat(), str(entry.user_id or ""),
        entry.username or "", entry.role or "", entry.action, str(entry.emergency_id or ""),
        entry.emergency_reference or "", entry.resource or "", entry.ip_address or "",
        entry.detail or "",
    ]
    return "|".join(parts)


def compute_hash(entry: AuditLog) -> str:
    return hashlib.sha256(_canonical(entry).encode("utf-8")).hexdigest()


def _client_ip() -> str | None:
    if not has_request_context():
        return None
    # ProxyFix (enabled in production) has already resolved X-Forwarded-For.
    return (request.remote_addr or "")[:64] or None


def record(action: str, emergency=None, resource: str | None = None,
           detail: str | None = None, user=None, commit: bool = True) -> AuditLog:
    """Append one audit entry."""
    actor = user
    if actor is None and has_request_context():
        try:
            actor = current_user if current_user.is_authenticated else None
        except Exception:  # noqa: BLE001 - outside login context
            actor = None

    try:
        if db.engine.dialect.name == "postgresql":
            db.session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PG_LOCK_ID})
        last = db.session.query(AuditLog.entry_hash).order_by(AuditLog.id.desc()).first()
        entry = AuditLog(
            created_at=utcnow(),
            user_id=getattr(actor, "id", None),
            username=getattr(actor, "username", None) or ("civilian" if actor is None else None),
            role=getattr(actor, "role", None) or ("civilian" if actor is None else None),
            action=action[:48],
            emergency_id=getattr(emergency, "id", None),
            emergency_reference=getattr(emergency, "reference", None),
            resource=(resource or "")[:120] or None,
            ip_address=_client_ip(),
            user_agent=(request.headers.get("User-Agent", "")[:200] if has_request_context() else None),
            detail=(detail or "")[:500] or None,
            prev_hash=last[0] if last else GENESIS_HASH,
        )
        entry.entry_hash = compute_hash(entry)
        db.session.add(entry)
        if commit:
            db.session.commit()
        return entry
    except SQLAlchemyError as exc:
        db.session.rollback()
        log.error("AUDIT WRITE FAILED for action=%s: %s", action, exc)
        raise AuditWriteError("Access could not be audited") from exc


def record_view(emergency, resource: str = "emergency", detail: str | None = None) -> AuditLog:
    """Log that the current user viewed an identifiable patient record."""
    return record("VIEW_PATIENT_RECORD", emergency=emergency, resource=resource, detail=detail)


def verify_chain(batch: int = 1000) -> dict:
    """Recompute the hash chain. Returns ``{ok, checked, first_bad_id}``."""
    prev = GENESIS_HASH
    checked = 0
    last_id = 0
    while True:
        rows = (AuditLog.query.filter(AuditLog.id > last_id)
                .order_by(AuditLog.id.asc()).limit(batch).all())
        if not rows:
            break
        for row in rows:
            if row.prev_hash != prev or compute_hash(row) != row.entry_hash:
                return {"ok": False, "checked": checked, "first_bad_id": row.id}
            prev = row.entry_hash
            checked += 1
            last_id = row.id
    return {"ok": True, "checked": checked, "first_bad_id": None}
