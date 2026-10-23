"""Clinical triage: MEWS baseline + raise-only AI harness.

Safety contract (enforced here, tested in ``tests/test_triage.py``):

1. The MEWS score (Subbe et al., 2001) is computed deterministically from the
   vitals. Raise-only red-flag rules (SpO2, GCS, glucose, any single MEWS
   parameter scoring 3) may lift it further. This is the **baseline**.
2. The local LLM may suggest a severity. ``final = max(baseline, ai)``. The AI
   can raise severity; it can never lower it.
3. Rule-based actions are ALWAYS returned. AI actions are appended separately
   and labelled advisory. The AI can add, never remove.
4. Any AI failure (offline, timeout, bad JSON, exception of any kind) falls
   back to the MEWS rule-based result. ``run_triage`` never raises because of
   the AI.

This is decision support for trained personnel, not a diagnosis.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity scale
# ---------------------------------------------------------------------------
LOW = "LOW"
MODERATE = "MODERATE"
HIGH = "HIGH"
CRITICAL = "CRITICAL"

SEVERITY_ORDER = [LOW, MODERATE, HIGH, CRITICAL]
SEVERITY_RANK = {name: i + 1 for i, name in enumerate(SEVERITY_ORDER)}

DISCLAIMER = (
    "Decision support only. MEWS is the clinical baseline; AI suggestions are "
    "advisory and can only raise severity. Final decisions rest with the "
    "attending clinician."
)


def severity_rank(severity: str | None) -> int:
    return SEVERITY_RANK.get((severity or "").upper(), 0)


def max_severity(*severities: str | None) -> str:
    valid = [s.upper() for s in severities if s and s.upper() in SEVERITY_RANK]
    if not valid:
        return LOW
    return max(valid, key=lambda s: SEVERITY_RANK[s])


# ---------------------------------------------------------------------------
# Vitals validation
# ---------------------------------------------------------------------------
# (min, max) physiologically plausible bounds. Values outside are rejected as
# probable data-entry errors rather than silently scored.
PLAUSIBLE_RANGES = {
    "respiratory_rate": (0, 80),
    "heart_rate": (0, 300),
    "systolic_bp": (30, 300),
    "diastolic_bp": (10, 200),
    "temperature": (25.0, 45.0),
    "spo2": (30, 100),
    "gcs": (3, 15),
    "glucose": (0.5, 50.0),   # mmol/L
    "age": (0, 120),
}

AVPU_VALUES = {"A": "Alert", "V": "Responds to Voice", "P": "Responds to Pain", "U": "Unresponsive"}

MEWS_PARAMETERS = ("respiratory_rate", "heart_rate", "systolic_bp", "temperature", "avpu")


class VitalsError(ValueError):
    """Raised when submitted vitals are not plausible."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("must be a number") from None
    if math.isnan(number) or math.isinf(number):
        raise ValueError("must be a finite number")
    return number


