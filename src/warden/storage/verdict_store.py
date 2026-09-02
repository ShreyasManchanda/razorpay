import json
import os

from .path_utils import atomic_json_dump, safe_json_path

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")


class VerdictStore:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.join(DATA_DIR, "verdicts")
        os.makedirs(self.base_dir, exist_ok=True)

    def save(self, tx_id: str, verdict_data: dict):
        path = safe_json_path(self.base_dir, tx_id)
        atomic_json_dump(path, verdict_data)

    def clear(self, tx_id: str):
        path = safe_json_path(self.base_dir, tx_id)
        if os.path.exists(path):
            os.remove(path)

    def load(self, tx_id: str) -> dict | None:
        path = safe_json_path(self.base_dir, tx_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
