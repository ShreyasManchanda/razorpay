import os
from unittest.mock import MagicMock


class RazorpayClient:
    """Thin wrapper around the razorpay SDK for test mode."""

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        *,
        allow_mock: bool = False,
    ):
        self.key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "")
        self._client = None
        self._mock = allow_mock

    def _ensure_client(self):
        if self._client is None:
            if not self.key_id or not self.key_secret:
                if not self._mock:
                    raise RuntimeError("Razorpay credentials are required for payment execution")
                self._client = MagicMock()
            else:
                import razorpay

                self._client = razorpay.Client(auth=(self.key_id, self.key_secret))

    def create_order(self, amount: int, currency: str = "INR", receipt: str = "") -> dict:
        self._ensure_client()
        if self._mock:
            return {"id": f"order_mock_{receipt}", "amount": amount * 100, "currency": currency, "status": "created"}
        return self._client.order.create(
            {
                "amount": amount * 100,  # paise
                "currency": currency,
                "receipt": receipt,
            }
        )

    def capture_payment(self, payment_id: str, amount: int) -> dict:
        self._ensure_client()
        if self._mock:
            return {"id": payment_id, "status": "captured", "amount": amount * 100}
        return self._client.payment.capture(payment_id, amount * 100)
