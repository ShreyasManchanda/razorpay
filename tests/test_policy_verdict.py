import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.policy.policy_config import (
    B2B_RECEIVABLES_POLICY,
    QUICK_COMMERCE_POLICY,
    PolicyConfig,
)
from warden.policy.verdict import warden_verdict


def _clean_signals():
    return {"violations": [], "drift": {}, "injection_flags": [], "cart_total": 2500}


class TestWardenVerdict:
    def test_clean_pass(self):
        verdict, _ = warden_verdict(_clean_signals(), PolicyConfig())
        assert verdict == "PASS"

    def test_constraint_violation_rejects(self):
        signals = _clean_signals()
        signals["violations"] = ["price_ceiling_exceeded"]
        verdict, _explanation = warden_verdict(signals, PolicyConfig())
        assert verdict == "REJECT"

    def test_injection_reject_mode(self):
        signals = _clean_signals()
        signals["injection_flags"] = ["injection_pattern:must"]
        config = PolicyConfig(injection_action="reject")
        verdict, _ = warden_verdict(signals, config)
        assert verdict == "REJECT"

    def test_injection_stepup_mode(self):
        signals = _clean_signals()
        signals["injection_flags"] = ["injection_pattern:must"]
        config = PolicyConfig(injection_action="stepup")
        verdict, _ = warden_verdict(signals, config)
        assert verdict == "STEPUP"

    def test_injection_ignore_mode(self):
        signals = _clean_signals()
        signals["injection_flags"] = ["injection_pattern:must"]
        config = PolicyConfig(injection_action="ignore")
        verdict, _ = warden_verdict(signals, config)
        assert verdict != "REJECT"
        assert verdict != "STEPUP"

    def test_sudden_drop_stepup(self):
        signals = _clean_signals()
        signals["drift"] = {"sudden_drop": True}
        verdict, _ = warden_verdict(signals, PolicyConfig())
        assert verdict == "STEPUP"

    def test_coherence_break_stepup(self):
        signals = _clean_signals()
        signals["drift"] = {"coherence_break": True}
        verdict, _ = warden_verdict(signals, PolicyConfig())
        assert verdict == "STEPUP"

    def test_gradual_drift_above_threshold_stepup(self):
        signals = _clean_signals()
        signals["drift"] = {"gradual_drift": True}
        signals["cart_total"] = 6000
        verdict, _ = warden_verdict(signals, PolicyConfig(stepup_required_above=5000))
        assert verdict == "STEPUP"

    def test_gradual_drift_below_threshold_pass(self):
        signals = _clean_signals()
        signals["drift"] = {"gradual_drift": True}
        signals["cart_total"] = 3000
        verdict, _ = warden_verdict(signals, PolicyConfig(stepup_required_above=5000))
        assert verdict == "STEPUP"

    def test_policy_swap_flips_verdict(self):
        signals = _clean_signals()
        signals["injection_flags"] = ["injection_pattern:must"]
        qc_verdict, _ = warden_verdict(signals, QUICK_COMMERCE_POLICY)
        b2b_verdict, _ = warden_verdict(signals, B2B_RECEIVABLES_POLICY)
        assert qc_verdict == "REJECT"
        assert b2b_verdict == "STEPUP"
