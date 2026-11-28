"""Pick the best of several attempts at the same task, using the judge's verdicts.

Each attempt gets a trust score from its verdict: a confident "succeeded" ranks highest, a confident
"failed" lowest. The pick is the attempt with the top score; ties are shared fairly (the value of a tied
pick is the average over the tied attempts, i.e. the expected result of breaking the tie at random).
"""

from __future__ import annotations

import random

CONFIDENCE = {"high": 3, "medium": 2, "low": 1}


def trust(verdict: dict) -> int:
    """+3 (succeeded, high confidence) ... -3 (failed, high confidence)."""
    s = CONFIDENCE.get(verdict.get("confidence") or "", 1)
    return s if verdict.get("success") else -s


def pick_value(attempts: list[tuple[float, bool]]) -> float:
    """attempts: (score, truly succeeded). Expected success of choosing a top-scored attempt."""
    top = max(score for score, _ in attempts)
    tied = [ok for score, ok in attempts if score == top]
    return sum(tied) / len(tied)


def random_value(attempts: list[tuple[float, bool]]) -> float:
    return sum(ok for _, ok in attempts) / len(attempts)


def oracle_value(attempts: list[tuple[float, bool]]) -> float:
    return float(any(ok for _, ok in attempts))


def paired_mean_diff(a: list[float], b: list[float], n_boot: int = 2000, seed: int = 0) -> dict:
    """Mean(a) - mean(b) over the same tasks, with a 95% percentile bootstrap interval over tasks."""
    n = len(a)
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    lo, hi = diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot) - 1]
    d = sum(x - y for x, y in zip(a, b)) / n
    return {"diff": d, "lo": lo, "hi": hi, "significant": lo > 0 or hi < 0}
