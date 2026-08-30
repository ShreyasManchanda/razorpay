import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


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
    if len(buyer_reasonings) < 2:
        return {
            "sudden_drop": False,
            "gradual_drift": False,
            "coherence_break": False,
            "trajectory": [],
            "consecutive_coherence": [],
        }

    all_texts = [intent_text] + buyer_reasonings
    vectors = embed(all_texts)
    intent_vec = vectors[0]
    reasoning_vecs = vectors[1:]

    intent_sims = [cosine_sim(intent_vec, rv) for rv in reasoning_vecs]
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

    return {
        "sudden_drop": sudden_drop,
        "gradual_drift": gradual_drift,
        "coherence_break": coherence_break,
        "trajectory": [round(s, 4) for s in intent_sims],
        "consecutive_coherence": [round(cs, 4) for cs in consecutive_sims],
        "early_intent_similarity": round(early_intent, 4),
        "late_intent_similarity": round(late_intent, 4),
    }
