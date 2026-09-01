"""Interactive, turn-by-turn negotiation API for the demo.

The replay page uses immutable fixtures.  This router is deliberately separate:
it keeps a short-lived session in memory, appends every user and merchant turn
to the normal transcript store, then runs the production detectors against the
signed cart after each exchange.  Provider failures use a deterministic
sabziwala reply, but the response is marked ``fallback`` so a demo never hides
that it degraded.
"""

import asyncio
import datetime
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from warden.detection.drift_scorer import drift_score
from warden.graph.negotiation_graph import build_cart_from_turns
from warden.mandates.schema import CanonicalMandate, IntentMandate
from warden.mandates.signing import sign_mandate
from warden.policy.policy_config import PolicyConfig
from warden.policy.verdict import warden_verdict
from warden.scenarios.loader import Scenario, load_scenario
from warden.services.authorization import evaluate_authorization
from warden.storage.transcript_store import TranscriptStore
from warden.storage.verdict_store import VerdictStore

router = APIRouter(prefix="/live", tags=["live negotiation"])

MAX_MESSAGE_CHARS = 2_000
MAX_BUYER_TURNS = 12
# Keep a presenter-facing turn responsive; the deterministic fallback handles
# provider timeouts without blocking the rest of the evidence pipeline.
AGENT_TIMEOUT_SECONDS = 8.0
MAX_LIVE_SESSIONS = 32
LIVE_SESSION_TTL_SECONDS = 1_800


class LiveSessionStartRequest(BaseModel):
    """Optional overrides for the default sabziwala mandate."""

    model_config = ConfigDict(extra="forbid")

    scenario: str = "sabziwala_vs_mom"
    intent_text: str | None = Field(default=None, max_length=1_000)
    max_price: float | None = Field(default=None, gt=0)
    red_lines: list[str] | None = Field(default=None, max_length=16)
    allowed_categories: list[str] | None = Field(default=None, max_length=16)

    @field_validator("intent_text")
    @classmethod
    def non_empty_intent(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("intent_text cannot be blank")
        return value.strip() if value is not None else value

    @field_validator("red_lines", "allowed_categories")
    @classmethod
    def bounded_items(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 200 for value in cleaned):
            raise ValueError("constraint entries must be 1-200 characters")
        return cleaned


class LiveTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def non_blank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class LiveReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


@dataclass
class LiveSession:
    session_id: str
    scenario: Scenario
    intent: IntentMandate
    transcript: list[dict[str, Any]] = field(default_factory=list)
    mode: Literal["live", "fallback"] = "live"
    reply_source: Literal["provider", "rules", "fallback"] = "provider"
    fallback_reasons: list[str] = field(default_factory=list)
    status: Literal["active", "awaiting_review", "completed", "blocked"] = "active"
    latest_evaluation: dict[str, Any] | None = None
    buyer_turns: int = 0
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())


_sessions: dict[str, LiveSession] = {}
_session_locks: dict[str, asyncio.Lock] = {}


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _lock_for(session_id: str) -> asyncio.Lock:
    return _session_locks.setdefault(session_id, asyncio.Lock())


def _prune_expired_sessions() -> None:
    now = datetime.datetime.now(datetime.UTC)
    expired = []
    for session_id, session in _sessions.items():
        created = datetime.datetime.fromisoformat(session.created_at)
        if (now - created).total_seconds() > LIVE_SESSION_TTL_SECONDS:
            expired.append(session_id)
    for session_id in expired:
        _sessions.pop(session_id, None)
        _session_locks.pop(session_id, None)


def _scenario_or_400(scenario_id: str) -> Scenario:
    try:
        return load_scenario(scenario_id)
    except FileNotFoundError as exc:
        raise HTTPException(400, f"Unknown scenario: {scenario_id}") from exc


def _intent_for(request: LiveSessionStartRequest, scenario: Scenario) -> IntentMandate:
    defaults = scenario.default_intent
    return IntentMandate(
        agent_id="buyer_agent_v1",
        raw_goal_text=request.intent_text or defaults["intent_text"],
        max_price=request.max_price if request.max_price is not None else defaults["max_price"],
        allowed_categories=request.allowed_categories or defaults["allowed_categories"],
        red_lines=request.red_lines if request.red_lines is not None else defaults["red_lines"],
    )


def _summary(turns: list[dict[str, Any]]) -> str:
    if not turns:
        return "This is the first turn. No prior messages."
    return "\n".join(f"{t['speaker']}: [{t.get('action', 'message')}] {t['message']}" for t in turns)


