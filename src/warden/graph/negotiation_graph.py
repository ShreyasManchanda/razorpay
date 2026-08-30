import datetime
from typing import Literal

from langgraph.graph import END, StateGraph

from warden.agents.buyer_agent import BuyerAgent
from warden.agents.merchant_agent import MerchantAgent
from warden.graph.state import NegotiationState, Turn
from warden.mandates.schema import CartMandate
from warden.storage.transcript_store import TranscriptStore


def _summary(turns: list[Turn]) -> str:
    if not turns:
        return "This is the first turn. No prior messages."
    lines = []
    for t in turns:
        lines.append(f"{t['speaker']}: [{t['action']}] {t['message']}")
    return "\n".join(lines)


async def buyer_turn(state: NegotiationState) -> dict:
    scenario = state.get("scenario")
    agent = BuyerAgent(scenario=scenario)
    intent = state["intent_mandate"]
    summary = _summary(state["turns"])
    result = await agent.act(intent, summary)
    turn = Turn(
        speaker="buyer_agent",
        action=result.action,
        reasoning=result.reasoning,
        message=result.message,
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
    )
    store = TranscriptStore()
    store.append_turn(state["tx_id"], dict(turn))
    return {
        "turns": [turn],
        "turn_count": state["turn_count"] + 1,
    }


async def merchant_turn(state: NegotiationState) -> dict:
    scenario = state.get("scenario")
    agent = MerchantAgent(scenario=scenario)
    summary = _summary(state["turns"])
    result = await agent.act(summary, state.get("attacker_payload"), state.get("attack_type"))
    turn = Turn(
        speaker="merchant_agent",
        action=result.action,
        reasoning=result.reasoning,
        message=result.message,
        timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        selected_items=list(result.selected_items),
    )
    store = TranscriptStore()
    store.append_turn(state["tx_id"], dict(turn))
    return {"turns": [turn]}


# DriftScorer needs >=5 buyer reasonings for its sustained-halves and
# coherence checks to have data; ending on the first accept starves every signal.
MIN_BUYER_TURNS = 5


def route_termination(state: NegotiationState) -> Literal["buyer_turn", "finalize_cart"]:
    if not state["turns"]:
        return "buyer_turn"
    last_action = state["turns"][-1]["action"]
    deal_done = last_action in ("accept", "reject")
    if deal_done and state["turn_count"] >= MIN_BUYER_TURNS:
        return "finalize_cart"
    if state["turn_count"] >= state["max_turns"]:
        return "finalize_cart"
    return "buyer_turn"


def build_cart_from_turns(turns: list[Turn], catalog: list[dict]) -> CartMandate:
    """Build a cart from merchant turns, preferring structured selected_items.

    Primary source: the merchant agent's explicit selected_items contract
    (exact catalog names the buyer actually agreed to buy). The substring
    heuristic is only a fallback for transcripts produced before that field
    existed — it over-matches suggested accessories (B-011).
    """
    catalog_by_name = {item["name"].lower(): item for item in catalog}
    items: list[dict] = []
    seen: set[str] = set()

    def add_item(item: dict):
        name_key = item["name"].lower()
        if name_key not in seen:
            seen.add(name_key)
            items.append(item)

    for t in turns:
        if t.get("speaker") != "merchant_agent":
            continue
        for name in t.get("selected_items") or []:
            match = catalog_by_name.get(name.lower())
            if match:
                add_item(match)

    if not items:
        for t in turns:
            if t["speaker"] == "merchant_agent" and t["action"] in ("offer", "accept"):
                msg = t.get("message", "").lower()
                for item in catalog:
                    name_words = item["name"].lower().split()
                    if any(w in msg for w in name_words):
                        add_item(item)

    if not items:
        items = [catalog[0]]

    total = sum(i["price"] for i in items)
    category = items[0].get("category", "electronics")
    return CartMandate(
        agent_id="merchant_agent_v1",
        items=items,
        total=total,
        category=category,
    )


async def finalize_cart(state: NegotiationState) -> dict:
    scenario = state.get("scenario")
    if scenario:
        catalog = [item.model_dump() for item in scenario.catalog]
    else:
        from warden.mandates.adapters.mock_adapter import MockAdapter

        catalog = MockAdapter().get_catalog()

    cart = build_cart_from_turns(state["turns"], catalog)
    return {"cart_mandate": cart}


def build_negotiation_graph():
    graph = StateGraph(NegotiationState)
    graph.add_node("buyer_turn", buyer_turn)
    graph.add_node("merchant_turn", merchant_turn)
    graph.add_node("finalize_cart", finalize_cart)

    graph.set_entry_point("buyer_turn")
    graph.add_edge("buyer_turn", "merchant_turn")
    graph.add_conditional_edges("merchant_turn", route_termination)
    graph.add_edge("finalize_cart", END)

    return graph.compile()
