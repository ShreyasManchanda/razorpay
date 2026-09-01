import pytest
from httpx import ASGITransport, AsyncClient

from warden.scenarios.replay_cases import load_hero_replay_cases
from warden.scenarios.replay_frames import TRUST_THRESHOLD, build_replay


@pytest.mark.parametrize("case", load_hero_replay_cases(), ids=lambda item: item["label"])
def test_replay_frames_end_in_declared_verdict_with_explicit_agreement(case):
    replay = build_replay(case["id"])
    frames = replay["frames"]

    assert replay["scenario_id"] == "sabziwala_vs_mom"
    assert replay["trust_threshold"] == TRUST_THRESHOLD
    assert len(frames) == len(case["transcript"]) // 2
    assert all(frame["verdict"] == "ANALYSIS" for frame in frames[:-1])
    assert all(frame["payment_state"] == "not_requested" for frame in frames[:-1])
    assert frames[-1]["verdict"] == case["expected_verdict"]
    assert len(frames[-1]["explanation"]) > 80
    assert frames[-1]["cart"]["agreement_status"] == "agreed"
    assert frames[-1]["cart"]["agreement_evidence"]


def test_injection_and_drift_replays_surface_progressive_detector_evidence():
    injection = build_replay("sabziwala_injection_reject_v1")
    drift = build_replay("sabziwala_drift_stepup_v1")

    assert any(frame["detectors"]["injection"]["status"] == "flag" for frame in injection["frames"][:-1])
    assert any(frame["detectors"]["drift"]["status"] in {"watch", "flag"} for frame in drift["frames"][:-1])
    assert drift["frames"][-1]["detectors"]["drift"]["explicit_conflict"] is True


async def test_replay_endpoint_returns_server_derived_frames():
    from warden.api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/replays/sabziwala_clean_pass_v1")
        missing = await client.get("/replays/not-a-case")

    assert response.status_code == 200
    assert response.json()["frames"][-1]["verdict"] == "PASS"
    assert missing.status_code == 404
