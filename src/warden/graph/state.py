from typing import Any, Literal, NotRequired, TypedDict

from warden.mandates.schema import CartMandate, IntentMandate


class Turn(TypedDict):
    speaker: Literal["buyer_agent", "merchant_agent"]
    action: str
    reasoning: str
    message: str
    timestamp: str
    selected_items: NotRequired[list[str]]
    offered_items: NotRequired[list[dict[str, Any]]]


class NegotiationState(TypedDict):
    tx_id: str
    intent_mandate: IntentMandate
    turns: list[Turn]
    cart_mandate: CartMandate | None
    turn_count: int
    max_turns: int
    attacker_payload: str | None
    attack_type: Literal["injection", "gradual_drift"] | None
    scenario: Any  # Scenario object or None