def _buyer_action(message: str) -> str:
    lowered = message.lower()
    if re.search(
        r"\b(accept|accepted|theek hai|done|final kar do|finalize(?: it)?|deal pakki|"
        r"i(?:'ll| will) take (?:it|them|these)|pack (?:it|them|these|kar do)|place the order|"
        r"order confirm(?:ed)?|confirm(?:ed)? (?:the )?(?:cart|order|deal))\b",
        lowered,
    ):
        return "accept"
    if re.search(
        r"\b(reject|cancel|no thanks|chod do|leave it|deal nahi chahiye|deal nahin chahiye|kuch nahi chahiye)\b",
        lowered,
    ):
        return "reject"
    return "counter"


ITEM_ALIASES = {
    "tamatar": ("tamatar", "tomato", "tomatoes", "tamataro", "टमाटर"),
    "pyaz": ("pyaz", "pyaaz", "onion", "onions", "प्याज", "प्याज़"),
    "aloo": ("aloo", "alu", "potato", "potatoes", "आलू"),
    "bhindi": ("bhindi", "okra", "ladyfinger", "lady finger", "भिंडी"),
    "dhaniya": ("dhaniya", "dhania", "coriander", "cilantro", "धनिया"),
}


def _aliases_for(name: str) -> tuple[str, ...]:
    normalized = name.lower()
    return tuple(dict.fromkeys((normalized, *ITEM_ALIASES.get(normalized, ()))))


def _catalog_matches(text: str, scenario: Scenario) -> list[dict[str, Any]]:
    lowered = text.lower()
    positioned = []
    for item in scenario.catalog:
        positions = [
            match.start()
            for alias in _aliases_for(item.name)
            if (match := re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered))
        ]
        if positions:
            positioned.append((min(positions), item.model_dump()))
    return [item for _position, item in sorted(positioned, key=lambda value: value[0])]


def _catalog_offer_item(item: dict[str, Any]) -> dict[str, Any]:
    description = str(item.get("description", "")).lower()
    gram_unit = re.search(r"per\s+(\d+(?:\.\d+)?)\s*g\b", description)
    if gram_unit:
        base_quantity = float(gram_unit.group(1)) / 1_000
        unit = "kg"
        unit_price = float(item["price"]) / base_quantity
    elif re.search(r"per\s+(?:kg|kilo)", description):
        base_quantity = 1.0
        unit = "kg"
        unit_price = float(item["price"])
    else:
        base_quantity = 1.0
        unit = "bundle"
        unit_price = float(item["price"])
    return {
        **item,
        "quantity": base_quantity,
        "unit": unit,
        "unit_price": unit_price,
        "price": float(item["price"]),
    }


def _previous_offer(session: LiveSession) -> list[dict[str, Any]]:
    catalog_by_name = {item.name.lower(): item.model_dump() for item in session.scenario.catalog}
    for turn in reversed(session.transcript):
        if turn.get("speaker") != "merchant_agent":
            continue
        offered = turn.get("offered_items") or []
        valid = []
        for item in offered:
            catalog_item = catalog_by_name.get(str(item.get("name", "")).lower()) if isinstance(item, dict) else None
            if not catalog_item:
                continue
            default_offer = _catalog_offer_item(catalog_item)
            quantity = float(item.get("quantity", default_offer["quantity"]))
            unit_price = float(item.get("unit_price", default_offer["unit_price"]))
            valid.append(
                {
                    **catalog_item,
                    "quantity": quantity,
                    "unit": str(item.get("unit", default_offer["unit"])),
                    "unit_price": unit_price,
                    "price": quantity * unit_price,
                }
            )
        if valid:
            return valid
        selected = [catalog_by_name.get(str(name).lower()) for name in turn.get("selected_items", [])]
        if any(selected):
            return [_catalog_offer_item(item) for item in selected if item]
    return []


def _quantity_from_message(message: str) -> float | None:
    match = re.search(
        r"(?<!\w)(\d+(?:\.\d+)?)\s*(kg|kilo(?:gram)?s?|grams?|g|किलो|ग्राम)(?!\w)",
        message,
        re.I,
    )
    if match:
        value = float(match.group(1))
        if match.group(2).lower().startswith("g") or match.group(2) == "ग्राम":
            value /= 1_000
        return value if 0 < value <= 100 else None
    lowered = message.lower()
    if re.search(r"(?<!\w)(?:aadha|half|आधा)\s*(?:kg|kilo|किलो)?(?!\w)", lowered):
        return 0.5
    if re.search(r"(?<!\w)(?:paav|pao|quarter|पाव)\s*(?:kg|kilo|किलो)?(?!\w)", lowered):
        return 0.25
    if re.search(r"(?<!\w)(?:do|two|दो)\s*(?:kg|kilo|किलो)(?!\w)", lowered):
        return 2.0
    if re.search(r"(?<!\w)(?:teen|three|तीन)\s*(?:kg|kilo|किलो)(?!\w)", lowered):
        return 3.0
    if re.search(r"(?<!\w)(?:ek|one|एक)\s*(?:kg|kilo|किलो)(?!\w)", lowered):
        return 1.0
    return None


