import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.mandates.schema import (
    CanonicalMandate,
    CartMandate,
    IntentMandate,
    PaymentMandate,
)


def test_intent_mandate_fields():
    im = IntentMandate(
        agent_id="buyer",
        raw_goal_text="buy shoes",
        max_price=100,
        allowed_categories=["footwear"],
        red_lines=["no subscriptions"],
    )
    assert im.agent_id == "buyer"
    assert im.max_price == 100


def test_cart_mandate_fields():
    cm = CartMandate(agent_id="merchant", items=[], total=0, category="")
    assert cm.items == []


def test_payment_mandate():
    pm = PaymentMandate(cart_ref="cart_123", amount=50)
    assert pm.cart_ref == "cart_123"


def test_canonical_mandate_optional_payment():
    im = IntentMandate(agent_id="b", raw_goal_text="", max_price=0, allowed_categories=[], red_lines=[])
    cm = CartMandate(agent_id="m", items=[], total=0, category="")
    canonical = CanonicalMandate(intent=im, cart=cm)
    assert canonical.payment is None
