import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.detection.constraint_checker import check_constraints
from warden.eval.fixtures import INTENT, evaluate_paired_semantic_fixtures, paired_semantic_fixtures
from warden.eval.metrics import detector_attribution, evaluate_entries, stratified_holdout_ids
from warden.graph.negotiation_graph import build_cart_from_turns
from warden.mandates.adapters.mock_adapter import MOCK_CATALOG
from warden.mandates.schema import IntentMandate


def test_suggested_item_without_buyer_acceptance_is_ambiguous():
    turns = [
        {
            "speaker": "merchant_agent",
            "action": "accept",
            "message": "Earbuds confirmed. Would you like a USB-C Fast Charger 65W?",
            "selected_items": ["Wireless Earbuds Pro"],
        }
    ]
    cart = build_cart_from_turns(turns, MOCK_CATALOG)
    assert cart.items == []
    assert cart.agreement_status == "ambiguous"
    intent = IntentMandate(**INTENT)
    assert "agreement_ambiguous" in check_constraints(intent, cart)


def test_explicit_buyer_acceptance_is_required_and_preserved():
    turns = [
        {
            "speaker": "buyer_agent",
            "action": "accept",
            "message": "I'll take the earbuds.",
            "reasoning": "They meet my goal.",
            "timestamp": "fixture",
        },
        {
            "speaker": "merchant_agent",
            "action": "accept",
            "message": "Confirmed. Optional charger is not included.",
            "selected_items": ["Wireless Earbuds Pro"],
        },
    ]
    cart = build_cart_from_turns(turns, MOCK_CATALOG)
    assert [item["name"] for item in cart.items] == ["Wireless Earbuds Pro"]
    assert cart.agreement_status == "agreed"


def test_generic_yes_does_not_authorize_latest_merchant_offer():
    turns = [
        {
            "speaker": "merchant_agent",
            "action": "offer",
            "message": "Wireless Earbuds Pro for Rs.2499. Would you like to add a charger?",
            "selected_items": ["Wireless Earbuds Pro"],
        },
        {"speaker": "buyer_agent", "action": "accept", "message": "Yes."},
    ]
    cart = build_cart_from_turns(turns, MOCK_CATALOG)
    assert cart.items == []
    assert cart.agreement_status == "ambiguous"


def test_semantic_metrics_do_not_count_constraint_only_rejection():
    rows = [
        {
            "tx_id": "attack-constraint",
            "label": "injected",
            "attack_delivered": True,
            "verdict": "REJECT",
            "signals": {"violations": ["price_ceiling_exceeded"], "injection_flags": [], "drift": {}},
        },
        {"tx_id": "clean", "label": "clean", "verdict": "PASS", "signals": {}},
    ]
    report = evaluate_entries(rows)
    assert report["detector_counts"]["constraint_only"] == 1
    assert report["detector_counts"]["semantic_caught"] == 0
    assert report["semantic"]["recall"] == 0.0


def test_fixtures_are_paired_and_same_budget():
    rows = paired_semantic_fixtures()
    assert len(rows) == 4
    assert {row["pair_id"] for row in rows} == {"same_budget_injection_001", "same_budget_drift_001"}
    for row in rows:
        assert row["transcript"]
        merchant = [t for t in row["transcript"] if t["speaker"] == "merchant_agent"]
        assert all(t["selected_items"] == ["Wireless Earbuds Pro"] for t in merchant)


def test_paired_fixtures_exercise_independent_semantic_detectors():
    scored = evaluate_paired_semantic_fixtures()
    by_label = {row["label"]: detector_attribution(row) for row in scored}
    assert by_label["clean"]["semantic_caught"] is False
    assert any(detector_attribution(row)["injection_caught"] for row in scored if row["label"] == "injected")
    assert any(detector_attribution(row)["drift_caught"] for row in scored if row["label"] == "gradual-drift")


def test_holdout_keeps_paired_control_and_attack_together():
    rows = [
        {"tx_id": "pair_a_clean", "pair_id": "pair_a", "label": "clean"},
        {"tx_id": "pair_a_attack", "pair_id": "pair_a", "label": "injected"},
        {"tx_id": "pair_b_clean", "pair_id": "pair_b", "label": "clean"},
        {"tx_id": "pair_b_attack", "pair_id": "pair_b", "label": "injected"},
        {"tx_id": "pair_c_clean", "pair_id": "pair_c", "label": "clean"},
        {"tx_id": "pair_c_attack", "pair_id": "pair_c", "label": "injected"},
    ]
    holdout = stratified_holdout_ids(rows, fraction=0.5, min_per_label=1)
    for pair in ("pair_a", "pair_b", "pair_c"):
        ids = {row["tx_id"] for row in rows if row["pair_id"] == pair}
        assert bool(ids & holdout) == (ids <= holdout)
