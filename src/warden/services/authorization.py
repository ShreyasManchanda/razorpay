"""Side-effect-free Warden authorization evaluation.

This module deliberately stops at an authorization decision. Payment execution
and human-review resolution remain explicit caller-owned actions.
"""

from collections.abc import Callable
from typing import Any

from warden.detection.constraint_checker import check_constraints
from warden.detection.drift_scorer import drift_score
from warden.detection.injection_scanner import scan_for_injection, scan_suspicious
from warden.mandates.schema import CanonicalMandate
from warden.mandates.signing import verify_mandate
from warden.policy.policy_config import PolicyConfig
from warden.policy.verdict import warden_verdict

DriftFn = Callable[[str, list[str]], dict[str, Any]]
VerdictFn = Callable[[dict[str, Any], PolicyConfig], tuple[str, str]]


def _empty_drift() -> dict[str, Any]:
    return {
        "sudden_drop": False,
        "gradual_drift": False,
        "coherence_break": False,
        "explicit_conflict": False,
        "trajectory": [],
        "consecutive_coherence": [],
    }


def _detector_statuses(
    *,
    signature_valid: bool,
    violations: list[str],
    drift: dict[str, Any],
    injection_flags: list[str],
    detector_errors: list[str],
    suspicious_flags: list[str] | None = None,
) -> dict[str, Any]:
    suspicious_flags = suspicious_flags or []
    trajectory = drift.get("trajectory", [])
    drift_flagged = any(
        drift.get(key) for key in ("sudden_drop", "gradual_drift", "coherence_break", "explicit_conflict")
    )
    return {
        "signature": {"status": "pass" if signature_valid else "fail", "valid": signature_valid},
        "constraints": {"status": "fail" if violations else "pass", "violations": violations},
        "drift": {
            "status": "unavailable" if detector_errors else "flag" if drift_flagged else "pass",
            "trajectory": trajectory,
            "score": trajectory[-1] if trajectory else 1.0,
            "explicit_conflict": bool(drift.get("explicit_conflict")),
        },
        "injection": {
            "status": "flag" if injection_flags else "watch" if suspicious_flags else "pass",
            "flags": injection_flags,
            "suspicious_flags": suspicious_flags,
        },
    }


def evaluate_authorization(
    canonical: CanonicalMandate,
    transcript: list[dict[str, Any]],
    policy_config: PolicyConfig,
    *,
    drift_fn: DriftFn | None = None,
    verdict_fn: VerdictFn | None = None,
) -> dict[str, Any]:
    """Verify a signed cart, compute detector signals, and apply a policy.

    An invalid or unknown signature fails before any semantic detector runs.
    Detector failures never become PASS: they degrade to STEPUP for review.
    """

    try:
        signature_valid = verify_mandate(canonical.cart)
    except Exception:
        signature_valid = False

    if not signature_valid:
        drift = _empty_drift()
        signals = {
            "signature_valid": False,
            "violations": [],
            "drift": drift,
            "injection_flags": [],
            "suspicious_flags": [],
            "cart_total": canonical.cart.total,
            "detector_errors": [],
        }
        return {
            "verdict": "REJECT",
            "explanation": "Cart mandate signature verification failed. Transaction blocked before detection.",
            "signals": signals,
            "trust_score_trajectory": [],
            "cart": canonical.cart.model_dump(),
            "detectors": _detector_statuses(
                signature_valid=False,
                violations=[],
                drift=drift,
                injection_flags=[],
                suspicious_flags=[],
                detector_errors=[],
            ),
            "degraded": False,
        }

    detector_errors: list[str] = []
    try:
        violations = check_constraints(canonical.intent, canonical.cart)
    except Exception as exc:
        violations = []
        detector_errors.append(f"constraint_checker:{type(exc).__name__}: {str(exc)[:180]}")

    buyer_reasonings = [
        str(turn.get("reasoning", ""))
        for turn in transcript
        if turn.get("speaker") == "buyer_agent" and turn.get("reasoning")
    ]
    try:
        drift = (drift_fn or drift_score)(canonical.intent.raw_goal_text, buyer_reasonings)
    except Exception as exc:
        drift = _empty_drift()
        detector_errors.append(f"drift_scorer:{type(exc).__name__}: {str(exc)[:180]}")

    try:
        merchant_messages = [
            str(turn.get("message", "")) for turn in transcript if turn.get("speaker") == "merchant_agent"
        ]
        injection_flags = [flag for message in merchant_messages for flag in scan_for_injection(message)]
        suspicious_flags = [flag for message in merchant_messages for flag in scan_suspicious(message)]
    except Exception as exc:
        injection_flags = []
        suspicious_flags = []
        detector_errors.append(f"injection_scanner:{type(exc).__name__}: {str(exc)[:180]}")

    trajectory = drift.get("trajectory", [])
    signals = {
        "signature_valid": True,
        "violations": violations,
        "drift": drift,
        "injection_flags": injection_flags,
        "suspicious_flags": suspicious_flags,
        "cart_total": canonical.cart.total,
        "detector_errors": detector_errors,
    }
    verdict, explanation = (verdict_fn or warden_verdict)(signals, policy_config)
    if detector_errors and verdict == "PASS":
        verdict = "STEPUP"
        explanation = (
            "A detector was unavailable, so Warden paused this transaction for human review "
            "instead of approving on incomplete evidence."
        )

    return {
        "verdict": verdict,
        "explanation": explanation,
        "signals": signals,
        "trust_score_trajectory": trajectory,
        "cart": canonical.cart.model_dump(),
        "detectors": _detector_statuses(
            signature_valid=True,
            violations=violations,
            drift=drift,
            injection_flags=injection_flags,
            suspicious_flags=suspicious_flags,
            detector_errors=detector_errors,
        ),
        "degraded": bool(detector_errors),
    }
