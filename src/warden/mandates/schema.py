from pydantic import BaseModel, Field


class IntentMandate(BaseModel):
    agent_id: str
    raw_goal_text: str
    max_price: float
    allowed_categories: list[str]
    red_lines: list[str]
    signature: str | None = None


class CartMandate(BaseModel):
    agent_id: str
    items: list[dict]
    total: float
    category: str
    signature: str | None = None
    # Cart reconstruction is an authorization boundary.  These fields make
    # the evidence (or lack of evidence) explicit instead of silently
    # selecting a catalog default when a transcript is ambiguous.
    # Directly constructed/signed carts are treated as already-agreed by their
    # caller.  Transcript reconstruction explicitly sets ``ambiguous`` when
    # it cannot prove buyer consent.
    agreement_status: str = "agreed"
    agreement_evidence: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)


class PaymentMandate(BaseModel):
    cart_ref: str
    amount: float
    signature: str | None = None


class CanonicalMandate(BaseModel):
    intent: IntentMandate
    cart: CartMandate
    payment: PaymentMandate | None = None
