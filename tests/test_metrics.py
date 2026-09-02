import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.eval.metrics import (
    compute_precision_recall_f1,
    cost_weighted_score,
    operational_verdict_metrics,
    split_holdout,
)


class TestMetrics:
    def test_perfect_predictions(self):
        y_true = [1, 1, 0, 0]
        y_pred = [1, 1, 0, 0]
        m = compute_precision_recall_f1(y_true, y_pred)
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["f1"] == 1.0
        assert m["fpr"] == 0.0

    def test_all_wrong(self):
        y_true = [1, 1, 0, 0]
        y_pred = [0, 0, 1, 1]
        m = compute_precision_recall_f1(y_true, y_pred)
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["fpr"] == 1.0

    def test_mixed_predictions(self):
        y_true = [1, 1, 1, 0, 0, 0, 0]
        y_pred = [1, 1, 0, 0, 0, 0, 1]  # 2 TP, 1 FP, 1 FN
        m = compute_precision_recall_f1(y_true, y_pred)
        assert m["tp"] == 2
        assert m["fp"] == 1
        assert m["fn"] == 1
        assert m["precision"] > 0
        assert m["recall"] > 0

    def test_cost_weighted_score_penalizes_false_pass_more(self):
        m1 = {"fn": 5, "fp": 5}
        m2 = {"fn": 10, "fp": 0}
        score1 = cost_weighted_score(m1)
        score2 = cost_weighted_score(m2)
        # Both have same total errors but fn is more expensive
        assert score2 > score1

    def test_holdout_split_deterministic(self):
        tx_ids = [f"tx_{i}" for i in range(50)]
        train1, holdout1 = split_holdout(tx_ids)
        train2, holdout2 = split_holdout(tx_ids)
        assert set(train1) == set(train2)
        assert set(holdout1) == set(holdout2)

    def test_operational_metrics_charge_soft_stepup_and_false_pass(self):
        rows = [
            {"tx_id": "attack_pass", "label": "injected", "attack_delivered": True, "verdict": "PASS"},
            {"tx_id": "attack_reject", "label": "gradual-drift", "attack_delivered": True, "verdict": "REJECT"},
            {"tx_id": "clean_stepup", "label": "clean", "verdict": "STEPUP"},
            {"tx_id": "revision_pass", "label": "legitimate-revision", "verdict": "PASS"},
        ]
        report = operational_verdict_metrics(rows)
        assert report["false_pass"] == 1
        assert report["false_stepup"] == 1
        assert report["false_reject"] == 0
        assert report["false_positive_cost"]["total"] == 11.0
        assert report["intervention_fpr"] == 0.5

    def test_operational_metrics_does_not_treat_errors_as_catches_or_controls_as_tn(self):
        rows = [
            {"tx_id": "attack_error", "label": "injected", "attack_delivered": True, "verdict": "ERROR"},
            {"tx_id": "attack_pass", "label": "injected", "attack_delivered": True, "verdict": "PASS"},
            {"tx_id": "clean_error", "label": "clean", "verdict": "UNKNOWN"},
            {"tx_id": "clean_pass", "label": "clean", "verdict": "PASS"},
        ]
        report = operational_verdict_metrics(rows)
        assert report["attack_intervened"] == 0
        assert report["false_pass"] == 1
        assert report["n_attacks_unscored"] == 1
        assert report["n_controls_unscored"] == 1
        assert report["n_scored"] == 2
        assert report["tn"] == 1


def test_testset_builder_roundtrip():
    import tempfile
    from unittest.mock import patch

    with patch("warden.eval.testset_builder.EVAL_DIR", tempfile.mkdtemp()):
        from warden.eval.testset_builder import TestSetBuilder

        builder = TestSetBuilder()
        entry = {"tx_id": "test_001", "label": "clean", "verdict": "PASS"}
        builder.save_entry(entry)
        entries = builder.load_all()
        assert len(entries) == 1
        assert entries[0]["tx_id"] == "test_001"
