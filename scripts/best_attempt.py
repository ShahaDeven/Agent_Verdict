"""Does the judge make agents better? Pick the best of several attempts with Verdict v2 ($0, cached data).

AgentRewardBench ran 4 agents (GPT-4o, Claude 3.7 Sonnet, Qwen2.5-VL, Llama 3.3) on the same tasks. For every
test-split task with at least 2 judged attempts, compare how often the chosen attempt truly succeeded (expert
labels) when you take the attempt Verdict v2 trusts most, always use one agent (the best single agent, chosen
with hindsight on these same tasks: a generous baseline), pick at random, or know the answer (the ceiling).
Intervals are paired bootstrap over tasks. No API calls. The calculation lives in agent_verdict.selection.

Usage (from the repo root):  python scripts\\best_attempt.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict.selection import best_of_attempts  # noqa: E402
from ember_core.ember import REPO_ROOT  # noqa: E402


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v2-minimal-f4", help="cached judge to pick with")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()
    b = best_of_attempts(args.variant, n_boot=args.n_boot)

    c = b["attempt_counts"]
    md = [f"# Best of several attempts, picked by the judge ({b['variant']}, AgentRewardBench test split)", "",
          f"{b['tasks']} tasks with at least 2 judged attempts ({c[4]} with 4, {c[3]} with 3, {c[2]} with 2); "
          f"{b['single_attempt_tasks']} tasks had only one attempt and are left out; {b['runs_without_verdict']} runs had no usable verdict.", "",
          "| How the attempt is chosen | Tasks solved |", "| --- | ---: |",
          f"| **Judge's pick (Verdict v2 on Muse Ember)** | **{pct(b['judge'])}** |"]
    for name, v in b["agents"].items():
        md.append(f"| Always {name}{' (best single agent)' if name == b['best_agent'] else ''} | {pct(v)} |")
    md += [f"| Random attempt | {pct(b['random'])} |", f"| Ceiling (pick right whenever any attempt succeeded) | {pct(b['ceiling'])} |", ""]
    for label, d in ((f"the best single agent ({b['best_agent']})", b["vs_best_agent"]), ("a random attempt", b["vs_random"])):
        md.append(f"- Judge's pick vs {label}: {d['diff'] * 100:+.1f} points (95% CI {d['lo'] * 100:+.1f} to {d['hi'] * 100:+.1f})"
                  f"{' **significant**' if d['significant'] else ', not significant'}.")
    if b["share_of_gain"] is not None:
        md.append(f"- Of the possible gain from choosing well (random {pct(b['random'])} to ceiling {pct(b['ceiling'])}), "
                  f"the judge's pick captures {b['share_of_gain'] * 100:.0f}%.")
    n = b["judge_says_none"]
    if n["tasks"]:
        md.append(f"- On {n['tasks']} tasks the judge said every attempt failed; it was right on {n['right']} "
                  f"({pct(n['right'] / n['tasks'])}). Those are the tasks to send to a person or retry.")
    md.append(f"- The best single agent is chosen with hindsight on these same tasks, which flatters that baseline. "
              f"Judging every attempt costs about $0.0009 each, so ${0.0009 * b['attempts']:.2f} for all {b['attempts']} attempts here.")
    md += ["", "## By benchmark", "", "| Benchmark | Tasks | Judge's pick | Best single agent | Random | Ceiling |",
           "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, x in b["by_benchmark"].items():
        md.append(f"| {name} | {x['tasks']} | {pct(x['judge'])} | {pct(x['best_agent'])} | {pct(x['random'])} | {pct(x['ceiling'])} |")

    out = REPO_ROOT / "results" / f"best_attempt_{datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md) + f"\n\nWrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
