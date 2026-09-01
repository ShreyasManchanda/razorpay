"""Scenario-owned, deterministic replay data for the Warden hero."""

import json
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from warden.graph.negotiation_graph import build_cart_from_turns
from warden.graph.warden_graph import build_warden_graph
from warden.keys import ensure_keys_loaded, get_private_key
from warden.mandates.schema import CanonicalMandate, IntentMandate
from warden.mandates.signing import sign_mandate
from warden.policy.policy_config import PolicyConfig
from warden.scenarios.loader import load_scenario
from warden.storage.transcript_store import TranscriptStore
from warden.storage.verdict_store import VerdictStore

DEFAULT_SCENARIO_ID = "sabziwala_vs_mom"
HERO_REPLAY_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "fixtures" / "sabziwala_vs_mom_hero_replays.json"
)


def load_hero_replay_cases() -> list[dict]:
    with HERO_REPLAY_FIXTURE_PATH.open(encoding="utf-8") as fixture:
        data = json.load(fixture)
    if data.get("scenario_id") != DEFAULT_SCENARIO_ID:
        raise RuntimeError("Hero replay fixture is not owned by the default scenario")
    return data["cases"]


def _canonical_for_case(case: dict) -> CanonicalMandate:
    scenario = load_scenario(DEFAULT_SCENARIO_ID)
    catalog = [item.model_dump() for item in scenario.catalog]
    extracted = build_cart_from_turns(case["transcript"], catalog)
    expected = case["cart"]
    expected_names = [item["name"] for item in expected["items"]]
    actual_names = [item["name"] for item in extracted.items]
    if extracted.agreement_status != "agreed" or actual_names != expected_names or extracted.total != expected["total"]:
        raise RuntimeError(f"Hero replay {case['id']} does not reconstruct its declared buyer-agreed cart")
    intent = IntentMandate(agent_id="buyer_agent_v1", **case["intent"])
    signed = sign_mandate(extracted, get_private_key("merchant_agent_v1"))
    return CanonicalMandate(intent=intent, cart=signed)


async def _seed_case(case: dict, checkpointer: MemorySaver, tx_id: str) -> dict:
    canonical = _canonical_for_case(case)
    transcript_store = TranscriptStore()
    transcript_store.reset(tx_id)
    for turn in case["transcript"]:
        transcript_store.append_turn(tx_id, turn)

    state = {
        "tx_id": tx_id,
        "canonical_mandate": canonical,
        "transcript": case["transcript"],
        "policy_config": PolicyConfig(),
        "execution_mode": "demo",
    }
    if "precomputed_drift" in case:
        state["precomputed_drift"] = case["precomputed_drift"]
    graph = build_warden_graph(checkpointer=checkpointer)
    return await graph.ainvoke(state, config={"configurable": {"thread_id": tx_id}})


async def seed_hero_replay_cases(checkpointer: MemorySaver) -> None:
    """Persist each immutable fixture through the Warden graph at startup."""
    ensure_keys_loaded()
    verdict_store = VerdictStore()

    for case in load_hero_replay_cases():
        result = await _seed_case(case, checkpointer, case["id"])
        persisted = verdict_store.load(case["id"])
        if persisted is None or persisted.get("verdict") != case["expected_verdict"]:
            raise RuntimeError(f"Hero replay {case['id']} did not produce {case['expected_verdict']}")
        if case["expected_verdict"] == "STEPUP" and not result.get("__interrupt__"):
            raise RuntimeError(f"Hero replay {case['id']} did not persist its review interrupt")


async def seed_review_clone(checkpointer: MemorySaver, source_case_id: str) -> str:
    """Create a disposable STEPUP transaction without mutating replay evidence."""
    ensure_keys_loaded()
    case = next((item for item in load_hero_replay_cases() if item["id"] == source_case_id), None)
    if case is None:
        raise KeyError(source_case_id)
    if case["expected_verdict"] != "STEPUP":
        raise ValueError("Only a STEPUP replay can be cloned for human review")
    tx_id = f"review_{uuid.uuid4().hex[:16]}"
    result = await _seed_case(case, checkpointer, tx_id)
    persisted = VerdictStore().load(tx_id)
    if not result.get("__interrupt__") or persisted is None or persisted.get("verdict") != "STEPUP":
        raise RuntimeError("Review clone did not reach a persisted STEPUP interrupt")
    return tx_id
