"""WebSocket (Socket.IO) layer.

Privacy rule: broadcasts carry **non-identifying summaries only**
(reference, situation, severity, status). Clients then fetch full details over
an authenticated HTTP endpoint, which writes the audit log. Names, phone
numbers, GPS and photos never travel over a broadcast.

Rooms
-----
``role:paramedic``      every signed-in paramedic (bystander feed, capacity)
``hospital:<id>``       staff of one hospital (their inbound queue)
``role:super_admin``    admins (system events)
"""

from __future__ import annotations

import logging
import threading
import time

from flask import request
from flask_login import current_user
from flask_socketio import join_room

from ..extensions import socketio
from ..models.user import ROLE_HOSPITAL_ADMIN, ROLE_PARAMEDIC, ROLE_SUPER_ADMIN
from .matching import haversine_km

log = logging.getLogger(__name__)

_connections: dict[str, dict] = {}
_lock = threading.Lock()


def active_connections() -> list[dict]:
    with _lock:
        return sorted((dict(v, sid=k[:8] + "...") for k, v in _connections.items()),
                      key=lambda c: c["connected_at"], reverse=True)


def connection_count() -> int:
    with _lock:
        return len(_connections)


def _safe_emit(event: str, payload: dict, room: str) -> None:
    try:
        socketio.emit(event, payload, to=room)
    except Exception:  # noqa: BLE001 - realtime is best-effort; HTTP is the source of truth
        log.exception("Socket emit failed: %s -> %s", event, room)


def register_handlers() -> None:
    @socketio.on("connect")
    def _on_connect(auth=None):  # noqa: ARG001
        if not current_user.is_authenticated:
            return False  # civilians and anonymous users cannot open sockets
        rooms = [f"role:{current_user.role}"]
        if current_user.role == ROLE_HOSPITAL_ADMIN and current_user.hospital_id:
            rooms.append(f"hospital:{current_user.hospital_id}")
        for room in rooms:
            join_room(room)
        with _lock:
            _connections[request.sid] = {
                "username": current_user.username,
                "role": current_user.role,
                "hospital_id": current_user.hospital_id,
                "connected_at": time.time(),
                "ip": request.remote_addr,
            }
        socketio.emit("hello", {"rooms": rooms, "server_time": time.time()}, to=request.sid)
        return True

    @socketio.on("disconnect")
    def _on_disconnect(*_args):
        with _lock:
            _connections.pop(request.sid, None)

    @socketio.on("ping_server")
    def _on_ping(_data=None):
        return {"pong": time.time()}


# --- Domain events ---------------------------------------------------------
def notify_new_report(emergency, hospitals=None, radius_km: float = 60.0) -> None:
    summary = emergency.public_summary()
    _safe_emit("report_new", summary, f"role:{ROLE_PARAMEDIC}")
    _safe_emit("report_new", summary, f"role:{ROLE_SUPER_ADMIN}")
    # Hospitals near the incident get a non-identifying heads-up with distance.
    if hospitals and emergency.lat is not None:
        for hosp in hospitals:
            try:
                dist = haversine_km(emergency.lat, emergency.lon, hosp.latitude, hosp.longitude)
            except (TypeError, ValueError):
                continue
            if dist <= radius_km:
                _safe_emit("nearby_report", dict(summary, distance_km=round(dist, 1)), f"hospital:{hosp.id}")


def notify_emergency_updated(emergency, previous_hospital_id=None) -> None:
    summary = emergency.public_summary()
    _safe_emit("emergency_updated", summary, f"role:{ROLE_PARAMEDIC}")
    if emergency.hospital_id:
        _safe_emit("emergency_updated", summary, f"hospital:{emergency.hospital_id}")
    if previous_hospital_id and previous_hospital_id != emergency.hospital_id:
        _safe_emit("emergency_removed", {"id": emergency.id}, f"hospital:{previous_hospital_id}")


def notify_capacity(hospital) -> None:
    payload = hospital.to_matching_dict()
    _safe_emit("capacity_updated", payload, f"role:{ROLE_PARAMEDIC}")
    _safe_emit("capacity_updated", payload, f"hospital:{hospital.id}")
    _safe_emit("capacity_updated", payload, f"role:{ROLE_SUPER_ADMIN}")
