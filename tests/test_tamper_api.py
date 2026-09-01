import pytest
from httpx import ASGITransport, AsyncClient

from warden.api.main import app


@pytest.mark.asyncio
async def test_tamper_check_rejects_before_detection_or_payment():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/tamper/check")

    assert response.status_code == 200
    body = response.json()
    assert body["original_signature_valid"] is True
    assert body["tampered_signature_valid"] is False
    assert body["detectors_ran"] is False
    assert body["payment_created"] is False
    assert body["verdict"] == "REJECT"
