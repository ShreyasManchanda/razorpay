"""MCP adapter for Warden's side-effect-free authorization decision."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, model_validator

from warden.mandates.schema import CanonicalMandate, CartMandate, IntentMandate
from warden.policy.policy_config import B2B_RECEIVABLES_POLICY, QUICK_COMMERCE_POLICY
from warden.services.authorization import evaluate_authorization

MAX_TRANSCRIPT_TURNS = 48
MAX_TEXT_CHARS = 2_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntentInput(StrictModel):
    agent_id: str = Field(min_length=1, max_length=120)
    raw_goal_text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    max_price: float = Field(gt=0, allow_inf_nan=False)
    allowed_categories: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(min_length=1, max_length=24)
    red_lines: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(default_factory=list, max_length=24)


class CartItemInput(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    # Preserve integer-versus-float JSON representation because Ed25519 signs
    # the exact canonical payload bytes.
    price: int | float = Field(ge=0, allow_inf_nan=False)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class SignedCartInput(StrictModel):
    agent_id: str = Field(min_length=1, max_length=120)
    items: list[CartItemInput] = Field(min_length=1, max_length=64)
    total: float = Field(gt=0, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=120)
    signature: str = Field(min_length=128, max_length=128, pattern=r"^[0-9a-fA-F]+$")
    agreement_status: Literal["agreed"]
    agreement_evidence: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(min_length=1, max_length=32)
    extraction_warnings: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=32
    )

    @model_validator(mode="after")
    def has_buyer_agreement_evidence(self):
        if not any("buyer_agreement" in evidence for evidence in self.agreement_evidence):
            raise ValueError("agreement_evidence must include a buyer_agreement record")
        return self


class TranscriptTurnInput(StrictModel):
    speaker: Literal["buyer_agent", "merchant_agent"]
    action: Literal["message", "offer", "counter", "accept", "reject"]
    reasoning: str = Field(default="", max_length=MAX_TEXT_CHARS)
    message: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    timestamp: str | None = Field(default=None, max_length=80)


class AuthorizationRequest(StrictModel):
    intent: IntentInput
    signed_cart: SignedCartInput
    transcript: list[TranscriptTurnInput] = Field(min_length=2, max_length=MAX_TRANSCRIPT_TURNS)
    policy_name: Literal["quick_commerce", "b2b_receivables"] = "quick_commerce"

    @model_validator(mode="after")
    def includes_both_agents(self):
        speakers = {turn.speaker for turn in self.transcript}
        if speakers != {"buyer_agent", "merchant_agent"}:
            raise ValueError("transcript must contain at least one buyer_agent and one merchant_agent turn")
        return self


class AuthorizationResponse(StrictModel):
    verdict: Literal["PASS", "STEPUP", "REJECT"]
    explanation: str
    policy_name: Literal["quick_commerce", "b2b_receivables"]
    signature_valid: bool
    signals: dict
    detectors: dict
    trust_score_trajectory: list[float]
    cart_total: float
    degraded: bool
    detector_errors: list[str]
    payment_executed: Literal[False] = False


mcp = FastMCP(
    "Project Warden",
    instructions=(
        "Authorize a signed agent-commerce mandate using Warden's signature gate, "
        "parallel security detectors, and named policy. This server never executes payment."
    ),
)


@mcp.tool(
    name="warden_authorize_payment",
    title="Authorize an agent payment",
    description=(
        "Verify the merchant-signed cart, evaluate the negotiation transcript, and return "
        "PASS, STEPUP, or REJECT. This is an authorization check only; it never creates or captures a payment."
    ),
    structured_output=True,
)
def warden_authorize_payment(request: AuthorizationRequest) -> AuthorizationResponse:
    """Run the same authorization service used by Warden's live API."""

    policies = {
        "quick_commerce": QUICK_COMMERCE_POLICY,
        "b2b_receivables": B2B_RECEIVABLES_POLICY,
    }
    intent = IntentMandate(**request.intent.model_dump())
    cart = CartMandate(**request.signed_cart.model_dump(exclude_none=True))
    canonical = CanonicalMandate(intent=intent, cart=cart)
    transcript = [turn.model_dump(exclude_none=True) for turn in request.transcript]
    result = evaluate_authorization(canonical, transcript, policies[request.policy_name])
    signals = result["signals"]
    return AuthorizationResponse(
        verdict=result["verdict"],
        explanation=result["explanation"],
        policy_name=request.policy_name,
        signature_valid=signals["signature_valid"],
        signals=signals,
        detectors=result["detectors"],
        trust_score_trajectory=result["trust_score_trajectory"],
        cart_total=signals["cart_total"],
        degraded=result["degraded"],
        detector_errors=signals["detector_errors"],
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
