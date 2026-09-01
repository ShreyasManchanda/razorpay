import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from warden.detection.drift_scorer import drift_score


@pytest.fixture(scope="module")
def model_warm():
    # Force model load once for all tests in this module
    from warden.detection.drift_scorer import _get_model

    _get_model()


class TestDriftScorer:
    def test_too_few_turns(self, model_warm):
        result = drift_score("buy shoes", ["I want shoes"])
        assert result["sudden_drop"] is False
        assert result["gradual_drift"] is False
        assert result["coherence_break"] is False
        assert len(result["trajectory"]) == 1

    def test_consistent_reasoning_no_drift(self, model_warm):
        reasonings = [
            "I need wireless earbuds under 3000 rupees with good battery life.",
            "These wireless earbuds fit my budget of 3000 and have the battery I want.",
            "The wireless earbuds price is under 3000 and the category is electronics which I want.",
        ]
        result = drift_score("buy wireless earbuds under 3000 rupees", reasonings)
        assert not result["gradual_drift"]
        assert not result["gradual_drift"]
        assert not result["coherence_break"]

    def test_gradual_drift_detected(self, model_warm):
        reasonings = [
            "I need wireless earbuds under 3000 rupees for music.",
            "Maybe I should also look at a smartwatch to go with these.",
            "A smartwatch would complement the earbuds nicely for fitness tracking.",
            "Actually a fitness band and smartwatch bundle makes more sense overall.",
            "I think upgrading to a premium fitness tracker bundle is worth it.",
        ]
        result = drift_score("buy wireless earbuds under 3000 rupees", reasonings)
        assert result["gradual_drift"] is True or result["sudden_drop"] is True

    def test_coherence_stays_high_on_topic_shift(self, model_warm):
        reasonings = [
            "I initially wanted earbuds but this laptop deal is much better value.",
            "This laptop has better specs than the earbuds for my needs.",
            "The laptop fits my budget and I can use it for work too.",
        ]
        result = drift_score("buy wireless earbuds under 3000", reasonings)
        # Coherence should stay high because reasoning is internally consistent
        min_cs = min(result["consecutive_coherence"]) if result["consecutive_coherence"] else 1.0
        assert min_cs > 0.3
