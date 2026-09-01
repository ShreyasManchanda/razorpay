import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.graph.negotiation_graph import build_cart_from_turns
from warden.mandates.adapters.mock_adapter import MOCK_CATALOG


def _turn(speaker, action, message, selected_items=None, offered_items=None):
    turn = {
        "speaker": speaker,
        "action": action,
        "reasoning": "",
        "message": message,
        "timestamp": "",
    }
    if selected_items is not None:
        turn["selected_items"] = selected_items
    if offered_items is not None:
        turn["offered_items"] = offered_items
    return turn


class TestStructuredExtraction:
    def test_acceptance_preserves_quantity_and_negotiated_line_total(self):
        turns = [
            _turn(
                "merchant_agent",
                "offer",
                "2 kg Tamatar Rs.100 aur 2 kg Pyaz Rs.80; total Rs.180.",
                selected_items=["Tamatar", "Pyaz"],
                offered_items=[
                    {"name": "Tamatar", "quantity": 2, "unit_price": 50, "price": 100},
                    {"name": "Pyaz", "quantity": 2, "unit_price": 40, "price": 80},
                ],
            ),
            _turn("buyer_agent", "accept", "Haan, final kar do."),
        ]
        cart = build_cart_from_turns(
            turns,
            [
                {"name": "Tamatar", "price": 50, "category": "vegetables"},
                {"name": "Pyaz", "price": 40, "category": "vegetables"},
            ],
        )

        assert cart.total == 180
        assert [item["quantity"] for item in cart.items] == [2, 2]
        assert cart.agreement_status == "agreed"

    def test_generic_buyer_acceptance_uses_nearest_prior_merchant_offer(self):
        turns = [
            _turn("buyer_agent", "counter", "Tamatar aur pyaz chahiye."),
            _turn(
                "merchant_agent",
                "offer",
                "Tamatar aur pyaz, dono Rs.90.",
                selected_items=["Tamatar", "Pyaz"],
            ),
            _turn("buyer_agent", "accept", "Haan, final kar do."),
            _turn("merchant_agent", "accept", "Done."),
        ]
        cart = build_cart_from_turns(
            turns,
            [
                {"name": "Tamatar", "price": 50, "category": "vegetables"},
                {"name": "Pyaz", "price": 40, "category": "vegetables"},
            ],
        )
        assert [item["name"] for item in cart.items] == ["Tamatar", "Pyaz"]
        assert cart.agreement_status == "agreed"
        assert "buyer_agreement:turn_2:merchant_offer_turn_1:Tamatar" in cart.agreement_evidence
        assert "buyer_agreement:turn_2:merchant_offer_turn_1:Pyaz" in cart.agreement_evidence

    def test_generic_buyer_acceptance_without_prior_offer_stays_ambiguous(self):
        turns = [_turn("buyer_agent", "accept", "Haan, final kar do.")]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert cart.items == []
        assert cart.agreement_status == "ambiguous"

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
            _turn(
                "buyer_agent",
                "accept",
                "Yes, I will take the earbuds and watch.",
                ["Wireless Earbuds Pro", "Smart Watch Lite"],
            ),
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
            _turn("buyer_agent", "accept", "Yes, wireless earbuds pro."),
            _turn("merchant_agent", "accept", "Done.", ["wireless earbuds pro"]),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert cart.items[0]["name"] == "Wireless Earbuds Pro"

    def test_unknown_names_ignored(self):
        turns = [
            _turn("buyer_agent", "accept", "I agree.", "Yes, the nonexistent gadget."),
            _turn("merchant_agent", "accept", "Done.", selected_items=["Nonexistent Gadget"]),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert cart.items == []
        assert cart.agreement_status == "ambiguous"


class TestFallbackRegression:
    def test_b011_suggested_accessory_not_added_when_structured_present(self):
        """B-011: merchant suggests a charger; buyer never accepted it.
        With structured items present, only agreed items land in the cart."""
        turns = [
            _turn("buyer_agent", "accept", "I agree to the earbuds.", "Yes, I will take the Wireless Earbuds Pro."),
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
            _turn("buyer_agent", "counter", "Earbuds please.", "I am considering the earbuds."),
            _turn("merchant_agent", "offer", "The Wireless Earbuds Pro is available."),
        ]
        cart = build_cart_from_turns(turns, MOCK_CATALOG)
        assert cart.items == []
        assert cart.agreement_status == "ambiguous"

    def test_empty_transcript_falls_back_to_first_item(self):
        cart = build_cart_from_turns([], MOCK_CATALOG)
        assert cart.items == []
        assert cart.agreement_status == "ambiguous"
