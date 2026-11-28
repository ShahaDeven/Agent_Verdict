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


AGENT_NAMES = {"GenericAgent-gpt-4o-2024-11-20": "GPT-4o", "GenericAgent-anthropic_claude-3.7-sonnet": "Claude 3.7 Sonnet",
               "GenericAgent-Qwen_Qwen2.5-VL-72B-Instruct": "Qwen2.5-VL 72B",
               "GenericAgent-meta-llama_Llama-3.3-70B-Instruct": "Llama 3.3 70B"}


def best_of_attempts(variant: str = "v2-minimal-f4", split: str = "test", n_boot: int = 2000) -> dict:
    """AgentRewardBench: for each task with 2+ judged attempts (different agents), how often the chosen attempt
    truly succeeded, for the judge's pick vs always one agent vs random vs the ceiling. Cached data only ($0)."""
    from collections import defaultdict

    from ember_core.ember import REPO_ROOT

    from . import ember_cache
    from .arb_data import _split_key, load_runs
    from .ember_judge import judged_ok

    data = REPO_ROOT / "data" / "arb"
    runs, _ = load_runs(data)
    tasks: dict[tuple, list] = defaultdict(list)
    missing = 0
    for r in runs:
        if r.split != split:
            continue
        res = ember_cache.load(data / "cache" / "ember", variant, 0, r.key)
        if not judged_ok(res):
            missing += 1
            continue
        tasks[(r.benchmark, _split_key(r.task_id))].append((r.agent, res["verdict"], bool(r.success)))
    multi = {k: v for k, v in tasks.items() if len(v) >= 2}
    agents = sorted({a for v in multi.values() for a, _, _ in v})

    def fixed(agent, att):  # always this agent; if it didn't attempt the task, a random attempt
        own = [ok for a, _, ok in att if a == agent]
        return float(own[0]) if own else random_value([(0, ok) for _, _, ok in att])

    rows = []
    for (bench, _task), att in sorted(multi.items()):
        scored = [(trust(v), ok) for _, v, ok in att]
        rows.append({"bench": bench, "n": len(att), "judge": pick_value(scored), "random": random_value(scored),
                     "oracle": oracle_value(scored), **{a: fixed(a, att) for a in agents},
                     "judge_says_none": max(s for s, _ in scored) < 0, "none_ok": not any(ok for _, ok in scored)})

    def mean(key, rs=rows):
        return sum(r[key] for r in rs) / len(rs) if rs else None

    best = max(agents, key=mean)
    none = [r for r in rows if r["judge_says_none"]]
    by_bench = {b: {"tasks": len(rs), "judge": mean("judge", rs), "best_agent": mean(best, rs), "random": mean("random", rs),
                    "ceiling": mean("oracle", rs)}
                for b in sorted({r["bench"] for r in rows}) for rs in [[r for r in rows if r["bench"] == b]]}
    return {
        "variant": variant, "tasks": len(rows), "attempts": sum(r["n"] for r in rows), "single_attempt_tasks": len(tasks) - len(rows),
        "attempt_counts": {k: sum(r["n"] == k for r in rows) for k in (2, 3, 4)}, "runs_without_verdict": missing,
        "judge": mean("judge"), "random": mean("random"), "ceiling": mean("oracle"), "best_agent": AGENT_NAMES.get(best, best),
        "agents": {AGENT_NAMES.get(a, a): mean(a) for a in sorted(agents, key=lambda a: -mean(a))},
        "vs_best_agent": paired_mean_diff([r["judge"] for r in rows], [r[best] for r in rows], n_boot=n_boot),
        "vs_random": paired_mean_diff([r["judge"] for r in rows], [r["random"] for r in rows], n_boot=n_boot),
        "share_of_gain": (mean("judge") - mean("random")) / (mean("oracle") - mean("random")) if mean("oracle") > mean("random") else None,
        "judge_says_none": {"tasks": len(none), "right": sum(r["none_ok"] for r in none)},
        "by_benchmark": by_bench,
    }


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
