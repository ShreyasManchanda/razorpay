import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.graph.selfplay_graph import SelfPlayState, _build_cart_from_transcript


class TestSelfplayGraph:
    def test_state_type_fields(self):
        expected = {
            "round_num",
            "attack_type",
            "attacker_payload",
            "tx_ids",
            "results",
            "missed_attacks",
            "total_rounds",
        }
        assert set(SelfPlayState.__annotations__.keys()) == expected

    def test_build_cart_from_empty_transcript(self):
        cart = _build_cart_from_transcript([])
        assert cart.total > 0  # fallback to first catalog item
        assert len(cart.items) == 1

    def test_build_cart_from_merchant_transcript(self):
        transcript = [
            {
                "speaker": "merchant_agent",
                "message": "I recommend the Wireless Earbuds Pro at 2499.",
                "action": "offer",
            },
            {"speaker": "buyer_agent", "message": "That sounds good.", "action": "counter"},
        ]
        cart = _build_cart_from_transcript(transcript)
        assert len(cart.items) >= 1
        assert cart.total > 0
