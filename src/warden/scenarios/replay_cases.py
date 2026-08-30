"""Scenario-owned, deterministic replay data for the Warden hero."""

import json
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from warden.graph.warden_graph import build_warden_graph
from warden.keys import ensure_keys_loaded, get_private_key
from warden.mandates.schema import CanonicalMandate, CartMandate, IntentMandate
from warden.mandates.signing import sign_mandate
from warden.policy.policy_config import PolicyConfig
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


async def seed_hero_replay_cases(checkpointer: MemorySaver) -> None:
    """Persist each fixture through the Warden graph at application startup."""
    ensure_keys_loaded()
    transcript_store = TranscriptStore()
    verdict_store = VerdictStore()
    graph = build_warden_graph(checkpointer=checkpointer)

    for case in load_hero_replay_cases():
        intent_data = case["intent"]
        cart_data = case["cart"]
        intent = IntentMandate(agent_id="buyer_agent_v1", **intent_data)
        cart = CartMandate(agent_id="merchant_agent_v1", **cart_data)
        canonical = CanonicalMandate(intent=intent, cart=sign_mandate(cart, get_private_key("merchant_agent_v1")))

        transcript_store.reset(case["id"])
        for turn in case["transcript"]:
            transcript_store.append_turn(case["id"], turn)

        state = {
            "tx_id": case["id"],
            "canonical_mandate": canonical,
            "transcript": case["transcript"],
            "policy_config": PolicyConfig(),
            "execution_mode": "demo",
        }
        if "precomputed_drift" in case:
            state["precomputed_drift"] = case["precomputed_drift"]
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": case["id"]}})
        persisted = verdict_store.load(case["id"])
        if persisted is None or persisted.get("verdict") != case["expected_verdict"]:
            raise RuntimeError(f"Hero replay {case['id']} did not produce {case['expected_verdict']}")
        if case["expected_verdict"] == "STEPUP" and not result.get("__interrupt__"):
            raise RuntimeError(f"Hero replay {case['id']} did not persist its review interrupt")