def _quantity_for_item(message: str, item_name: str) -> float | None:
    quantities = [
        (
            match.span(),
            float(match.group(1)) / 1_000
            if match.group(2).lower().startswith("g") or match.group(2) == "ग्राम"
            else float(match.group(1)),
        )
        for match in re.finditer(
            r"(?<!\w)(\d+(?:\.\d+)?)\s*(kg|kilo(?:gram)?s?|grams?|g|किलो|ग्राम)(?!\w)",
            message,
            re.I,
        )
    ]
    quantities.extend(
        (match.span(), value)
        for pattern, value in (
            (r"(?<!\w)(?:aadha|half|आधा)\s*(?:kg|kilo|किलो)?(?!\w)", 0.5),
            (r"(?<!\w)(?:paav|pao|quarter|पाव)\s*(?:kg|kilo|किलो)?(?!\w)", 0.25),
            (r"(?<!\w)(?:ek|one|एक)\s*(?:kg|kilo|किलो)(?!\w)", 1.0),
            (r"(?<!\w)(?:do|two|दो)\s*(?:kg|kilo|किलो)(?!\w)", 2.0),
            (r"(?<!\w)(?:teen|three|तीन)\s*(?:kg|kilo|किलो)(?!\w)", 3.0),
        )
        for match in re.finditer(pattern, message, re.I)
    )
    candidates = []
    for alias in _aliases_for(item_name):
        for alias_match in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", message, re.I):
            alias_start, alias_end = alias_match.span()
            for (quantity_start, quantity_end), value in quantities:
                gap = max(alias_start - quantity_end, quantity_start - alias_end, 0)
                if gap <= 18:
                    candidates.append((gap, value))
    if not candidates:
        return None
    value = min(candidates, key=lambda candidate: candidate[0])[1]
    return value if 0 < value <= 100 else None


def _item_is_removed(message: str, item_name: str) -> bool:
    for alias in _aliases_for(item_name):
        escaped = re.escape(alias)
        if re.search(
            rf"(?<!\w){escaped}(?!\w)[^,.;]{{0,20}}\b(?:hata|remove|skip|nahi\s+chahiye|mat\s+do)\b",
            message,
            re.I,
        ) or re.search(
            rf"\b(?:hata(?:\s+do)?|remove|skip|without|no)\s+(?<!\w){escaped}(?!\w)",
            message,
            re.I,
        ):
            return True
    return False


def _requires_structured_reply(message: str, scenario: Scenario) -> bool:
    if _catalog_matches(message, scenario) or _quantity_from_message(message) is not None:
        return True
    if _buyer_action(message) in {"accept", "reject"}:
        return True
    return bool(
        re.search(
            r"\b(?:rate|price|cost|kitna|budget|fresh|taaza|quality|stale|dikhao|show|catalog|options|"
            r"add|saath|remove|hata|skip|jagah|instead|replace|discount|sasta|mehenga|kam\s+karo|"
            r"dono|both|each|pack|cart|total|available|kya\s+kya|rs\.?|rupees?|rupaye?|rupay)\b",
            message,
            re.I,
        )
    )


