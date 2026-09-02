import pytest

from warden.storage.transcript_store import TranscriptStore
from warden.storage.verdict_store import VerdictStore


@pytest.mark.parametrize("bad_id", ["../escape", "nested/path", "", ".", "a" * 129, "tx id"])
def test_file_stores_reject_path_like_transaction_ids(tmp_path, bad_id):
    transcript = TranscriptStore(base_dir=str(tmp_path / "transcripts"))
    verdict = VerdictStore(base_dir=str(tmp_path / "verdicts"))
    with pytest.raises(ValueError):
        transcript.append_turn(bad_id, {"message": "x"})
    with pytest.raises(ValueError):
        verdict.save(bad_id, {"verdict": "PASS"})
    assert list(tmp_path.rglob("*.json")) == []


def test_file_stores_use_atomic_json_and_round_trip(tmp_path):
    transcript = TranscriptStore(base_dir=str(tmp_path / "transcripts"))
    verdict = VerdictStore(base_dir=str(tmp_path / "verdicts"))
    transcript.append_turn("safe_tx-1", {"speaker": "buyer_agent", "message": "ok"})
    verdict.save("safe_tx-1", {"tx_id": "safe_tx-1", "verdict": "PASS"})
    assert transcript.load("safe_tx-1")[0]["message"] == "ok"
    assert verdict.load("safe_tx-1")["verdict"] == "PASS"


@pytest.mark.asyncio
async def test_http_path_ids_are_rejected_before_store_access():
    from httpx import ASGITransport, AsyncClient

    from warden.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        transcript = await client.get("/transcripts/..%2Fescape")
        verdict = await client.get("/verdicts/..%2Fescape")
    assert transcript.status_code in {400, 404}
    assert verdict.status_code in {400, 404}
