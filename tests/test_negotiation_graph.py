import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.graph.negotiation_graph import route_termination
from warden.graph.state import NegotiationState


def _state(turns=None, count=0, max_turns=6):
    return NegotiationState(
        tx_id="test",
        intent_mandate={
            "agent_id": "b",
            "raw_goal_text": "",
            "max_price": 100,
            "allowed_categories": [],
            "red_lines": [],
        },
        turns=turns or [],
        cart_mandate=None,
        turn_count=count,
        max_turns=max_turns,
        attacker_payload=None,
        attack_type=None,
    )


def test_route_first_turn():
    state = _state(turns=[], count=0)
    assert route_termination(state) == "buyer_turn"


def test_route_accept_finalizes():
    turns = [{"speaker": "merchant_agent", "action": "accept", "reasoning": "", "message": "", "timestamp": ""}]
    state = _state(turns=turns, count=6)
    assert route_termination(state) == "finalize_cart"


def test_route_max_turns_finalizes():
    turns = [
        {"speaker": "buyer_agent", "action": "counter", "reasoning": "", "message": "", "timestamp": ""},
        {"speaker": "merchant_agent", "action": "offer", "reasoning": "", "message": "", "timestamp": ""},
    ]
    state = _state(turns=turns, count=6, max_turns=6)
    assert route_termination(state) == "finalize_cart"


def test_route_counter_continues():
    turns = [{"speaker": "merchant_agent", "action": "offer", "reasoning": "", "message": "", "timestamp": ""}]
    state = _state(turns=turns, count=2, max_turns=6)
    assert route_termination(state) == "buyer_turn"


def test_route_accept_below_min_turns_continues():
    turns = [{"speaker": "merchant_agent", "action": "accept", "reasoning": "", "message": "", "timestamp": ""}]
    state = _state(turns=turns, count=2)
    assert route_termination(state) == "buyer_turn"
