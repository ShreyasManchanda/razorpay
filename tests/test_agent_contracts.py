from typing import Literal

import pytest
from pydantic import BaseModel


class BuyerAction(BaseModel):
    action: Literal["accept", "counter", "reject"]


def test_buyer_action_rejects_unknown_variant():
    with pytest.raises(ValueError):
        BuyerAction(action="accept_offer")


def test_buyer_action_accepts_contract_variants():
    assert BuyerAction(action="accept").action == "accept"
    assert BuyerAction(action="counter").action == "counter"
    assert BuyerAction(action="reject").action == "reject"
