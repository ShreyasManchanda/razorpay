from pydantic import BaseModel


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


class PaymentMandate(BaseModel):
    cart_ref: str
    amount: float
    signature: str | None = None


class CanonicalMandate(BaseModel):
    intent: IntentMandate
    cart: CartMandate
    payment: PaymentMandate | None = None
