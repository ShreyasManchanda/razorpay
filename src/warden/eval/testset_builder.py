import json
import os

EVAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "eval")


class TestSetBuilder:
    def __init__(self):
        os.makedirs(EVAL_DIR, exist_ok=True)

    def save_entry(self, entry: dict):
        path = os.path.join(EVAL_DIR, "testset.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def load_all(self) -> list[dict]:
        path = os.path.join(EVAL_DIR, "testset.jsonl")
        if not os.path.exists(path):
            return []
        entries = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
