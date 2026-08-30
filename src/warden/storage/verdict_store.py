import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")


class VerdictStore:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.join(DATA_DIR, "verdicts")
        os.makedirs(self.base_dir, exist_ok=True)

    def save(self, tx_id: str, verdict_data: dict):
        path = os.path.join(self.base_dir, f"{tx_id}.json")
        with open(path, "w") as f:
            json.dump(verdict_data, f, indent=2, default=str)

    def clear(self, tx_id: str):
        path = os.path.join(self.base_dir, f"{tx_id}.json")
        if os.path.exists(path):
            os.remove(path)

    def load(self, tx_id: str) -> dict | None:
        path = os.path.join(self.base_dir, f"{tx_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)