def normalize_vitals(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce raw form/JSON vitals. Missing values become None."""
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {}
    for key, (low, high) in PLAUSIBLE_RANGES.items():
        try:
            number = _to_number(raw.get(key))
        except ValueError as exc:
            errors[key] = str(exc)
            continue
        if number is not None and not (low <= number <= high):
            errors[key] = f"{number:g} is outside the plausible range {low}-{high}"
            continue
        if number is not None and key in {"respiratory_rate", "heart_rate", "systolic_bp",
                                          "diastolic_bp", "spo2", "gcs", "age"}:
            number = int(round(number))
        clean[key] = number

    avpu = (raw.get("avpu") or "").strip().upper()[:1] or None
    if avpu is not None and avpu not in AVPU_VALUES:
        errors["avpu"] = "must be one of A, V, P, U"
    else:
        clean["avpu"] = avpu

    sex = (raw.get("sex") or "").strip().upper()[:1] or None
    clean["sex"] = sex if sex in {"M", "F"} else None

    if errors:
        raise VitalsError(errors)
    return clean


# ---------------------------------------------------------------------------
# MEWS
# ---------------------------------------------------------------------------
def _score_rr(rr: float) -> int:
    if rr < 9:
        return 2
    if rr <= 14:
        return 0
    if rr <= 20:
        return 1
    if rr < 30:
        return 2
    return 3


def _score_hr(hr: float) -> int:
    if hr <= 40:
        return 2
    if hr <= 50:
        return 1
    if hr <= 100:
        return 0
    if hr <= 110:
        return 1
    if hr < 130:
        return 2
    return 3


def _score_sbp(sbp: float) -> int:
    if sbp <= 70:
        return 3
    if sbp <= 80:
        return 2
    if sbp <= 100:
        return 1
    if sbp < 200:
        return 0
    return 2


def _score_temp(temp: float) -> int:
    if temp < 35.0:
        return 2
    if temp < 38.5:
        return 0
    return 2


_AVPU_SCORE = {"A": 0, "V": 1, "P": 2, "U": 3}


def mews_severity_for_score(score: int) -> str:
    if score >= 5:
        return CRITICAL
    if score == 4:
        return HIGH
    if score >= 2:
        return MODERATE
    return LOW


@dataclass
class MewsResult:
    score: int
    components: dict[str, int]
    missing: list[str]
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "components": self.components,
                "missing": self.missing, "severity": self.severity}


def calculate_mews(vitals: dict[str, Any]) -> MewsResult:
    """Compute the Modified Early Warning Score from normalised vitals."""
    scorers = {
        "respiratory_rate": _score_rr,
        "heart_rate": _score_hr,
        "systolic_bp": _score_sbp,
        "temperature": _score_temp,
    }
    components: dict[str, int] = {}
    missing: list[str] = []
    for key, scorer in scorers.items():
        value = vitals.get(key)
        if value is None:
            missing.append(key)
        else:
            components[key] = scorer(float(value))
    avpu = vitals.get("avpu")
    if avpu in _AVPU_SCORE:
        components["avpu"] = _AVPU_SCORE[avpu]
    else:
        missing.append("avpu")
    score = sum(components.values())
    return MewsResult(score, components, missing, mews_severity_for_score(score))


def red_flag_escalations(vitals: dict[str, Any], mews: MewsResult) -> list[tuple[str, str]]:
    """Raise-only escalation rules applied on top of MEWS.

    Returns ``(minimum_severity, reason)`` pairs.
    """
    flags: list[tuple[str, str]] = []
    if any(points >= 3 for points in mews.components.values()):
        flags.append((HIGH, "A single vital sign is in the most extreme MEWS band"))
    spo2 = vitals.get("spo2")
    if spo2 is not None:
        if spo2 < 85:
            flags.append((CRITICAL, f"SpO2 {spo2}% (< 85%)"))
        elif spo2 < 90:
            flags.append((HIGH, f"SpO2 {spo2}% (< 90%)"))
    gcs = vitals.get("gcs")
    if gcs is not None:
        if gcs <= 8:
            flags.append((CRITICAL, f"GCS {gcs} (<= 8, airway at risk)"))
        elif gcs <= 12:
            flags.append((HIGH, f"GCS {gcs} (9-12)"))
    glucose = vitals.get("glucose")
    if glucose is not None and glucose < 3.0:
        flags.append((HIGH, f"Blood glucose {glucose:g} mmol/L (< 3.0, hypoglycaemia)"))
    if vitals.get("heart_rate") == 0 or vitals.get("respiratory_rate") == 0:
        flags.append((CRITICAL, "No pulse or no breathing recorded - start CPR"))
    return flags


# ---------------------------------------------------------------------------
# Rule-based actions (always returned)
# ---------------------------------------------------------------------------
SEVERITY_ACTIONS = {
    CRITICAL: [
        "Time-critical: manage Airway, Breathing, Circulation now; call for senior support.",
        "Give high-flow oxygen if SpO2 < 94% or unmeasurable; prepare suction and bag-valve-mask.",
        "Pre-alert the receiving hospital and transport immediately - do not delay on scene.",
        "Reassess full vitals every 5 minutes and record trends.",
        "Be ready to start CPR if breathing or pulse is lost.",
    ],
    HIGH: [
        "Urgent: complete primary survey (ABCDE) and correct life threats first.",
        "Give oxygen to keep SpO2 >= 94% (88-92% if known chronic lung disease).",
        "Obtain IV/IO access if trained and equipped; do not delay transport for it.",
        "Pre-alert the receiving hospital; reassess vitals every 10 minutes.",
    ],
    MODERATE: [
        "Complete ABCDE assessment and focused history (SAMPLE).",
        "Monitor vitals every 15 minutes; escalate if MEWS rises.",
        "Transport to an appropriate facility; inform hospital on approach.",
    ],
    LOW: [
        "Complete ABCDE assessment and document findings.",
        "Reassess vitals every 30 minutes or sooner if condition changes.",
        "Arrange transport or referral as clinically appropriate.",
    ],
}

SITUATION_ACTIONS = {
    "accident": [
        "Assume spinal injury in high-energy trauma: manual in-line stabilisation; minimise movement.",
        "Control external haemorrhage with direct pressure; tourniquet for life-threatening limb bleeding.",
    ],
    "bleeding": [
        "Apply firm direct pressure; pack deep wounds; tourniquet if limb bleeding is uncontrolled.",
        "Keep patient warm and lying flat; watch for signs of shock.",
    ],
    "breathing": [
        "Sit patient upright if conscious; check for airway obstruction or wheeze.",
    ],
    "unconscious": [
        "Open and maintain airway; recovery position if breathing and no spinal concern.",
        "Check blood glucose if equipment available.",
    ],
    "chest_pain": [
        "Rest patient in position of comfort; 12-lead ECG if available; pre-alert for possible ACS.",
    ],
    "seizure": [
        "Protect from injury; do not restrain or put anything in the mouth; time the seizure.",
        "Check blood glucose; recovery position once jerking stops.",
    ],
    "burns": [
        "Cool the burn with clean running water for 20 minutes; remove jewellery; cover loosely with cling film.",
        "Look for airway burns (soot, hoarse voice) - these are time-critical.",
    ],
    "childbirth": [
        "Assess stage of labour; prepare clean delivery kit; watch for post-partum haemorrhage.",
    ],
    "poisoning": [
        "Identify substance, amount and time; bring container to hospital. Do not induce vomiting.",
    ],
    "snakebite": [
        "Immobilise the limb and keep patient still; remove rings; no cutting, sucking or tourniquet.",
    ],
    "drowning": [
        "Prioritise airway and breathing; start CPR with rescue breaths if not breathing normally.",
    ],
}


def rule_based_actions(severity: str, situation: str | None, vitals: dict[str, Any]) -> list[str]:
    actions = list(SEVERITY_ACTIONS.get(severity, SEVERITY_ACTIONS[LOW]))
    actions.extend(SITUATION_ACTIONS.get(situation or "", []))
    if vitals.get("heart_rate") == 0 or vitals.get("respiratory_rate") == 0:
        actions.insert(0, "Start CPR now (30:2) and apply AED as soon as available.")
    return actions


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
@dataclass
class TriageResult:
    vitals: dict[str, Any]
    mews: MewsResult
    red_flags: list[str]
    baseline_severity: str
    final_severity: str
    actions: list[str]
    ai_status: str
    ai_severity: str | None = None
    ai_actions: list[str] = field(default_factory=list)
    ai_rationale: str | None = None
    ai_model: str | None = None
    ai_latency_ms: int | None = None
    ai_error: str | None = None
    ai_raised: bool = False
    ai_attempted_downgrade: bool = False

    @property
    def final_rank(self) -> int:
        return severity_rank(self.final_severity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mews": self.mews.to_dict(),
            "red_flags": self.red_flags,
            "baseline_severity": self.baseline_severity,
            "final_severity": self.final_severity,
            "actions": self.actions,
            "ai": {
                "status": self.ai_status,
                "severity": self.ai_severity,
                "actions": self.ai_actions,
                "rationale": self.ai_rationale,
                "model": self.ai_model,
                "latency_ms": self.ai_latency_ms,
                "error": self.ai_error,
                "raised": self.ai_raised,
                "attempted_downgrade": self.ai_attempted_downgrade,
            },
            "disclaimer": DISCLAIMER,
        }


def run_triage(
    raw_vitals: dict[str, Any],
    symptoms: str | None = None,
    situation: str | None = None,
    harness: Any = None,
) -> TriageResult:
    """Full triage pipeline. Raises ``VitalsError`` only for invalid input;
    never raises because of the AI."""
    vitals = normalize_vitals(raw_vitals)
    mews = calculate_mews(vitals)

    baseline = mews.severity
    red_flags: list[str] = []
    for minimum, reason in red_flag_escalations(vitals, mews):
        red_flags.append(reason)
        baseline = max_severity(baseline, minimum)
    if mews.missing:
        red_flags.append("Incomplete vitals (" + ", ".join(mews.missing)
                         + ") - MEWS may underestimate severity; obtain missing values")

    result = TriageResult(
        vitals=vitals,
        mews=mews,
        red_flags=red_flags,
        baseline_severity=baseline,
        final_severity=baseline,
        actions=rule_based_actions(baseline, situation, vitals),
        ai_status="disabled",
    )

    if harness is None:
        return result

    try:
        assessment = harness.assess(
            vitals=vitals,
            symptoms=symptoms or "",
            situation=situation or "other",
            mews_score=mews.score,
            baseline_severity=baseline,
        )
    except Exception as exc:  # noqa: BLE001 - the AI must never crash triage
        status = getattr(exc, "status", "fallback")
        result.ai_status = status if isinstance(status, str) else "fallback"
        result.ai_error = str(exc)[:300]
        log.warning("AI triage unavailable, using MEWS fallback: %s", exc)
        return result

    result.ai_status = "ok"
    result.ai_model = getattr(assessment, "model", None)
    result.ai_latency_ms = getattr(assessment, "latency_ms", None)
    result.ai_rationale = getattr(assessment, "rationale", None)
    ai_severity = str(getattr(assessment, "severity", "") or "").upper()
    if ai_severity not in SEVERITY_RANK:
        # Defence in depth: the harness validates too.
        result.ai_status = "invalid"
        result.ai_error = "AI returned an unknown severity"
        return result

    result.ai_severity = ai_severity
    result.ai_actions = list(getattr(assessment, "actions", []) or [])
    if severity_rank(ai_severity) < severity_rank(baseline):
        # SAFETY OVERRIDE: the AI may never lower severity.
        result.ai_attempted_downgrade = True
        log.info("AI suggested %s below baseline %s - ignored (raise-only rule)", ai_severity, baseline)
    elif severity_rank(ai_severity) > severity_rank(baseline):
        result.ai_raised = True
        result.final_severity = ai_severity
        # Recompute rule-based actions for the higher severity; keep all.
        result.actions = rule_based_actions(ai_severity, situation, vitals)
    result.final_severity = max_severity(baseline, result.final_severity)
    return result