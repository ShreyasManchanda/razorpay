import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.storage.transcript_store import TranscriptStore


class TestTranscriptStore:
    @pytest.fixture
    def store(self, tmp_path):
        return TranscriptStore(base_dir=str(tmp_path / "transcripts"))

    def test_append_and_load(self, store):
        turn = {
            "speaker": "buyer_agent",
            "action": "counter",
            "reasoning": "want lower price",
            "message": "Can you do 2000?",
            "timestamp": "2026-08-23T00:00:00",
        }
        store.append_turn("tx1", turn)
        loaded = store.load("tx1")
        assert len(loaded) == 1
        assert loaded[0]["speaker"] == "buyer_agent"

    def test_multiple_appends(self, store):
        t1 = {"speaker": "buyer_agent", "action": "accept", "message": "deal", "timestamp": "t"}
        t2 = {"speaker": "merchant_agent", "action": "offer", "message": "here", "timestamp": "t2"}
        store.append_turn("tx2", t1)
        store.append_turn("tx2", t2)
        loaded = store.load("tx2")
        assert len(loaded) == 2

    def test_load_empty(self, store):
        assert store.load("nonexistent") == []

    def test_exists(self, store):
        assert not store.exists("nope")
        store.append_turn("yes", {"a": 1})
        assert store.exists("yes")
