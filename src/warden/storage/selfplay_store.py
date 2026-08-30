import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")


class SelfplayStore:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.join(DATA_DIR, "selfplay_runs")
        os.makedirs(self.base_dir, exist_ok=True)

    def save_round(self, round_num: int, results: list[dict]):
        path = os.path.join(self.base_dir, f"round_{round_num}.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)

    def load_round(self, round_num: int) -> list[dict] | None:
        path = os.path.join(self.base_dir, f"round_{round_num}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)
