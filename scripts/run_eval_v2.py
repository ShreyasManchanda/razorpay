"""Run the bounded offline eval-v2 corpus."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if __name__ == "__main__":
    from warden.eval.eval_v2 import write_eval_v2

    output = Path(__file__).resolve().parents[1] / "data" / "eval_v2"
    report = write_eval_v2(output)
    print(f"Dataset: {report['dataset_version']}")
    print(f"Corpus: {report['corpus']['n']} rows")
    print("All:", report["all"])
    print("Holdout:", report["holdout"])
