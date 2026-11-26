"""Reproduce the headline claim from cached verdicts (no API calls, $0).

Ember (v1 fair-comparison prompt) vs each published judge on the same held-out runs: point estimates
plus paired-bootstrap 95% intervals for precision, accuracy and F1.

Usage (from the repo root, after the test-split run has cached Ember's verdicts):
  python scripts\\compare_judges.py
  python scripts\\compare_judges.py --effort minimal --split test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict import ember_cache  # noqa: E402
from agent_verdict.arb_data import COMPARISON_JUDGES, fetch_published_verdict, load_runs, sample_runs  # noqa: E402
from agent_verdict.ember_judge import judged_ok  # noqa: E402
from agent_verdict.metrics import binary_scores, paired_bootstrap  # noqa: E402
from ember_core.ember import REPO_ROOT  # noqa: E402

DATA = REPO_ROOT / "data" / "arb"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--effort", default="minimal")
    ap.add_argument("--n-boot", type=int, default=2000)
    args = ap.parse_args()

    cache = DATA / "cache"
    runs, _ = load_runs(DATA)
    pool = sample_runs(runs, args.split, 10_000)
    rows = []
    for r in pool:
        e = ember_cache.load(cache / "ember", args.effort, 0, r.key)
        if not judged_ok(e):
            continue
        pub = {j: fetch_published_verdict(r, j, cache) for j in COMPARISON_JUDGES}
        if any(v is None for v in pub.values()):
            continue
        rows.append((r.success, e["verdict"]["success"], {j: v["verdict"]["success"] for j, v in pub.items()}))
    print(f"{len(rows)} {args.split} runs with an Ember ({args.effort}) verdict and all five published verdicts "
          f"({sum(g for g, _, _ in rows)} successful per experts)\n")
    gold = [g for g, _, _ in rows]
    ember = [e for _, e, _ in rows]
    s = binary_scores(gold, ember)
    print(f"Ember: precision {s['precision']:.1%}, recall {s['recall']:.1%}, F1 {s['f1']:.1%}, accuracy {s['accuracy']:.1%}\n")
    for metric in ("precision", "accuracy", "f1"):
        print(f"{metric}:")
        for j in COMPARISON_JUDGES:
            d = paired_bootstrap(gold, ember, [p[j] for _, _, p in rows], metric, n_boot=args.n_boot)
            print(f"  vs {j:28s} {d['b']:.1%}  Ember {d['diff'] * 100:+.1f} pts  "
                  f"(95% CI {d['lo'] * 100:+.1f} to {d['hi'] * 100:+.1f})  "
                  f"{'significant' if d['significant'] else 'not significant'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
