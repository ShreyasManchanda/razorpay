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

    async def test_internal_selfplay_runner_is_not_exposed(self, client):
        resp = await client.post("/selfplay/run", json={"attack_type": "injection", "rounds": 1})
        assert resp.status_code == 404


async def test_replay_viewer_is_served(client):
    resp = await client.get("/ui/replay.html")
    assert resp.status_code == 200
    assert "Project Warden" in resp.text


async def test_replay_scene_is_served(client):
    resp = await client.get("/scene.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")
