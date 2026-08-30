"""Stub mapping between our internal mandate schema and Google's Agent Payments Protocol (AP2).
Minimal mapping to demonstrate protocol-adaptability."""

from pydantic import BaseModel


class AP2IntentPayload(BaseModel):
    merchant_id: str = "default_merchant"
    agent_id: str
    intent_text: str
    max_amount: float
    constraints: dict


class AP2CartPayload(BaseModel):
    cart_id: str
    items: list[dict]
    total_amount: float
    currency: str = "INR"
    agent_signature: str | None = None


def intent_to_ap2(intent) -> AP2IntentPayload:
    return AP2IntentPayload(
        agent_id=intent.agent_id,
        intent_text=intent.raw_goal_text,
        max_amount=intent.max_price,
        constraints={"categories": intent.allowed_categories, "red_lines": intent.red_lines},
    )


def cart_to_ap2(cart) -> AP2CartPayload:
    return AP2CartPayload(
        cart_id=cart.agent_id,
        items=cart.items,
        total_amount=cart.total,
        agent_signature=cart.signature,
    )
