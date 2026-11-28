"""Does the judge make agents better? Pick the best of several attempts with Verdict v2 ($0, cached data).

AgentRewardBench ran 4 agents (GPT-4o, Claude 3.7 Sonnet, Qwen2.5-VL, Llama 3.3) on the same tasks. For every
test-split task with at least 2 judged attempts, compare how often the chosen attempt truly succeeded (expert
labels) when you:
  - take the attempt Verdict v2 trusts most (judge's pick),
  - always use one agent (the best single agent, chosen with hindsight on these same tasks: a generous baseline),
  - pick an attempt at random,
  - or know the answer (ceiling: any attempt succeeded).
Intervals are paired bootstrap over tasks. No API calls.

Usage (from the repo root):  python scripts\\best_attempt.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict import ember_cache  # noqa: E402
from agent_verdict.arb_data import _split_key, load_runs  # noqa: E402
from agent_verdict.ember_judge import judged_ok  # noqa: E402
from agent_verdict.selection import oracle_value, paired_mean_diff, pick_value, random_value, trust  # noqa: E402
from ember_core.ember import REPO_ROOT  # noqa: E402

DATA = REPO_ROOT / "data" / "arb"
AGENT_NAMES = {"GenericAgent-gpt-4o-2024-11-20": "GPT-4o", "GenericAgent-anthropic_claude-3.7-sonnet": "Claude 3.7 Sonnet",
               "GenericAgent-Qwen_Qwen2.5-VL-72B-Instruct": "Qwen2.5-VL 72B", "GenericAgent-meta-llama_Llama-3.3-70B-Instruct": "Llama 3.3 70B"}


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v2-minimal-f4", help="cached judge to pick with")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()

    cache = DATA / "cache" / "ember"
    runs, _ = load_runs(DATA)
    tasks: dict[tuple, list] = defaultdict(list)   # (benchmark, task) -> [(agent, verdict, truly succeeded)]
    missing = 0
    for r in runs:
        if r.split != "test":
            continue
        res = ember_cache.load(cache, args.variant, 0, r.key)
        if not judged_ok(res):
            missing += 1
            continue
        tasks[(r.benchmark, _split_key(r.task_id))].append((r.agent, res["verdict"], bool(r.success)))
    multi = {k: v for k, v in tasks.items() if len(v) >= 2}

    agents = sorted({a for v in multi.values() for a, _, _ in v})

    def fixed(agent: str, attempts) -> float:  # always use this agent; if it didn't attempt the task, a random one
        own = [ok for a, _, ok in attempts if a == agent]
        return float(own[0]) if own else random_value([(0, ok) for _, _, ok in attempts])

    rows = []
    for (bench, task), att in sorted(multi.items()):
        scored = [(trust(v), ok) for _, v, ok in att]
        rows.append({"bench": bench, "n": len(att), "judge": pick_value(scored), "random": random_value(scored),
                     "oracle": oracle_value(scored), **{a: fixed(a, att) for a in agents},
                     "judge_says_none": max(s for s, _ in scored) < 0, "none_ok": not any(ok for _, ok in scored)})
    n = len(rows)
    mean = lambda key, rs=rows: sum(r[key] for r in rs) / len(rs)  # noqa: E731
    best_agent = max(agents, key=lambda a: mean(a))

    md = [f"# Best of several attempts, picked by the judge ({args.variant}, AgentRewardBench test split)", "",
          f"{n} tasks with at least 2 judged attempts ({sum(r['n'] == 4 for r in rows)} with 4, "
          f"{sum(r['n'] == 3 for r in rows)} with 3, {sum(r['n'] == 2 for r in rows)} with 2); "
          f"{len(tasks) - n} tasks had only one attempt and are left out; {missing} runs had no usable verdict.", "",
          "| How the attempt is chosen | Tasks solved |", "| --- | ---: |",
          f"| **Judge's pick (Verdict v2 on Muse Ember)** | **{pct(mean('judge'))}** |"]
    for a in sorted(agents, key=lambda a: -mean(a)):
        md.append(f"| Always {AGENT_NAMES.get(a, a)}{' (best single agent)' if a == best_agent else ''} | {pct(mean(a))} |")
    md += [f"| Random attempt | {pct(mean('random'))} |", f"| Ceiling (pick right whenever any attempt succeeded) | {pct(mean('oracle'))} |", ""]

    for label, other in ((f"the best single agent ({AGENT_NAMES.get(best_agent, best_agent)})", best_agent), ("a random attempt", "random")):
        d = paired_mean_diff([r["judge"] for r in rows], [r[other] for r in rows], n_boot=args.n_boot)
        md.append(f"- Judge's pick vs {label}: {d['diff'] * 100:+.1f} points (95% CI {d['lo'] * 100:+.1f} to {d['hi'] * 100:+.1f})"
                  f"{' **significant**' if d['significant'] else ', not significant'}.")
    gap = mean("oracle") - mean("random")
    if gap > 0:
        md.append(f"- Of the possible gain from choosing well (random {pct(mean('random'))} to ceiling {pct(mean('oracle'))}), "
                  f"the judge's pick captures {100 * (mean('judge') - mean('random')) / gap:.0f}%.")
    none = [r for r in rows if r["judge_says_none"]]
    if none:
        md.append(f"- On {len(none)} tasks the judge said every attempt failed; it was right on "
                  f"{sum(r['none_ok'] for r in none)} ({pct(sum(r['none_ok'] for r in none) / len(none))}). "
                  "Those are the tasks to send to a person or retry.")
    md.append(f"- The best single agent is chosen with hindsight on these same tasks, which flatters that baseline. "
              f"Judging every attempt costs about $0.0009 each, so ${0.0009 * sum(r['n'] for r in rows):.2f} for all "
              f"{sum(r['n'] for r in rows)} attempts here.")

    md += ["", "## By benchmark", "", "| Benchmark | Tasks | Judge's pick | Best single agent | Random | Ceiling |",
           "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for b in sorted({r["bench"] for r in rows}):
        rs = [r for r in rows if r["bench"] == b]
        md.append(f"| {b} | {len(rs)} | {pct(mean('judge', rs))} | {pct(mean(best_agent, rs))} | {pct(mean('random', rs))} | "
                  f"{pct(mean('oracle', rs))} |")

    out = REPO_ROOT / "results" / f"best_attempt_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md) + f"\n\nWrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
