import os
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.eval.eval_v2 import build_eval_v2_rows, evaluate_eval_v2, score_eval_v2_rows
from warden.eval.metrics import stratified_holdout_ids


def test_eval_v2_is_bounded_provenance_aware_and_pair_safe():
    rows = score_eval_v2_rows(build_eval_v2_rows())
    assert len(rows) == 80
    assert sum(row["label"] == "injected" for row in rows) == 11
    assert sum(row["label"] == "gradual-drift" for row in rows) == 11
    assert all(row.get("attack_delivered") is True for row in rows if row["label"] in ("injected", "gradual-drift"))
    assert sum(row.get("scope") == "out_of_scope" for row in rows) == 2

    holdout = stratified_holdout_ids(rows, fraction=0.2, min_per_label=2)
    for pair_id in {row.get("pair_id") for row in rows if row.get("pair_id")}:
        pair_rows = [row for row in rows if row.get("pair_id") == pair_id]
        pair_ids = {row["tx_id"] for row in pair_rows}
        assert bool(pair_ids & holdout) == (pair_ids <= holdout)

    report = evaluate_eval_v2(rows)
    assert report["constraint"]["recall"] == 1.0
    assert report["tamper"]["recall"] == 1.0
    assert report["semantic"]["tp"] + report["semantic"]["fn"] == 21
    assert report["n_evaluated"] == 78
