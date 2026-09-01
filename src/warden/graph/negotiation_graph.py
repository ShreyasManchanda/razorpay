import datetime
import math
import re
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
    """Build a cart only from evidence of buyer agreement.

    Merchant ``selected_items`` is an offer/settlement hint, not proof that a
    buyer accepted every item.  Older code used message substring matching and
    finally defaulted to the first catalog item; both behaviours can turn a
    suggestion into an authorization.  Ambiguous transcripts now produce an
    empty, explicitly marked cart so the constraint/policy layer fails closed.
    """
    catalog_by_name = {item["name"].lower(): item for item in catalog}
    items: list[dict] = []
    seen: set[str] = set()
    evidence: list[str] = []
    warnings: list[str] = []

    def add_item(item: dict, reason: str):
        name_key = item["name"].lower()
        if name_key not in seen:
            seen.add(name_key)
            items.append(item)
            evidence.append(reason)

    def matching_names(message: str) -> list[str]:
        """Return catalog names explicitly referred to by a buyer message.

        Full names are preferred; a single distinctive catalog token is
        accepted only when it identifies exactly one item.  This avoids the
        old ``any(word in message)`` over-match (e.g. a charger suggestion).
        """
        text = str(message or "").lower()
        exact = [item["name"] for item in catalog if item["name"].lower() in text]
        if exact:
            return exact
        stop = {"the", "a", "an", "pro", "lite", "fast", "wireless", "smart", "usb", "c"}
        token_hits: dict[str, int] = {}
        for item in catalog:
            tokens = {t for t in re.findall(r"[a-z0-9]+", item["name"].lower()) if t not in stop and len(t) > 2}
            hits = sum(1 for token in tokens if re.search(rf"\b{re.escape(token)}\b", text))
            if hits:
                token_hits[item["name"]] = hits
        # A token is safe only if it identifies one catalog item.
        return [name for name, hits in token_hits.items() if hits >= 1] if len(token_hits) == 1 else []

    def structured_items(turn: Turn) -> list[tuple[str, dict]]:
        """Resolve structured item names without treating malformed fields as evidence."""
        raw_offers = turn.get("offered_items") or []
        resolved_offers: list[tuple[str, dict]] = []
        if isinstance(raw_offers, list):
            for raw_offer in raw_offers:
                if not isinstance(raw_offer, dict):
                    continue
                match = catalog_by_name.get(str(raw_offer.get("name", "")).lower())
                if not match:
                    continue
                try:
                    quantity = float(raw_offer.get("quantity", 1))
                    unit_price = float(raw_offer.get("unit_price", match["price"]))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(quantity) or not math.isfinite(unit_price):
                    continue
                if quantity <= 0 or quantity > 100 or unit_price < 0 or unit_price > 1_000_000:
                    continue
                offered = dict(match)
                offered.update(
                    quantity=quantity,
                    unit=str(raw_offer.get("unit", "unit")),
                    unit_price=unit_price,
                    price=round(quantity * unit_price, 2),
                )
                resolved_offers.append((match["name"], offered))
        if resolved_offers:
            return resolved_offers

        raw_items = turn.get("selected_items") or []
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        resolved: list[tuple[str, dict]] = []
        for raw_name in raw_items:
            match = catalog_by_name.get(str(raw_name).lower())
            if match:
                resolved.append((match["name"], match))
        return resolved

    affirmative = re.compile(
        r"\b(?:accept|accepted|agree|confirmed|confirm|buy|purchase|take|go\s+with|let'?s\s+do\s+it|yes)\b",
        re.I,
    )
    negative = re.compile(r"\b(?:would\s+you\s+like|suggest|optional|maybe|consider|offer)\b", re.I)

    for idx, turn in enumerate(turns):
        speaker = turn.get("speaker")
        if speaker == "merchant_agent":
            continue
        if speaker != "buyer_agent":
            continue
        message = str(turn.get("message", ""))
        selected = [name for name, _match in structured_items(turn)]
        explicit = matching_names(message)
        is_accept = str(turn.get("action", "")).lower() == "accept" or bool(affirmative.search(message))
        if not is_accept or negative.search(message):
            continue
        accepted = selected or explicit
        evidence_prefix = f"buyer_agreement:turn_{idx}"
        offered_by_name: dict[str, dict] = {}
        # A generic acceptance ("yes", "final kar do") is valid only when it
        # follows a structured merchant offer. Explicitly named acceptance also
        # inherits quantity and negotiated price from the nearest matching offer.
        for offer_idx in range(idx - 1, -1, -1):
            offer_turn = turns[offer_idx]
            if offer_turn.get("speaker") != "merchant_agent":
                continue
            offer_items = structured_items(offer_turn)
            if not offer_items:
                continue
            offer_message = str(offer_turn.get("message", ""))
            optional_add_on = re.search(
                r"\b(?:would\s+you\s+like|optional|add|accessor(?:y|ies)|charger)\b",
                offer_message,
                re.I,
            )
            if optional_add_on and not accepted:
                break
            candidate = {name.lower(): item for name, item in offer_items}
            if accepted and not any(name.lower() in candidate for name in accepted):
                continue
            offered_by_name = candidate
            if not accepted:
                accepted = [name for name, _match in offer_items]
            evidence_prefix = f"buyer_agreement:turn_{idx}:merchant_offer_turn_{offer_idx}"
            break
        if not accepted:
            warnings.append(f"buyer_acceptance_ambiguous:turn_{idx}")
            continue
        for name in accepted:
            match = offered_by_name.get(name.lower()) or catalog_by_name.get(name.lower())
            if match:
                add_item(match, f"{evidence_prefix}:{match['name']}")

    if not items:
        warnings.append("no_explicit_buyer_agreement")

    total = sum(i["price"] for i in items)
    category = items[0].get("category", "unknown") if items else "unknown"
    return CartMandate(
        agent_id="merchant_agent_v1",
        items=items,
        total=total,
        category=category,
        agreement_status="agreed" if items else "ambiguous",
        agreement_evidence=evidence,
        extraction_warnings=warnings,
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
