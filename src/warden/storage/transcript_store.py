import json
import os

from .path_utils import atomic_json_dump, safe_json_path, validate_tx_id

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")


class TranscriptStore:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.join(DATA_DIR, "transcripts")
        os.makedirs(self.base_dir, exist_ok=True)

    def append_turn(self, tx_id: str, turn: dict):
        path = self._path(tx_id)
        turns = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                turns = json.load(f)
        turns.append(turn)
        atomic_json_dump(path, turns)

    def load(self, tx_id: str) -> list[dict]:
        path = self._path(tx_id)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def reset(self, tx_id: str):
        """Discard an orphaned partial transcript before retrying the same tx_id."""
        atomic_json_dump(self._path(tx_id), [])

    def exists(self, tx_id: str) -> bool:
        return os.path.exists(self._path(tx_id))

    def _path(self, tx_id: str) -> str:
        validate_tx_id(tx_id)
        return str(safe_json_path(self.base_dir, tx_id))
