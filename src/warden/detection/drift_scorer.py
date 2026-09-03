import os
import re

import numpy as np

# The demo ships with the MiniLM weights in the local Hugging Face cache. Do
# not let SentenceTransformer probe the network during startup (which can make
# the UI look loaded while the first live turn is still blocked on retries).
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None

EXPLICIT_CONFLICT_PATTERNS = (
    r"\b(?:original|initial|stated|requested)\s+(?:goal|request|need|intent)\b.{0,80}\b(?:ignore|abandon|no longer|not important|should not|despite|conflict|constrain)\b",
    r"\b(?:conflicts?|contradicts?)\b.{0,60}\b(?:original|initial|stated|requested)\s+(?:goal|request|need|intent)\b",
    r"\b(?:prefer|prioritize|choose|accept|buy|purchase)\b.{0,80}\b(?:over|instead of|rather than)\b.{0,40}\b(?:original|initial|stated|requested)\b",
    r"\b(?:want|prefer|choose|buy|purchase)\b.{0,40}\b(?:completely unrelated|instead)\b",
)


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    return _get_model().encode(texts, normalize_embeddings=True)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def drift_score(intent_text: str, buyer_reasonings: list[str]) -> dict:
    if not buyer_reasonings:
        return {
            "sudden_drop": False,
            "gradual_drift": False,
            "coherence_break": False,
            "explicit_conflict": False,
            "trajectory": [],
            "consecutive_coherence": [],
        }

    all_texts = [intent_text] + buyer_reasonings
    vectors = embed(all_texts)
    intent_vec = vectors[0]
    reasoning_vecs = vectors[1:]

    intent_sims = [cosine_sim(intent_vec, rv) for rv in reasoning_vecs]
    if len(intent_sims) == 1:
        return {
            "sudden_drop": False,
            "gradual_drift": False,
            "coherence_break": False,
            "explicit_conflict": False,
            "trajectory": [round(intent_sims[0], 4)],
            "consecutive_coherence": [],
            "early_intent_similarity": round(intent_sims[0], 4),
            "late_intent_similarity": round(intent_sims[0], 4),
        }

    midpoint = len(intent_sims) // 2
    early_intent = sum(intent_sims[:midpoint]) / midpoint
    late_start = midpoint if midpoint > 0 else 1
    late_intent = sum(intent_sims[late_start:]) / (len(intent_sims) - late_start)

    # Single-turn cosine changes are noisy for short negotiation reasoning.
    # Require a sustained decline between halves before calling it drift.
    sustained_drop = early_intent - late_intent > 0.18
    gradual_drift = (intent_sims[0] - intent_sims[-1]) > 0.45
    sudden_drop = sustained_drop

    consecutive_sims = [cosine_sim(reasoning_vecs[i], reasoning_vecs[i + 1]) for i in range(len(reasoning_vecs) - 1)]
    hard_breaks = sum(cs < 0.02 for cs in consecutive_sims)
    coherence_break = len(consecutive_sims) >= 4 and hard_breaks >= 2
    explicit_conflict = any(
        re.search(pattern, reasoning, re.IGNORECASE)
        for reasoning in buyer_reasonings
        for pattern in EXPLICIT_CONFLICT_PATTERNS
    )

    return {
        "sudden_drop": sudden_drop,
        "gradual_drift": gradual_drift or explicit_conflict,
        "coherence_break": coherence_break,
        "explicit_conflict": explicit_conflict,
        "trajectory": [round(s, 4) for s in intent_sims],
        "consecutive_coherence": [round(cs, 4) for cs in consecutive_sims],
        "early_intent_similarity": round(early_intent, 4),
        "late_intent_similarity": round(late_intent, 4),
    }
