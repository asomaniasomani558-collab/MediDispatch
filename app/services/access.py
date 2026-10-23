"""Record-level access policy (who may see which patient record)."""

from __future__ import annotations

from flask import current_app

from ..models.user import ROLE_HOSPITAL_ADMIN, ROLE_PARAMEDIC, ROLE_SUPER_ADMIN


def can_view_emergency(user, emergency) -> bool:
    if user is None or not getattr(user, "is_authenticated", False) or emergency is None:
        return False
    if user.role == ROLE_PARAMEDIC:
        return emergency.paramedic_id == user.id
    if user.role == ROLE_HOSPITAL_ADMIN:
        return user.hospital_id is not None and emergency.hospital_id == user.hospital_id
    if user.role == ROLE_SUPER_ADMIN:
        return bool(current_app.config.get("ADMIN_CAN_VIEW_PATIENT_DATA"))
    return False
