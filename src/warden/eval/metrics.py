def compute_precision_recall_f1(y_true: list[int], y_pred: list[int]) -> dict:
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr": round(fpr, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def cost_weighted_score(metrics: dict, false_pass_cost: float = 10.0, false_reject_cost: float = 1.0) -> float:
    """Lower is better."""
    return metrics["fn"] * false_pass_cost + metrics["fp"] * false_reject_cost


def split_holdout(tx_ids: list[str], holdout_modulo: int = 5) -> tuple[list[str], list[str]]:
    train, holdout = [], []
    for tx_id in tx_ids:
        import hashlib

        digest = int(hashlib.sha256(tx_id.encode()).hexdigest(), 16)
        if digest % holdout_modulo == 0:
            holdout.append(tx_id)
        else:
            train.append(tx_id)
    return train, holdout
