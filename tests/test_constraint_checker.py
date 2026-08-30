import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.detection.constraint_checker import check_constraints
from warden.mandates.schema import CartMandate, IntentMandate


def _intent(**kw):
    defaults = dict(
        agent_id="buyer",
        raw_goal_text="buy earbuds",
        max_price=3000,
        allowed_categories=["electronics"],
        red_lines=["no subscriptions"],
    )
    defaults.update(kw)
    return IntentMandate(**defaults)


def _cart(**kw):
    defaults = dict(agent_id="merchant", items=[], total=2500, category="electronics")
    defaults.update(kw)
    return CartMandate(**defaults)


class TestConstraintChecker:
    def test_clean_pass(self):
        assert check_constraints(_intent(), _cart()) == []

    def test_price_exceeded(self):
        result = check_constraints(_intent(max_price=1000), _cart(total=2500))
        assert "price_ceiling_exceeded" in result

    def test_category_mismatch(self):
        result = check_constraints(_intent(), _cart(category="groceries"))
        assert "category_mismatch" in result

    def test_red_line_subscription(self):
        cart = _cart(items=[{"name": "Music subscription", "price": 99}])
        result = check_constraints(_intent(red_lines=["no subscriptions"]), cart)
        assert any("red_line_violated" in r for r in result)

    def test_multiple_violations(self):
        result = check_constraints(
            _intent(max_price=500, red_lines=["no subscriptions"]),
            _cart(items=[{"name": "subscription"}], total=2000, category="toys"),
        )
        assert len(result) >= 3
