import os
import sys
from typing import ClassVar

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.keys import AGENT_REGISTRY, generate_keypair, get_public_key
from warden.mandates.schema import CartMandate, IntentMandate
from warden.mandates.signing import sign_mandate, verify_mandate


@pytest.fixture(autouse=True)
def setup_keys():
    AGENT_REGISTRY.clear()
    TestSigning._private_keys.clear()


class TestKeyGeneration:
    def test_generate_produces_valid_keys(self):
        priv, pub = generate_keypair("test_agent")
        assert len(priv) == 64
        assert len(pub) == 64

    def test_registry_contains_agent(self):
        generate_keypair("test_agent")
        assert "test_agent" in AGENT_REGISTRY

    def test_get_public_key(self):
        _, pub = generate_keypair("lookup_agent")
        assert get_public_key("lookup_agent") == pub


class TestSigning:
    _private_keys: ClassVar[dict[str, str]] = {}

    @pytest.fixture(autouse=True)
    def setup_private(self):
        for agent_id in ["buyer_agent_v1", "merchant_agent_v1"]:
            priv, _pub = generate_keypair(agent_id)
            self._private_keys[agent_id] = priv

    def _make_intent(self):
        return IntentMandate(
            agent_id="buyer_agent_v1",
            raw_goal_text="buy wireless earbuds under 3000",
            max_price=3000,
            allowed_categories=["electronics"],
            red_lines=["no subscriptions"],
        )

    def _make_cart(self):
        return CartMandate(
            agent_id="merchant_agent_v1",
            items=[{"name": "earbuds", "price": 2500}],
            total=2500,
            category="electronics",
        )

    def test_sign_and_verify_intent_roundtrip(self):
        intent = self._make_intent()
        signed = sign_mandate(intent, self._private_keys["buyer_agent_v1"])
        assert signed.signature is not None
        assert verify_mandate(signed) is True

    def test_sign_and_verify_cart_roundtrip(self):
        cart = self._make_cart()
        signed = sign_mandate(cart, self._private_keys["merchant_agent_v1"])
        assert signed.signature is not None
        assert verify_mandate(signed) is True

    def test_wrong_key_fails_verification(self):
        intent = self._make_intent()
        signed = sign_mandate(intent, self._private_keys["merchant_agent_v1"])
        assert verify_mandate(signed) is False

    def test_tampered_payload_fails_verification(self):
        intent = self._make_intent()
        signed = sign_mandate(intent, self._private_keys["buyer_agent_v1"])
        signed.raw_goal_text = "buy laptop under 99999"
        assert verify_mandate(signed) is False

    def test_no_signature_fails_verification(self):
        intent = self._make_intent()
        assert verify_mandate(intent) is False

    def test_tampered_price_fails_verification(self):
        cart = self._make_cart()
        signed = sign_mandate(cart, self._private_keys["merchant_agent_v1"])
        cart.total = 999999
        assert verify_mandate(signed) is False
