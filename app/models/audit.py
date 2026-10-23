"""Append-only audit log of who accessed which patient records.

Append-only is enforced in three layers:

1. ORM ``before_update`` / ``before_delete`` mapper events raise.
2. A session ``do_orm_execute`` hook rejects bulk ``UPDATE`` / ``DELETE``
   statements aimed at the table.
3. On PostgreSQL, a trigger (created with the table) rejects UPDATE/DELETE at
   the database level, so even raw SQL from the app user cannot rewrite history.

Each row also carries a SHA-256 hash chained to the previous row, so any
tampering by a database superuser is detectable (``services.audit.verify_chain``).
"""

from __future__ import annotations

from sqlalchemy import DDL, event
from sqlalchemy.orm import Session

from ..extensions import db
from .base import utcnow


class AuditLogImmutableError(RuntimeError):
    """Raised on any attempt to modify or delete an audit row."""


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)
    username = db.Column(db.String(64), nullable=True)
    role = db.Column(db.String(32), nullable=True)
    action = db.Column(db.String(48), nullable=False, index=True)
    emergency_id = db.Column(db.Integer, nullable=True, index=True)
    emergency_reference = db.Column(db.String(24), nullable=True)
    resource = db.Column(db.String(120), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    detail = db.Column(db.String(500), nullable=True)
    prev_hash = db.Column(db.String(64), nullable=False)
    entry_hash = db.Column(db.String(64), nullable=False, unique=True)


@event.listens_for(AuditLog, "before_update")
def _block_update(mapper, connection, target):  # noqa: ARG001
    raise AuditLogImmutableError("Audit log entries are append-only and cannot be modified")


@event.listens_for(AuditLog, "before_delete")
def _block_delete(mapper, connection, target):  # noqa: ARG001
    raise AuditLogImmutableError("Audit log entries are append-only and cannot be deleted")


@event.listens_for(Session, "do_orm_execute")
def _block_bulk(orm_execute_state):
    if orm_execute_state.is_update or orm_execute_state.is_delete:
        for mapper in orm_execute_state.all_mappers:
            if mapper.class_ is AuditLog:
                raise AuditLogImmutableError("Bulk UPDATE/DELETE on audit_logs is forbidden")


_PG_TRIGGER = DDL(
    """
    CREATE OR REPLACE FUNCTION audit_logs_block_mutation() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_logs is append-only';
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS audit_logs_no_mutation ON audit_logs;
    CREATE TRIGGER audit_logs_no_mutation
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation();
    """
).execute_if(dialect="postgresql")

event.listen(AuditLog.__table__, "after_create", _PG_TRIGGER)
