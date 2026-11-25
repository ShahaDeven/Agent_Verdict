"""Agreement between a judge and the expert labels.

AgentRewardBench treats "Successful" as the positive class. Precision answers "when the judge says
the agent succeeded, how often is it right?", which matters most when judges are used as rewards or
to report success rates. We report precision, recall, F1 and accuracy, and count unparsed answers
separately instead of silently treating them as a verdict.
"""

from __future__ import annotations

import random


def bootstrap_ci(gold: list[bool], pred: list[bool | None], metric: str, n_boot: int = 2000,
                 seed: int = 0, level: float = 0.95) -> tuple[float, float] | None:
    """Percentile bootstrap over runs for one metric from binary_scores (e.g. "accuracy", "f1").
    Resamples where the metric is undefined (e.g. no predicted positives) are skipped."""
    if not gold:
        return None
    rng = random.Random(seed)
    idx = range(len(gold))
    vals = []
    for _ in range(n_boot):
        pick = [rng.choice(idx) for _ in idx]
        v = binary_scores([gold[i] for i in pick], [pred[i] for i in pick])[metric]
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    lo = vals[int((1 - level) / 2 * (len(vals) - 1))]
    hi = vals[int((1 + level) / 2 * (len(vals) - 1))]
    return lo, hi


def binary_scores(gold: list[bool], pred: list[bool | None]) -> dict:
    pairs = [(g, p) for g, p in zip(gold, pred) if p is not None]
    tp = sum(g and p for g, p in pairs)
    fp = sum((not g) and p for g, p in pairs)
    fn = sum(g and (not p) for g, p in pairs)
    tn = sum((not g) and (not p) for g, p in pairs)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    acc = (tp + tn) / len(pairs) if pairs else None
    return {"n": len(pairs), "unparsed": len(pred) - len(pairs), "tp": tp, "fp": fp, "fn": fn,
            "tn": tn, "precision": prec, "recall": rec, "f1": f1, "accuracy": acc}