def _replacement_names(message: str, direct: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Resolve (removed, replacement) for common Hindi and English ordering."""

    names_by_alias = {alias.lower(): item["name"].lower() for item in direct for alias in _aliases_for(item["name"])}
    alias_pattern = "|".join(sorted((re.escape(alias) for alias in names_by_alias), key=len, reverse=True))
    if not alias_pattern:
        return None
    patterns = (
        rf"(?P<old>{alias_pattern})\s+(?:ki\s+)?jagah\s+(?P<new>{alias_pattern})",
        rf"(?P<new>{alias_pattern})\s+instead\s+of\s+(?P<old>{alias_pattern})",
        rf"replace\s+(?P<old>{alias_pattern})\s+with\s+(?P<new>{alias_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.I)
        if match:
            return names_by_alias[match.group("old").lower()], names_by_alias[match.group("new").lower()]
    return None


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique[item["name"].lower()] = item
    return list(unique.values())


def _offer_breakdown(items: list[dict[str, Any]]) -> str:
    return " aur ".join(
        f"{item['quantity']:g} {item.get('unit', 'unit')} {item['name']} Rs.{item['price']:g}" for item in items
    )


def _catalog_rate_card(session: LiveSession) -> str:
    rates = []
    for item in session.scenario.catalog:
        offer = _catalog_offer_item(item.model_dump())
        label = f"{offer['quantity']:g} {offer['unit']}"
        rates.append(f"{item.name} Rs.{item.price:g}/{label}")
    return ", ".join(rates)


def _fallback_conversation_reply(message: str, offer: str, total: float) -> str:
    """Give useful market-context replies when no model provider is reachable."""

    lowered = message.lower()
    current = f" Current offer {offer}; total Rs.{total:g}." if offer else ""
    if re.search(r"\b(?:deliver|delivery|home|ghar|bhej|pickup)\b", lowered):
        return "Didi, is demo stall mein home delivery configured nahi hai; mandi pickup hi hai." + current
    if re.search(r"\b(?:pay|payment|upi|cash|card|razorpay|gpay|phonepe)\b", lowered):
        return (
            "Payment Warden clearance ke baad Razorpay test mode mein banta hai; abhi koi paisa move nahi hua."
            + current
        )
    if re.search(r"\b(?:organic|chemical|pesticide|source|kahan\s+se|mandi)\b", lowered):
        return (
            "Aaj ka stock local mandi se aaya hai. Main organic certification ka jhootha claim nahi karunga." + current
        )
    if re.search(r"\b(?:recipe|pakau|banao|cook|cooking)\b", lowered):
        return (
            "Tamatar-pyaz ki sabzi ya gravy achchi banegi; recipe se pehle quantity aur final rate pakka kar lete hain."
            + current
        )
    if re.search(r"\b(?:thank|thanks|shukriya|dhanyavaad)\b", lowered):
        return "Shukriya didi. Rate ya cart mein aur koi badlav ho toh bol dijiye." + current
    if re.search(r"\b(?:how are you|kaise ho|naam kya|your name|who are you)\b", lowered):
        return (
            "Bilkul badhiya didi, main Warden demo ka sabziwala agent hoon. Aap natural language mein cart badal sakti hain."
            + current
        )
    return (
        "Didi, us baat ka pakka jawab mere paas nahi hai. Main sabzi, quantity, rate, freshness, cart aur payment ke "
        "baare mein sahi jawab de sakta hoon." + current
    )


def _has_grounded_conversation_reply(message: str) -> bool:
    return bool(
        re.search(
            r"\b(?:deliver|delivery|home|ghar|bhej|pickup|pay|payment|upi|cash|card|razorpay|gpay|phonepe|"
            r"organic|chemical|pesticide|source|mandi|recipe|pakau|banao|cook|cooking|thank|thanks|"
            r"shukriya|dhanyavaad|how are you|kaise ho|naam kya|your name|who are you)\b",
            message,
            re.I,
        )
    )


def _live_buyer_reasoning(session: LiveSession, message: str) -> str:
    """Turn a terse chat utterance into the buyer state the drift model expects.

    Agent reasoning traces normally restate their active objective. Human chat
    turns do not: "kitna?" or "swap the bhindi" are fragments. Scoring those
    fragments directly creates false drift, so live mode preserves the original
    mandate and resolved cart while retaining the verbatim instruction.
    """

    current = _previous_offer(session)
    cart_names = ", ".join(item["name"] for item in current) or "no settled items"
    return (
        f"Original mandate remains: {session.intent.raw_goal_text}. "
        f"Current negotiated cart: {cart_names}. Latest buyer instruction: {message}"
    )


def _bounded_merchant(session: LiveSession, *, source: Literal["rules", "fallback"] = "rules") -> dict[str, Any]:
    """Handle transactional language without losing offer or consent state."""

    message = next(
        (turn.get("message", "") for turn in reversed(session.transcript) if turn.get("speaker") == "buyer_agent"),
        session.intent.raw_goal_text,
    )
    lowered = message.lower()
    direct = _catalog_matches(message, session.scenario)
    previous = _previous_offer(session)
    previous_by_name = {item["name"].lower(): item for item in previous}
    direct_by_name = {item["name"].lower(): item for item in direct}
    replacement_names = _replacement_names(message, direct)
    replace_mode = replacement_names is not None
    add_mode = bool(re.search(r"\b(?:add|bhi|saath|include|plus)\b", lowered))
    remove_all = bool(re.search(r"\b(?:dono|both|sab)\b", lowered)) and bool(
        re.search(r"\b(?:hata|remove|skip|mat\s+do|nahi\s+chahiye)\b", lowered)
    )

    if remove_all:
        selected = []
    elif replace_mode:
        removed_name, replacement_name = replacement_names
        selected = [item for item in previous if item["name"].lower() != removed_name]
        replacement = direct_by_name[replacement_name]
        selected.append(previous_by_name.get(replacement_name, replacement))
    elif direct:
        removed = {item["name"].lower() for item in direct if _item_is_removed(message, item["name"])}
        additions = [
            previous_by_name.get(item["name"].lower(), item) for item in direct if item["name"].lower() not in removed
        ]
        if removed:
            selected = [item for item in previous if item["name"].lower() not in removed]
            selected.extend(item for item in additions if item["name"].lower() not in removed)
        elif add_mode or ("free" in lowered and "dhaniya" in direct_by_name):
            selected = list(previous)
            selected.extend(item for item in additions if item["name"].lower() not in previous_by_name)
        else:
            selected = additions
    else:
        selected = previous or _catalog_matches(session.intent.raw_goal_text, session.scenario)
    selected = _dedupe_items(selected)

    quantity = _quantity_from_message(message)
    applies_to_all = bool(re.search(r"\b(?:dono|both|each|har)\b", message, re.I)) or len(selected) == 1
    bargain = bool(
        re.search(
            r"\b(?:discount|sasta|mehenga|zyada|kam\s+karo|best\s+rate|final\s+rate|"
            r"\d+(?:\.\d+)?\s*(?:rs\.?|rupees?|rupaye?|rupay|mein|me)\s+(?:kar|mein|me|do|de))\b",
            lowered,
        )
    )
    offered_items = []
    for item in selected:
        specific_quantity = _quantity_for_item(message, item["name"])
        item_quantity = (
            specific_quantity
            if specific_quantity is not None
            else quantity
            if quantity is not None and applies_to_all
            else float(item.get("quantity", 1))
        )
        catalog_item = next(entry for entry in session.scenario.catalog if entry.name == item["name"])
        default_offer = _catalog_offer_item(catalog_item.model_dump())
        if specific_quantity is None and not (quantity is not None and applies_to_all):
            item_quantity = float(item.get("quantity", default_offer["quantity"]))
        unit_price = float(item.get("unit_price", default_offer["unit_price"]))
        if bargain:
            unit_price = max(float(catalog_item.price) * 0.8, round(unit_price * 0.9))
        if item["name"].lower() == "dhaniya" and "free" in lowered:
            unit_price = 0.0
        offered_items.append(
            {
                "name": item["name"],
                "quantity": item_quantity,
                "unit": default_offer["unit"],
                "unit_price": unit_price,
                "price": round(item_quantity * unit_price, 2),
            }
        )

    total = sum(item["price"] for item in offered_items)
    breakdown = _offer_breakdown(offered_items)
    action = _buyer_action(message)
    full_catalog = bool(re.search(r"\b(?:catalog|options|kya\s+kya|what\s+do\s+you\s+have|available)\b", lowered))
    freshness = bool(re.search(r"\b(?:fresh|taaza|taza|quality|stale|sada|mandi)\b", lowered))
    greeting = bool(re.fullmatch(r"\s*(?:hi|hello|hey|namaste|namaskar|bhaiya|didi)[!.,\s]*", lowered))
    if not offered_items:
        message_text = (
            f"Didi, cart abhi khaali hai. Aaj ke rates: {_catalog_rate_card(session)}. Kya aur kitna chahiye?"
        )
    elif action == "accept":
        message_text = f"Theek hai didi, {breakdown} pack kar deta hoon. Total Rs.{total:g}."
    elif action == "reject":
        message_text = "Koi baat nahi didi, aap araam se sochiye. Main deal hold nahi karunga."
    elif full_catalog:
        message_text = (
            f"Aaj ke rates: {_catalog_rate_card(session)}. Aapka current offer {breakdown}; total Rs.{total:g}."
        )
    elif freshness:
        message_text = f"Didi, {', '.join(item['name'] for item in offered_items)} aaj ka fresh mandi stock hai. {breakdown}; total Rs.{total:g}."
    elif bargain:
        message_text = f"Aapke liye rate kam karke {breakdown}; final total Rs.{total:g}."
    elif greeting:
        message_text = f"Namaste didi. Aapka current offer {breakdown}; total Rs.{total:g}. Rate, quantity ya freshness pooch lijiye."
    elif (source == "fallback" or _has_grounded_conversation_reply(message)) and not _requires_structured_reply(
        message, session.scenario
    ):
        message_text = _fallback_conversation_reply(message, breakdown, total)
    else:
        over_by = total - float(session.intent.max_price)
        if over_by > 0:
            message_text = (
                f"Didi, {breakdown}; total Rs.{total:g}. Yeh aapke Rs.{session.intent.max_price:g} "
                f"budget se Rs.{over_by:g} zyada hai. Quantity kam karun?"
            )
        elif session.buyer_turns == 0:
            message_text = f"Aaiye didi, {breakdown}; total Rs.{total:g}. Sab bilkul taaza hai."
        elif not _requires_structured_reply(message, session.scenario):
            message_text = (
                f"Didi, main current offer sambhal ke rakhta hoon: {breakdown}; total Rs.{total:g}. "
                "Sabzi, quantity, rate, freshness, add ya remove jo chahiye seedha bol dijiye."
            )
        else:
            message_text = f"Didi, {breakdown}; total Rs.{total:g}. Yeh aapke budget ke andar hai."
    session.reply_source = source
    return {
        "action": "accept" if action == "accept" else "reject" if action == "reject" else "offer",
        "reasoning": "Preserve the active catalog offer, quantity, and budget context across the negotiation.",
        "message": message_text,
        "selected_items": [item["name"] for item in offered_items],
        "offered_items": offered_items,
    }


async def _merchant_reply(session: LiveSession) -> dict[str, Any]:
    """Ask the configured provider first; expose fallback state on any failure."""

    from warden.agents.merchant_agent import MerchantAgent

    latest_buyer_message = next(
        (turn.get("message", "") for turn in reversed(session.transcript) if turn.get("speaker") == "buyer_agent"),
        None,
    )
    # A grounded opening is faster and cannot invent catalog state. Once a
    # provider fails, keep this session on the deterministic path instead of
    # making the presenter wait through the same timeout on every turn.
    if latest_buyer_message is None:
        return _bounded_merchant(session, source="rules")
    if session.mode == "fallback":
        return _bounded_merchant(session, source="fallback")
    if latest_buyer_message and _requires_structured_reply(latest_buyer_message, session.scenario):
        return _bounded_merchant(session, source="rules")
    if _has_grounded_conversation_reply(latest_buyer_message):
        return _bounded_merchant(session, source="rules")

    try:
        previous_offer = _previous_offer(session)
        dialogue = await asyncio.wait_for(
            MerchantAgent(scenario=session.scenario).converse(_summary(session.transcript)),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        payload = {
            "action": "offer",
            "reasoning": dialogue.reasoning,
            "message": dialogue.message,
            "selected_items": [],
        }
        if (
            len(str(payload.get("message", ""))) > MAX_MESSAGE_CHARS
            or len(str(payload.get("reasoning", ""))) > MAX_MESSAGE_CHARS
        ):
            raise ValueError("merchant response exceeded the message limit")
        catalog_by_name = {item.name: item.model_dump() for item in session.scenario.catalog}
        if previous_offer:
            # Free-form answers can change the dialogue, but only a structured
            # buyer request may mutate quantity, price, or cart membership.
            payload["selected_items"] = [item["name"] for item in previous_offer]
            payload["offered_items"] = previous_offer
        else:
            valid_names = set(catalog_by_name)
            payload["selected_items"] = [name for name in payload.get("selected_items", []) if name in valid_names]
            payload["offered_items"] = [
                _catalog_offer_item(catalog_by_name[name]) for name in payload["selected_items"]
            ]
        # A merchant mentioning a catalog item is an offer, not buyer consent.
        # Do not infer or default ``selected_items`` from message substrings.
        if payload.get("action") not in {"offer", "accept", "reject"}:
            raise ValueError("merchant agent returned an invalid action")
        if re.search(r"\bRs\.?\s*0(?:\.0+)?\b|catalog options", str(payload.get("message", "")), re.I):
            raise ValueError("merchant agent returned an empty placeholder offer")
        session.reply_source = "provider"
        return payload
    except Exception as exc:  # provider, timeout, validation, or malformed output
        reason = f"{type(exc).__name__}: {str(exc)[:180]}"
        session.mode = "fallback"
        session.fallback_reasons.append(reason)
        return _bounded_merchant(session, source="fallback")


def _persist_live_verdict(session: LiveSession, evaluation: dict[str, Any]) -> None:
    VerdictStore().save(
        session.session_id,
        {
            "tx_id": session.session_id,
            "session_id": session.session_id,
            "scenario_id": session.scenario.id,
            "verdict": evaluation["verdict"],
            "explanation": evaluation["explanation"],
            "signals": evaluation["signals"],
            "trust_score_trajectory": evaluation["trust_score_trajectory"],
            "mode": session.mode,
            "timestamp": _now(),
        },
    )


def _evaluate(session: LiveSession) -> dict[str, Any]:
    """Run the same signed-cart detectors and policy used by the Warden graph."""

    catalog = [item.model_dump() for item in session.scenario.catalog]
    cart = build_cart_from_turns(session.transcript, catalog)
    signed_cart = sign_mandate(cart, _merchant_private_key())
    canonical = CanonicalMandate(intent=session.intent, cart=signed_cart)
    result = evaluate_authorization(
        canonical,
        session.transcript,
        PolicyConfig(**session.scenario.policy_overrides.model_dump()),
        drift_fn=drift_score,
        verdict_fn=warden_verdict,
    )
    if cart.agreement_status == "agreed":
        return result

    # Before explicit buyer acceptance there is no authorization to approve or
    # reject for cart ambiguity. Semantic attacks may still stop the exchange,
    # but an ordinary offer remains a visibly provisional analysis state.
    semantic_signals = dict(result["signals"])
    # Cart/category/price checks have no settled subject until the buyer agrees.
    # They all remain pending rather than leaking a provisional empty cart into
    # the final policy decision.
    semantic_signals["violations"] = []
    semantic_verdict, semantic_explanation = warden_verdict(
        semantic_signals,
        PolicyConfig(**session.scenario.policy_overrides.model_dump()),
    )
    if result.get("degraded") and semantic_verdict == "PASS":
        result["verdict"] = "STEPUP"
        result["explanation"] = "A required detector was unavailable. Human review is required before authorization."
    elif semantic_verdict == "PASS":
        result["verdict"] = "ANALYSIS"
        result["explanation"] = "Monitoring the negotiation. Authorization waits for explicit buyer agreement."
    else:
        result["verdict"] = semantic_verdict
        result["explanation"] = semantic_explanation
    result["signals"] = semantic_signals
    result["detectors"]["constraints"] = {"status": "pending", "violations": []}
    offered_items = _previous_offer(session)
    result["cart"] = {
        "agent_id": "merchant_agent_v1",
        "items": offered_items,
        "total": round(sum(float(item["price"]) for item in offered_items), 2),
        "category": offered_items[0].get("category", "unknown") if offered_items else "unknown",
        "signature": None,
        "agreement_status": "pending",
        "agreement_evidence": [],
        "extraction_warnings": ["awaiting_explicit_buyer_agreement"],
    }
    return result


def _merchant_private_key():
    from warden.keys import ensure_keys_loaded, get_private_key

    ensure_keys_loaded()
    return get_private_key("merchant_agent_v1")


def _response(session: LiveSession, latest_turn: dict[str, Any] | None = None) -> dict[str, Any]:
    evaluation = session.latest_evaluation or {
        "verdict": "PASS",
        "explanation": "Awaiting first exchange.",
        "signals": {},
        "trust_score_trajectory": [],
        "cart": None,
        "detectors": {},
    }
    decision_state = "provisional"
    if session.status == "awaiting_review":
        decision_state = "review_required"
    elif session.status in {"completed", "blocked"}:
        decision_state = "final"
    return {
        "session_id": session.session_id,
        "tx_id": session.session_id,
        "scenario_id": session.scenario.id,
        "scenario": session.scenario.display_name,
        "status": session.status,
        "decision_state": decision_state,
        "can_continue": session.status == "active",
        "mode": session.mode,
        "reply_source": session.reply_source,
        "degraded": session.mode == "fallback" or bool(evaluation.get("degraded")),
        "detector_errors": evaluation.get("signals", {}).get("detector_errors", []),
        "fallback_reasons": session.fallback_reasons,
        "turn_count": session.buyer_turns,
        "transcript": session.transcript,
        "latest_turn": latest_turn,
        "verdict": evaluation["verdict"],
        "explanation": evaluation["explanation"],
        "signals": evaluation["signals"],
        "detectors": evaluation["detectors"],
        "trust_score_trajectory": evaluation["trust_score_trajectory"],
        "cart": evaluation["cart"],
        "created_at": session.created_at,
    }


async def _start_session(request: LiveSessionStartRequest) -> dict[str, Any]:
    _prune_expired_sessions()
    if len(_sessions) >= MAX_LIVE_SESSIONS:
        raise HTTPException(429, "Live demo capacity is full; wait for an existing session to expire")
    scenario = _scenario_or_400(request.scenario)
    session_id = f"live_{uuid.uuid4().hex[:20]}"
    session = LiveSession(session_id=session_id, scenario=scenario, intent=_intent_for(request, scenario))
    _sessions[session_id] = session
    _session_locks[session_id] = asyncio.Lock()

    # Open with a merchant greeting so the first screen has a real exchange.
    merchant = await _merchant_reply(session)
    opening = {
        "speaker": "merchant_agent",
        "action": merchant["action"],
        "reasoning": merchant["reasoning"],
        "message": merchant["message"],
        "timestamp": _now(),
        "selected_items": merchant.get("selected_items", []),
        "offered_items": merchant.get("offered_items", []),
    }
    session.transcript.append(opening)
    TranscriptStore().reset(session_id)
    TranscriptStore().append_turn(session_id, opening)
    session.latest_evaluation = _evaluate(session)
    if session.latest_evaluation["verdict"] == "REJECT":
        session.status = "blocked"
    elif session.latest_evaluation["verdict"] == "STEPUP":
        session.status = "awaiting_review"
    _persist_live_verdict(session, session.latest_evaluation)
    return _response(session, opening)


@router.post("/sessions", status_code=201)
async def start_live_session(request: LiveSessionStartRequest | None = None):
    """Start an interactive sabziwala conversation."""

    return await _start_session(request or LiveSessionStartRequest())


@router.post("/sessions/{session_id}/turns")
async def append_live_turn(session_id: str, request: LiveTurnRequest):
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(404, f"No live session {session_id}")
    async with _lock_for(session_id):
        if session.status != "active":
            raise HTTPException(409, f"Session is {session.status}; start a new conversation")
        buyer_action = _buyer_action(request.message)
        buyer = {
            "speaker": "buyer_agent",
            "action": buyer_action,
            "reasoning": f"User said: {request.message}",
            "message": request.message,
            "timestamp": _now(),
        }
        session.transcript.append(buyer)
        session.buyer_turns += 1

        merchant_data = await _merchant_reply(session)
        merchant = {
            "speaker": "merchant_agent",
            "action": merchant_data["action"],
            "reasoning": merchant_data["reasoning"],
            "message": merchant_data["message"],
            "timestamp": _now(),
            "selected_items": merchant_data.get("selected_items", []),
            "offered_items": merchant_data.get("offered_items", []),
        }
        session.transcript.append(merchant)
        buyer["reasoning"] = _live_buyer_reasoning(session, request.message)
        TranscriptStore().append_turn(session_id, buyer)
        TranscriptStore().append_turn(session_id, merchant)

        session.latest_evaluation = _evaluate(session)
        verdict = session.latest_evaluation["verdict"]
        if verdict == "REJECT":
            session.status = "blocked"
        elif verdict == "STEPUP":
            session.status = "awaiting_review"
        elif buyer_action in {"accept", "reject"} or session.buyer_turns >= MAX_BUYER_TURNS:
            session.status = "completed"
        _persist_live_verdict(session, session.latest_evaluation)
        return _response(session, merchant)


@router.get("/sessions/{session_id}")
async def get_live_session(session_id: str):
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(404, f"No live session {session_id}")
    async with _lock_for(session_id):
        return _response(session)


@router.post("/sessions/{session_id}/review")
async def review_live_session(session_id: str, request: LiveReviewRequest):
    """Resolve a live STEPUP without requiring a LangGraph checkpoint."""

    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(404, f"No live session {session_id}")
    async with _lock_for(session_id):
        if session.status != "awaiting_review" or not session.latest_evaluation:
            raise HTTPException(409, "Session is not awaiting a live review")
        if request.approved:
            session.latest_evaluation["verdict"] = "PASS"
            session.latest_evaluation["explanation"] = "Human approved the paused negotiation."
            session.status = "completed"
        else:
            session.latest_evaluation["verdict"] = "REJECT"
            session.latest_evaluation["explanation"] = "Human rejected during STEPUP review."
            session.status = "blocked"
        _persist_live_verdict(session, session.latest_evaluation)
        return _response(session)


def clear_live_sessions() -> None:
    """Test hook and development reset; production callers should start a new session."""

    _sessions.clear()
    _session_locks.clear()
