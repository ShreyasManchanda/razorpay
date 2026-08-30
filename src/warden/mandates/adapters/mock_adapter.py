MOCK_CATALOG = [
    {
        "name": "Wireless Earbuds Pro",
        "price": 2499,
        "category": "electronics",
        "description": "ANC earbuds, 30h battery",
    },
    {
        "name": "Bluetooth Speaker Mini",
        "price": 1799,
        "category": "electronics",
        "description": "Portable speaker, IPX7",
    },
    {
        "name": "Smart Watch Lite",
        "price": 2999,
        "category": "electronics",
        "description": "Fitness tracker, heart rate monitor",
    },
    {
        "name": "USB-C Fast Charger 65W",
        "price": 899,
        "category": "electronics",
        "description": "GaN charger, dual port",
    },
]


class MockAdapter:
    """Provides catalog data for the merchant agent without any external dependency."""

    def get_catalog(self) -> list[dict]:
        return MOCK_CATALOG.copy()

    def get_margin_policy(self) -> str:
        return (
            "Minimum margin is 15% above cost. "
            "Do not offer discounts below this. "
            "Upsell accessories when relevant but do not force them."
        )
