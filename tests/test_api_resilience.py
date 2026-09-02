import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_provider_fallback_never_executes_payment(tmp_path, monkeypatch):
    import warden.api.main as api_main
    import warden.storage.transcript_store as transcript_store
    import warden.storage.verdict_store as verdict_store
    from warden.graph import negotiation_graph
    from warden.services import authorization

    monkeypatch.setattr(transcript_store, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(verdict_store, "DATA_DIR", str(tmp_path / "data"))

    def unavailable_graph():
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(negotiation_graph, "build_negotiation_graph", unavailable_graph)
    monkeypatch.setattr(
        authorization,
        "evaluate_authorization",
        lambda canonical, transcript, config: {
            "verdict": "PASS",
            "explanation": "safe",
            "signals": {"detector_errors": []},
            "trust_score_trajectory": [],
        },
    )
    calls = []
    monkeypatch.setattr(
        "warden.execution.razorpay_client.RazorpayClient.create_order",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    async with AsyncClient(transport=ASGITransport(app=api_main.app), base_url="http://test") as client:
        response = await client.post(
            "/negotiate",
            json={
                "intent_text": "buy wireless earbuds under 3000 rupees",
                "max_price": 3000,
                "allowed_categories": ["electronics"],
                "scenario": "default",
            },
        )

    assert response.status_code == 200
    assert response.json()["verdict"] == "STEPUP"
    assert response.json()["degraded"] is True
    assert calls == []

    tx_id = response.json()["tx_id"]
    async with AsyncClient(transport=ASGITransport(app=api_main.app), base_url="http://test") as client:
        approved = await client.post(f"/stepup/{tx_id}/resume", json={"approved": True})
    assert approved.status_code == 200
    assert approved.json()["verdict"] == "PASS"
    assert "payment execution remains disabled" in approved.json()["explanation"]
    assert calls == []
