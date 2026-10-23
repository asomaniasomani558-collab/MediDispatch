"""Hospital matching logic (pure functions, no database)."""

from __future__ import annotations

from datetime import datetime

from app.services.matching import estimate_eta_minutes, haversine_km, match_hospitals

NOW = datetime(2026, 10, 22, 12, 0, 0)
FRESH = "2026-10-22T11:30:00Z"

# Kumasi Adum area
PATIENT = (6.6885, -1.6244)


def hosp(id, name, lat, lon, er=5, icu=2, specialists=None, facilities=None, active=True, updated=FRESH):
    return {
        "id": id, "name": name, "code": name[:4].upper(), "level": "Regional", "phone": None,
        "latitude": lat, "longitude": lon, "is_active": active,
        "er_beds_available": er, "icu_beds_available": icu, "general_beds_available": 10,
        "specialists": specialists or {}, "facilities": facilities or {}, "capacity_updated_at": updated,
    }


def test_haversine_known_distance():
    # Accra (Korle Bu) to Kumasi (KATH) is roughly 200 km in a straight line.
    d = haversine_km(5.5365, -0.2275, 6.6977, -1.6298)
    assert 195 < d < 215


def test_eta_is_positive():
    assert estimate_eta_minutes(0) == 1
    assert estimate_eta_minutes(10) > 10


def test_nearest_wins_when_equal_capability():
    hospitals = [hosp(1, "Far", 6.80, -1.70), hosp(2, "Near", 6.69, -1.62)]
    result = match_hospitals(hospitals, *PATIENT, severity="LOW", situation="other", now=NOW)
    assert result["matches"][0]["name"] == "Near"


def test_capability_beats_small_distance_for_critical_trauma():
    trauma = {"trauma_surgeon": True}
    hospitals = [
        hosp(1, "Clinic", 6.689, -1.625),                              # ~0 km, no trauma, no facilities
        hosp(2, "Trauma Centre", 6.70, -1.63, specialists=trauma,
             facilities={"ct_scanner": True, "blood_bank": True}),     # ~1.4 km
    ]
    result = match_hospitals(hospitals, *PATIENT, severity="CRITICAL", situation="accident", now=NOW)
    assert result["matches"][0]["name"] == "Trauma Centre"
    assert "trauma_surgeon" in result["matches"][0]["matched"]


def test_full_hospitals_excluded_when_alternatives_exist():
    hospitals = [hosp(1, "Full", 6.689, -1.625, er=0), hosp(2, "Open", 6.75, -1.65)]
    result = match_hospitals(hospitals, *PATIENT, now=NOW)
    names = [m["name"] for m in result["matches"]]
    assert names == ["Open"]


def test_all_full_still_returns_nearest_with_warning():
    hospitals = [hosp(1, "Full A", 6.689, -1.625, er=0), hosp(2, "Full B", 6.9, -1.7, er=0)]
    result = match_hospitals(hospitals, *PATIENT, now=NOW)
    assert result["matches"][0]["name"] == "Full A"
    assert any("0 ER beds" in w for w in result["warnings"])


def test_inactive_hospitals_ignored():
    hospitals = [hosp(1, "Closed", 6.689, -1.625, active=False), hosp(2, "Open", 6.9, -1.7)]
    result = match_hospitals(hospitals, *PATIENT, now=NOW)
    assert [m["name"] for m in result["matches"]] == ["Open"]


def test_no_hospitals_gives_warning_not_crash():
    result = match_hospitals([], *PATIENT, now=NOW)
    assert result["matches"] == []
    assert result["warnings"]


def test_unknown_location_ranks_by_capability():
    hospitals = [hosp(1, "Basic", 6.689, -1.625),
                 hosp(2, "Maternity", 6.9, -1.7, specialists={"obstetrician": True}, facilities={"maternity": True})]
    result = match_hospitals(hospitals, None, None, severity="HIGH", situation="childbirth", now=NOW)
    assert result["matches"][0]["name"] == "Maternity"
    assert result["matches"][0]["distance_km"] is None
    assert any("location unknown" in w for w in result["warnings"])


def test_critical_prefers_icu():
    hospitals = [hosp(1, "No ICU", 6.689, -1.625, icu=0), hosp(2, "ICU", 6.70, -1.63, icu=3)]
    result = match_hospitals(hospitals, *PATIENT, severity="CRITICAL", situation="breathing", now=NOW)
    assert result["matches"][0]["name"] == "ICU"


def test_child_prefers_paediatrician():
    hospitals = [hosp(1, "Adult", 6.689, -1.625), hosp(2, "Kids", 6.70, -1.63, specialists={"paediatrician": True})]
    result = match_hospitals(hospitals, *PATIENT, severity="HIGH", situation="other", patient_age=6, now=NOW)
    assert result["matches"][0]["name"] == "Kids"


def test_stale_capacity_noted():
    hospitals = [hosp(1, "Stale", 6.689, -1.625, updated="2026-10-20T08:00:00Z")]
    result = match_hospitals(hospitals, *PATIENT, now=NOW)
    assert any("call ahead" in n for n in result["matches"][0]["notes"])


def test_bad_coordinates_skipped():
    hospitals = [hosp(1, "Broken", None, None), hosp(2, "Good", 6.7, -1.63)]
    result = match_hospitals(hospitals, *PATIENT, now=NOW)
    assert [m["name"] for m in result["matches"]] == ["Good"]


def test_limit_respected():
    hospitals = [hosp(i, f"H{i}", 6.6 + i / 100, -1.6) for i in range(10)]
    assert len(match_hospitals(hospitals, *PATIENT, limit=3, now=NOW)["matches"]) == 3
