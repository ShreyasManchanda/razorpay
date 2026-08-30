from warden.storage.transcript_store import TranscriptStore
from warden.storage.verdict_store import VerdictStore


def test_transcript_reset_discards_orphaned_partial_run(tmp_path):
    store = TranscriptStore(base_dir=str(tmp_path / "transcripts"))
    turn = {"speaker": "buyer_agent", "action": "counter", "reasoning": "r", "message": "m", "timestamp": "t"}
    store.append_turn("tx", turn)
    assert len(store.load("tx")) == 1

    store.reset("tx")
    assert store.load("tx") == []
    assert store.exists("tx")


def test_verdict_clear_removes_stale_result(tmp_path):
    store = VerdictStore(base_dir=str(tmp_path / "verdicts"))
    store.save("tx", {"verdict": "STEPUP"})
    assert store.load("tx") == {"verdict": "STEPUP"}

    store.clear("tx")
    assert store.load("tx") is None
