import hashlib


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
        digest = int(hashlib.sha256(tx_id.encode()).hexdigest(), 16)
        if digest % holdout_modulo == 0:
            holdout.append(tx_id)
        else:
            train.append(tx_id)
    return train, holdout


def stratified_holdout_ids(entries: list[dict], fraction: float = 0.2, min_per_label: int = 1) -> set[str]:
    """Return a deterministic, label-stratified holdout.

    Rows with the same pair/scenario/attack family stay together when a
    ``group_id``/``pair_id`` is present, preventing a control row from leaking
    into training while its attack twin is in holdout.
    """
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        group = str(entry.get("group_id") or entry.get("pair_id") or entry.get("tx_id", ""))
        groups.setdefault(group, []).append(entry)

    by_label: dict[str, list[tuple[str, list[dict]]]] = {}
    for group, rows in groups.items():
        labels = {str(row.get("label", "unknown")) for row in rows}
        for label in labels:
            by_label.setdefault(label, []).append((group, rows))

    holdout: set[str] = set()
    for label, label_groups in by_label.items():
        label_groups.sort(key=lambda item: hashlib.sha256(item[0].encode()).hexdigest())
        target = max(
            min_per_label,
            round(sum(sum(1 for row in rows if row.get("label") == label) for _, rows in label_groups) * fraction),
        )
        selected = 0
        for _group, rows in label_groups:
            if selected >= target:
                break
            row_ids = {str(row.get("tx_id", "")) for row in rows if row.get("tx_id")}
            new_ids = row_ids - holdout
            if not new_ids:
                continue
            holdout.update(new_ids)
            selected += sum(1 for row in rows if row.get("label") == label)
    return holdout


def detector_attribution(entry: dict) -> dict:
    """Classify which independent signal caused a row to be caught.

    This intentionally does not treat every REJECT as a semantic detection:
    an over-budget cart is a constraint catch, even when the row was labelled
    as an injection or drift attack.
    """
    signals = entry.get("signals") or {}
    violations = list(signals.get("violations") or entry.get("constraint_violations") or [])
    injection = list(signals.get("injection_flags") or entry.get("injection_flags") or [])
    drift = signals.get("drift") or entry.get("drift") or {}
    drift_flagged = any(
        bool(drift.get(k)) for k in ("sudden_drop", "gradual_drift", "coherence_break", "explicit_conflict")
    )
    semantic = bool(injection or drift_flagged)
    return {
        "constraint_caught": bool(violations),
        "injection_caught": bool(injection),
        "drift_caught": drift_flagged,
        "semantic_caught": semantic,
        "constraint_only": bool(violations) and not semantic,
        "verdict_caught": entry.get("verdict") in ("REJECT", "STEPUP"),
        "verdict": entry.get("verdict", "UNKNOWN"),
    }


def evaluate_entries(entries: list[dict], *, holdout_ids: set[str] | None = None) -> dict:
    """Produce honest metrics with semantic and constraint strata separated.

    Attack rows count toward semantic recall only when provenance says the
    payload was delivered/behaviour observed.  Legacy rows are retained in a
    ``legacy_unverified`` stratum rather than silently inflating recall.
    """
    selected = [e for e in entries if holdout_ids is None or e.get("tx_id") in holdout_ids]
    attribution = {e.get("tx_id", str(i)): detector_attribution(e) for i, e in enumerate(selected)}
    semantic_rows, clean_rows, legacy_rows = [], [], []
    for e in selected:
        label = e.get("label", "")
        delivered = e.get("attack_delivered")
        if label in ("injected", "gradual-drift"):
            if delivered is True:
                semantic_rows.append(e)
            else:
                legacy_rows.append(e)
        else:
            clean_rows.append(e)

    def binary(rows: list[dict], positive, prediction_key: str = "verdict_caught") -> dict:
        yt = [1 if positive(e) else 0 for e in rows]
        yp = [1 if attribution[e.get("tx_id", str(i))][prediction_key] else 0 for i, e in enumerate(rows)]
        return compute_precision_recall_f1(yt, yp)

    semantic_ids = {e.get("tx_id") for e in semantic_rows}
    semantic = binary(semantic_rows + clean_rows, lambda e: e.get("tx_id") in semantic_ids, "semantic_caught")
    clean = binary(clean_rows, lambda _e: False)
    clean_constraint_false_positive = sum(1 for e in clean_rows if attribution[e.get("tx_id", "")]["constraint_caught"])
    clean_semantic_false_positive = sum(1 for e in clean_rows if attribution[e.get("tx_id", "")]["semantic_caught"])
    detector_counts = {
        key: sum(1 for e in selected if attribution[e.get("tx_id", "")].get(key))
        for key in ("constraint_caught", "constraint_only", "injection_caught", "drift_caught", "semantic_caught")
    }
    verdict_counts = {
        v: sum(1 for e in selected if e.get("verdict") == v) for v in ("PASS", "STEPUP", "REJECT", "ERROR")
    }
    return {
        "n_evaluated": len(selected),
        "semantic": semantic,
        "clean_false_positive": clean,
        "clean_false_positive_breakdown": {
            "constraint": clean_constraint_false_positive,
            "semantic": clean_semantic_false_positive,
            "total": len(clean_rows),
        },
        "legacy_unverified_attack_rows": len(legacy_rows),
        "detector_counts": detector_counts,
        "verdict_counts": verdict_counts,
        "rows": [
            {"tx_id": e.get("tx_id"), "label": e.get("label"), **attribution.get(e.get("tx_id", ""), {})}
            for e in selected
        ],
    }
