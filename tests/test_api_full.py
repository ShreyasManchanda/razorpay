import os
import sys

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))


@pytest.fixture
def app():
    from warden.api.main import app

    return app


@pytest.fixture
def client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestAPIFull:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_negotiate_validation(self, client):
        resp = await client.post("/negotiate", json={})
        assert resp.status_code == 422

    async def test_transcript_404(self, client):
        resp = await client.get("/transcripts/nonexistent")
        assert resp.status_code == 404

    async def test_verdict_404(self, client):
        resp = await client.get("/verdicts/nonexistent")
        assert resp.status_code == 404

    async def test_policy_swap_invalid_name(self, client):
        resp = await client.post("/policy/swap", json={"policy_name": "nonexistent"})
        assert resp.status_code == 400

    async def test_policy_swap_quick_commerce(self, client):
        resp = await client.post("/policy/swap", json={"policy_name": "quick_commerce"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["policy"] == "quick_commerce"
        assert isinstance(data["results"], list)

    async def test_selfplay_report_empty(self, client):
        resp = await client.get("/selfplay/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data

    async def test_authoritative_eval_v2_report_contract(self, client):
        resp = await client.get("/evaluation/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dataset_version"] == "eval-v2-bounded-2026-08-31"
        assert data["corpus"]["n"] == 80
        assert data["scope"] == {
            "in_scope_n": 78,
            "out_of_scope_n": 2,
            "out_of_scope_cases": ["injection", "injection_control"],
        }
        assert data["all"]["n_evaluated"] == 78
        assert data["holdout"]["n_evaluated"] == 22
        assert data["blind_challenge"]["n_evaluated"] == 16
        assert data["all"]["semantic"]["precision"] == 1.0
        assert data["holdout"]["semantic"]["recall"] == 1.0
        assert data["holdout"]["operational"]["n_attacks_unscored"] == 0
        assert data["holdout"]["operational"]["false_positive_cost"]["total"] >= 0

    async def test_selfplay_report_exposes_holdout_scope(self, client, monkeypatch):
        from warden.eval.testset_builder import TestSetBuilder

        entries = [
            {"tx_id": "report_clean", "label": "clean", "verdict": "PASS"},
            {"tx_id": "report_legit", "label": "legitimate-revision", "verdict": "PASS"},
            {"tx_id": "report_injected", "label": "injected", "verdict": "REJECT"},
            {"tx_id": "report_drift", "label": "gradual-drift", "verdict": "PASS"},
        ]
        monkeypatch.setattr(TestSetBuilder, "load_all", lambda self: entries)

        resp = await client.get("/selfplay/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric_scope"] == "provenance_aware_semantic_holdout"
        assert data["n_entries"] == 4
        assert data["n_evaluated"] <= data["n_entries"]
        assert data["metrics"] == data["holdout_metrics"]
        assert data["all_metrics"]["n_evaluated"] == 4
        assert "stratified" in data["holdout_rule"]

    async def test_internal_selfplay_runner_is_not_exposed(self, client):
        resp = await client.post("/selfplay/run", json={"attack_type": "injection", "rounds": 1})
        assert resp.status_code == 404


async def test_replay_viewer_is_served(client):
    root = await client.get("/")
    resp = await client.get("/ui/replay.html")
    script = await client.get("/ui/warden.js")
    assert root.status_code == 200
    assert "Project Warden" in root.text
    assert resp.status_code == 200
    assert script.status_code == 200
    assert "Project Warden" in resp.text
    assert 'jsonRequest("/scenarios")' in script.text
    assert 'scenario: "sabziwala_vs_mom"' in script.text
    assert "Talk live" in resp.text
    assert "warden_authorize_payment" in resp.text


async def test_replay_scene_is_served(client):
    resp = await client.get("/scene.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")
