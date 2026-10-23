"""Hospital matching.

Pure functions over plain dicts (see ``Hospital.to_matching_dict``) so the
logic is fully unit-testable without a database.

Ranking = estimated drive time (minutes) + penalties for missing capability.
A hospital with zero ER beds is only suggested when *every* hospital is full,
and then with an explicit warning - the system never returns "no options".
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

EARTH_RADIUS_KM = 6371.0088
ROAD_FACTOR = 1.4          # straight-line -> typical road distance
AVERAGE_SPEED_KMH = 45.0   # blended urban / highway ambulance speed
STALE_CAPACITY_HOURS = 12

# What each situation would ideally like at the receiving hospital.
SITUATION_NEEDS: dict[str, dict[str, list[str]]] = {
    "accident":    {"specialists": ["trauma_surgeon", "general_surgeon"], "facilities": ["ct_scanner", "blood_bank"]},
    "bleeding":    {"specialists": ["trauma_surgeon", "general_surgeon"], "facilities": ["blood_bank"]},
    "breathing":   {"specialists": ["anaesthetist"], "facilities": []},
    "unconscious": {"specialists": ["neurosurgeon"], "facilities": ["ct_scanner"]},
    "chest_pain":  {"specialists": ["cardiologist"], "facilities": ["cath_lab"]},
    "seizure":     {"specialists": ["neurosurgeon"], "facilities": ["ct_scanner"]},
    "burns":       {"specialists": ["burns_specialist"], "facilities": ["burns_unit"]},
    "childbirth":  {"specialists": ["obstetrician"], "facilities": ["maternity"]},
    "poisoning":   {"specialists": [], "facilities": []},
    "snakebite":   {"specialists": [], "facilities": []},
    "drowning":    {"specialists": ["anaesthetist"], "facilities": []},
    "other":       {"specialists": [], "facilities": []},
}

SPECIALIST_PENALTY = {"CRITICAL": 40, "HIGH": 30, "MODERATE": 15, "LOW": 5}
FACILITY_PENALTY = {"CRITICAL": 15, "HIGH": 10, "MODERATE": 5, "LOW": 2}
NO_ICU_PENALTY = {"CRITICAL": 35, "HIGH": 15, "MODERATE": 0, "LOW": 0}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def estimate_eta_minutes(distance_km: float) -> int:
    return max(1, int(round(distance_km * ROAD_FACTOR / AVERAGE_SPEED_KMH * 60)))


def _valid_coords(lat: Any, lon: Any) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def _is_stale(updated_iso: str | None, now: datetime) -> bool:
    if not updated_iso:
        return True
    try:
        updated = datetime.fromisoformat(updated_iso.rstrip("Z"))
    except ValueError:
        return True
    return (now - updated).total_seconds() > STALE_CAPACITY_HOURS * 3600


def match_hospitals(
    hospitals: Iterable[dict[str, Any]],
    lat: float | None,
    lon: float | None,
    severity: str = "MODERATE",
    situation: str = "other",
    patient_age: int | None = None,
    limit: int = 3,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rank hospitals for a patient. Returns ``{"matches": [...], "warnings": [...]}``."""
    severity = (severity or "MODERATE").upper()
    if severity not in SPECIALIST_PENALTY:
        severity = "MODERATE"
    needs = SITUATION_NEEDS.get(situation or "other", SITUATION_NEEDS["other"])
    want_specialists = list(needs["specialists"])
    if patient_age is not None and patient_age < 16:
        want_specialists.append("paediatrician")
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    has_location = _valid_coords(lat, lon)

    warnings: list[str] = []
    if not has_location:
        warnings.append("Patient location unknown - ranking by capability only; confirm location by phone.")

    candidates: list[dict[str, Any]] = []
    for h in hospitals:
        if not h.get("is_active", True) or not _valid_coords(h.get("latitude"), h.get("longitude")):
            continue
        reasons: list[str] = []
        missing: list[str] = []
        notes: list[str] = []
        penalty = 0.0

        if has_location:
            distance = haversine_km(float(lat), float(lon), float(h["latitude"]), float(h["longitude"]))
            eta = estimate_eta_minutes(distance)
        else:
            distance, eta = None, 0

        specialists = h.get("specialists") or {}
        facilities = h.get("facilities") or {}

        if want_specialists:
            on_duty = [s for s in want_specialists if specialists.get(s)]
            if on_duty:
                reasons.extend(on_duty)
            else:
                missing.extend(want_specialists)
                penalty += SPECIALIST_PENALTY[severity]
        for fac in needs["facilities"]:
            if facilities.get(fac):
                reasons.append(fac)
            else:
                missing.append(fac)
                penalty += FACILITY_PENALTY[severity]

        icu = int(h.get("icu_beds_available") or 0)
        if icu <= 0:
            penalty += NO_ICU_PENALTY[severity]
            if severity in ("CRITICAL", "HIGH"):
                missing.append("icu_bed")
        else:
            reasons.append("icu_bed")

        er_beds = int(h.get("er_beds_available") or 0)
        if er_beds == 1:
            penalty += 5
            notes.append("Only 1 ER bed left")
        if _is_stale(h.get("capacity_updated_at"), now):
            penalty += 5
            notes.append("Capacity not updated in 12h - call ahead")

        candidates.append({
            "hospital_id": h["id"],
            "name": h["name"],
            "code": h.get("code"),
            "level": h.get("level"),
            "phone": h.get("phone"),
            "distance_km": round(distance, 1) if distance is not None else None,
            "eta_minutes": eta if has_location else None,
            "er_beds_available": er_beds,
            "icu_beds_available": icu,
            "score": round(eta + penalty, 1),
            "matched": reasons,
            "missing": missing,
            "notes": notes,
            "full": er_beds <= 0,
        })

    if not candidates:
        warnings.append("No active hospitals are registered - call 112 control room.")
        return {"matches": [], "warnings": warnings}

    open_ones = [c for c in candidates if not c["full"]]
    if open_ones:
        pool = open_ones
    else:
        warnings.append("Every hospital reports 0 ER beds - nearest shown; call ahead before transport.")
        pool = candidates

    key = (lambda c: (c["score"], c["distance_km"] or 0)) if has_location else (lambda c: c["score"])
    pool.sort(key=key)
    return {"matches": pool[:max(1, limit)], "warnings": warnings}
