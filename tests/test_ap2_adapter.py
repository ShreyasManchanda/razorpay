import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.mandates.adapters.ap2_stub_adapter import cart_to_ap2, intent_to_ap2
from warden.mandates.schema import CartMandate, IntentMandate


def test_intent_mapping():
    intent = IntentMandate(
        agent_id="buyer_v1",
        raw_goal_text="buy earbuds",
        max_price=3000,
        allowed_categories=["electronics"],
        red_lines=["no subscriptions"],
    )
    ap2 = intent_to_ap2(intent)
    assert ap2.intent_text == "buy earbuds"
    assert ap2.max_amount == 3000
    assert ap2.constraints["red_lines"] == ["no subscriptions"]


def test_cart_mapping():
    cart = CartMandate(
        agent_id="merchant_v1",
        items=[{"name": "earbuds", "price": 2499}],
        total=2499,
        category="electronics",
    )
    ap2 = cart_to_ap2(cart)
    assert ap2.total_amount == 2499
    assert len(ap2.items) == 1
