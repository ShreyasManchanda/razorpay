import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.execution.razorpay_client import RazorpayClient


class TestRazorpayClient:
    def test_create_order_mock_mode(self):
        client = RazorpayClient(key_id="", key_secret="", allow_mock=True)
        result = client.create_order(amount=2500, receipt="test_tx")
        assert result["id"].startswith("order_mock_")
        assert result["amount"] == 250000  # paise
        assert result["currency"] == "INR"

    def test_capture_payment_mock_mode(self):
        client = RazorpayClient(key_id="", key_secret="", allow_mock=True)
        result = client.capture_payment("pay_test123", 2500)
        assert result["status"] == "captured"

    def test_no_credentials_falls_back_to_mock(self):
        client = RazorpayClient(allow_mock=True)
        result = client.create_order(amount=100, receipt="x")
        assert "order_mock_" in result.get("id", "")


def test_no_credentials_requires_explicit_mock():
    client = RazorpayClient(key_id="", key_secret="")
    with pytest.raises(RuntimeError, match="Razorpay credentials"):
        client.create_order(amount=100, receipt="guarded")
