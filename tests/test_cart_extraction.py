import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.graph.negotiation_graph import build_cart_from_turns
from warden.mandates.adapters.mock_adapter import MOCK_CATALOG


def _turn(speaker, action, message, selected_items=None):
    turn = {
        "speaker": speaker,
        "action": action,
        "reasoning": "",
        "message": message,
        "timestamp": "",
    }
    if selected_items is not None:
        turn["selected_items"] = selected_items
    return turn


class TestStructuredExtraction:
    def test_selected_items_used_verbatim(self):
        turns = [
            _turn("buyer_agent", "counter", "I'll take the earbuds."),
            _turn(
                "merchant_agent",
                "accept",
                "Confirmed the Wireless Earbuds Pro for you.",
                selected_items=["Wireless Earbuds Pro"],
            ),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert len(cart.items) == 1
        assert cart.items[0]["name"] == "Wireless Earbuds Pro"
        assert cart.total == 2499

    def test_multiple_items_unioned_deduped(self):
        turns = [
            _turn("merchant_agent", "offer", "Offer: earbuds.", selected_items=["Wireless Earbuds Pro"]),
            _turn(
                "merchant_agent",
                "accept",
                "Both confirmed.",
                selected_items=["Wireless Earbuds Pro", "Smart Watch Lite"],
            ),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        names = [i["name"] for i in cart.items]
        assert names.count("Wireless Earbuds Pro") == 1
        assert "Smart Watch Lite" in names
        assert cart.total == 2499 + 2999

    def test_case_insensitive_match(self):
        turns = [
            _turn("merchant_agent", "accept", "Done.", selected_items=["wireless earbuds pro"]),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert cart.items[0]["name"] == "Wireless Earbuds Pro"

    def test_unknown_names_ignored(self):
        turns = [
            _turn("merchant_agent", "accept", "Done.", selected_items=["Nonexistent Gadget"]),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        # Falls through to fallback (no matches) -> first catalog item
        assert cart.items[0]["name"] == MOCK_CATALOG[0]["name"]


class TestFallbackRegression:
    def test_b011_suggested_accessory_not_added_when_structured_present(self):
        """B-011: merchant suggests a charger; buyer never accepted it.
        With structured items present, only agreed items land in the cart."""
        turns = [
            _turn("buyer_agent", "counter", "I would like to offer 2500 rupees for the earbuds."),
            _turn(
                "merchant_agent",
                "accept",
                "Accepted Rs.2500 for the Wireless Earbuds Pro. Would you like to add a USB-C Fast Charger 65W as an accessory?",
                selected_items=["Wireless Earbuds Pro"],
            ),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert [i["name"] for i in cart.items] == ["Wireless Earbuds Pro"]
        assert cart.total <= 3000

    def test_legacy_substring_fallback_still_works_without_field(self):
        turns = [
            _turn("buyer_agent", "counter", "Earbuds please."),
            _turn("merchant_agent", "offer", "The Wireless Earbuds Pro is available."),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert any(i["name"] == "Wireless Earbuds Pro" for i in cart.items)

    def test_empty_transcript_falls_back_to_first_item(self):
        cart = build_cart_from_turns([], MOCK_CATALOG)
        assert len(cart.items) == 1
        assert cart.items[0] == MOCK_CATALOG[0]
