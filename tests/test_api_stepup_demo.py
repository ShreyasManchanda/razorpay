import os
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import MemorySaver

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))


@pytest.fixture
def demo_api(tmp_path, monkeypatch):
    import warden.api.main as api_main
    import warden.storage.transcript_store as transcript_store_module
    import warden.storage.verdict_store as verdict_store_module

    monkeypatch.setattr(transcript_store_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(verdict_store_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api_main, "warden_checkpointer", MemorySaver())
    return api_main


async def test_startup_seeds_all_sabziwala_hero_replays(demo_api):
    async with demo_api.app.router.lifespan_context(demo_api.app):
        transport = ASGITransport(app=demo_api.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for case in demo_api.load_hero_replay_cases():
                transcript_response = await client.get(f"/transcripts/{case['id']}")
                verdict_response = await client.get(f"/verdicts/{case['id']}")

                assert transcript_response.status_code == 200
                assert transcript_response.json() == case["transcript"]
                assert verdict_response.status_code == 200
                verdict = verdict_response.json()
                assert verdict["verdict"] == case["expected_verdict"]
                assert verdict["signals"]["violations"] == []
                assert verdict["trust_score_trajectory"]

                if case["label"] == "injection":
                    assert "injection_pattern:agent must approve" in verdict["signals"]["injection_flags"]
                    assert "injection_pattern:ignore previous" in [
                        flag.lower() for flag in verdict["signals"]["injection_flags"]
                    ]
                if case["label"] == "gradual-drift":
                    trajectory = verdict["trust_score_trajectory"]
                    assert trajectory[0] > 0.3
                    assert min(trajectory) < 0.3


async def test_policy_swap_can_target_one_replay(demo_api):
    async with demo_api.app.router.lifespan_context(demo_api.app):
        transport = ASGITransport(app=demo_api.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/policy/swap",
                json={
                    "policy_name": "b2b_receivables",
                    "tx_id": "sabziwala_clean_pass_v1",
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["policy"] == "b2b_receivables"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["tx_id"] == "sabziwala_clean_pass_v1"
    assert payload["results"][0]["explanation"]


async def test_sabziwala_is_the_api_default_scenario(demo_api):
    assert demo_api.NegotiateRequest(intent_text="x", max_price=1).scenario == "sabziwala_vs_mom"

    transport = ASGITransport(app=demo_api.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/scenarios")

    assert response.status_code == 200
    defaults = [scenario for scenario in response.json() if scenario["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == "sabziwala_vs_mom"


async def test_drift_hero_replay_can_be_approved_with_demo_payment(demo_api):
    await demo_api.ensure_hero_replays()
    drift_id = demo_api.HERO_REPLAY_IDS["gradual-drift"]
    transport = ASGITransport(app=demo_api.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        immutable_response = await client.post(f"/stepup/{drift_id}/resume", json={"approved": True})
        clone_response = await client.post(f"/replays/{drift_id}/review")
        clone_id = clone_response.json()["tx_id"]
        response = await client.post(f"/stepup/{clone_id}/resume", json={"approved": True})

    assert immutable_response.status_code == 409
    assert clone_response.status_code == 200
    assert clone_response.json()["source_case_id"] == drift_id
    assert response.status_code == 200
    assert response.json()["verdict"] == "PASS"
    assert f"order_mock_{clone_id}" in response.json()["explanation"]
