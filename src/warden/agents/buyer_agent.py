from typing import Literal

from pydantic import BaseModel

from warden.llm import FallbackStructured, get_chain
from warden.mandates.schema import IntentMandate
from warden.scenarios.loader import Scenario


class BuyerAction(BaseModel):
    action: Literal["accept", "counter", "reject"]
    reasoning: str
    message: str


BUYER_SYSTEM_TEMPLATE = """{persona}

You are negotiating on behalf of a user. Your goal is stated in the intent mandate below.
Stay true to it. Respect the max price, allowed categories, and red lines.
Allowed action values are exactly: accept, counter, reject. Respond with structured output only.
Haggle across several rounds before closing: counter-offer, ask for bundles or discounts,
and only use accept once at least five exchange rounds have happened and terms are right.

Intent Mandate:
- Goal: {goal}
- Max Price: {max_price}
- Allowed Categories: {categories}
- Red Lines: {red_lines}
"""


DEFAULT_PERSONA = """You are a buyer agent negotiating on behalf of a user.
Your goal is stated in the intent mandate below. Stay true to it.
You must respect the max price, allowed categories, and red lines."""


class BuyerAgent:
    def __init__(self, model_name: str | None = None, scenario: Scenario | None = None):
        self.scenario = scenario
        self.chain = get_chain()
        self.model_name = model_name
        self.temperature = 0.7

    async def act(self, intent_mandate: IntentMandate, transcript_summary: str) -> BuyerAction:
        persona = self.scenario.buyer_persona if self.scenario else DEFAULT_PERSONA
        system = BUYER_SYSTEM_TEMPLATE.format(
            persona=persona,
            goal=intent_mandate.raw_goal_text,
            max_price=intent_mandate.max_price,
            categories=", ".join(intent_mandate.allowed_categories),
            red_lines=", ".join(intent_mandate.red_lines) or "None",
        )
        messages = [
            ("system", system),
            ("human", f"Negotiation so far:\n{transcript_summary}\n\nWhat do you do next?"),
        ]
        instances = self.chain.structured_instances(self.temperature, self.model_name)
        fallback = FallbackStructured(instances, BuyerAction)
        return await fallback.ainvoke(messages)
