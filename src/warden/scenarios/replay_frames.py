"""Server-derived evidence frames for deterministic hero replays."""

from copy import deepcopy
from typing import Any

from warden.detection.injection_scanner import scan_for_injection, scan_suspicious
from warden.graph.negotiation_graph import build_cart_from_turns
from warden.keys import ensure_keys_loaded, get_private_key
from warden.mandates.schema import CanonicalMandate, IntentMandate
from warden.mandates.signing import sign_mandate
from warden.policy.policy_config import QUICK_COMMERCE_POLICY
from warden.scenarios.loader import load_scenario
from warden.scenarios.replay_cases import DEFAULT_SCENARIO_ID, load_hero_replay_cases
from warden.services.authorization import evaluate_authorization

TRUST_THRESHOLD = 0.45


def _offered_cart(prefix: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    catalog_by_name = {item["name"].lower(): item for item in catalog}
    for turn in reversed(prefix):
        selected = turn.get("selected_items") or []
        offered = [catalog_by_name[str(name).lower()] for name in selected if str(name).lower() in catalog_by_name]
        if offered:
            return {
                "items": offered,
                "total": sum(item["price"] for item in offered),
                "category": offered[0].get("category", "unknown"),
            }
    return {"items": [], "total": 0, "category": "unknown"}


def _drift_for_frame(case: dict[str, Any], buyer_turns: int, final: bool) -> dict[str, Any]:
    source = deepcopy(case.get("precomputed_drift", {}))
    source["trajectory"] = source.get("trajectory", [])[:buyer_turns]
    source["consecutive_coherence"] = source.get("consecutive_coherence", [])[: max(0, buyer_turns - 1)]
    if not final:
        source["sudden_drop"] = False
        source["gradual_drift"] = False
        source["coherence_break"] = False
        source["explicit_conflict"] = False
    return source


def _provisional_detectors(
    prefix: list[dict[str, Any]], drift: dict[str, Any], cart: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    merchant_messages = [turn.get("message", "") for turn in prefix if turn.get("speaker") == "merchant_agent"]
    hard_flags = [flag for message in merchant_messages for flag in scan_for_injection(message)]
    soft_flags = [flag for message in merchant_messages for flag in scan_suspicious(message)]
    trajectory = drift.get("trajectory", [])
    score = trajectory[-1] if trajectory else 1.0
    drift_status = "flag" if score < TRUST_THRESHOLD else "watch" if score < 0.65 else "pass"
    injection_status = "flag" if hard_flags else "watch" if soft_flags else "pass"
    signals = {
        "signature_valid": None,
        "violations": [],
        "drift": drift,
        "injection_flags": hard_flags,
        "suspicious_flags": soft_flags,
        "cart_total": cart["total"],
        "detector_errors": [],
    }
    detectors = {
        "signature": {"status": "pending", "valid": None},
        "constraints": {"status": "pending", "violations": []},
        "drift": {"status": drift_status, "trajectory": trajectory, "score": score},
        "injection": {"status": injection_status, "flags": hard_flags, "suspicious_flags": soft_flags},
    }
    return signals, detectors


def build_replay(case_id: str) -> dict[str, Any]:
    """Return immutable, exchange-by-exchange evidence for one hero case."""
    case = next((item for item in load_hero_replay_cases() if item["id"] == case_id), None)
    if case is None:
        raise KeyError(case_id)

    ensure_keys_loaded()
    scenario = load_scenario(DEFAULT_SCENARIO_ID)
    catalog = [item.model_dump() for item in scenario.catalog]
    transcript = case["transcript"]
    intent = IntentMandate(agent_id="buyer_agent_v1", **case["intent"])
    frames = []

    for end in range(2, len(transcript) + 1, 2):
        prefix = deepcopy(transcript[:end])
        final = end == len(transcript)
        buyer_turns = sum(turn.get("speaker") == "buyer_agent" for turn in prefix)
        drift = _drift_for_frame(case, buyer_turns, final)
        extracted = build_cart_from_turns(prefix, catalog)
        offered = _offered_cart(prefix, catalog)
        display_cart = (
            extracted.model_dump()
            if extracted.items
            else {
                "agent_id": "merchant_agent_v1",
                **offered,
                "signature": None,
                "agreement_status": "pending",
                "agreement_evidence": [],
                "extraction_warnings": ["awaiting_explicit_buyer_agreement"],
            }
        )

        if final:
            signed = sign_mandate(extracted, get_private_key("merchant_agent_v1"))
            result = evaluate_authorization(
                CanonicalMandate(intent=intent, cart=signed),
                prefix,
                QUICK_COMMERCE_POLICY,
                drift_fn=lambda _intent, _reasonings, value=drift: value,
            )
            verdict = result["verdict"]
            explanation = case.get("case_explanation", result["explanation"])
            signals = result["signals"]
            detectors = result["detectors"]
            display_cart = result["cart"]
            payment_state = (
                "demo_order_created" if verdict == "PASS" else "awaiting_review" if verdict == "STEPUP" else "blocked"
            )
        else:
            signals, detectors = _provisional_detectors(prefix, drift, display_cart)
            verdict = "ANALYSIS"
            explanation = "Warden is observing the negotiation. Authorization waits for explicit buyer agreement."
            payment_state = "not_requested"

        frames.append(
            {
                "exchange_index": end // 2,
                "turn_count": end,
                "transcript": prefix,
                "cart": display_cart,
                "signals": signals,
                "detectors": detectors,
                "trust_score_trajectory": drift.get("trajectory", []),
                "decision_state": "final" if final else "provisional",
                "verdict": verdict,
                "explanation": explanation,
                "payment_state": payment_state,
            }
        )

    if not frames or frames[-1]["verdict"] != case["expected_verdict"]:
        raise RuntimeError(f"Replay {case_id} does not end in {case['expected_verdict']}")
    return {
        "case_id": case_id,
        "scenario_id": DEFAULT_SCENARIO_ID,
        "label": case["label"],
        "expected_verdict": case["expected_verdict"],
        "intent": case["intent"],
        "trust_threshold": TRUST_THRESHOLD,
        "frames": frames,
    }
