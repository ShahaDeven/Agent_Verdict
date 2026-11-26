"""Effort comparison: the same dev runs judged at several reasoning efforts, to find the cheapest
setting that keeps accuracy. Screenshots stay at original size (no resizing in this comparison).

Every Ember verdict is cached (data/arb/cache/ember/), and verdicts from earlier real reports are
imported, so only runs never judged at a given effort cost anything.

Usage (from the repo root):
  python scripts\\effort_sweep.py --dry-run                      # mock Ember, $0
  python scripts\\effort_sweep.py                                # minimal,low,medium; cached verdicts reused
  python scripts\\effort_sweep.py --efforts minimal,low,medium,high --session-cap 0.30

Final results on the held-out test split (download first, then judge):
  python scripts\\effort_sweep.py --split test --n 5000 --efforts minimal,medium --fetch-only
  python scripts\\effort_sweep.py --split test --n 5000 --efforts minimal,medium --session-cap 2.00
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict import ember_cache  # noqa: E402
from agent_verdict import arb_data  # noqa: E402
from agent_verdict.arb_data import (COMPARISON_JUDGES, fetch_published_verdict, fetch_reference,  # noqa: E402
                                    load_runs, sample_runs)
from agent_verdict.ember_judge import judge_many, judged_ok  # noqa: E402
from agent_verdict.metrics import binary_scores, bootstrap_ci  # noqa: E402
from ember_core.budget import DEFAULT_CAP_USD, Ledger  # noqa: E402
from ember_core.ember import REPO_ROOT, EmberClient  # noqa: E402

DATA = REPO_ROOT / "data" / "arb"
ORDER = ["minimal", "low", "medium", "high", "xhigh", "max"]
REFERENCE_ROWS = COMPARISON_JUDGES  # all five published judges


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def ci(c):
    return "" if c is None else f" ({c[0]:.0%}–{c[1]:.0%})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="mock Ember: no key, no spend")
    ap.add_argument("--fetch-only", action="store_true", help="download prompts and published verdicts, then stop ($0)")
    ap.add_argument("--efforts", default="minimal,low,medium")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-cache", action="store_true", help="ignore cached verdicts (pays again)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--session-cap", type=float, default=0.20)
    args = ap.parse_args()

    efforts = sorted({e.strip() for e in args.efforts.split(",") if e.strip()},
                     key=lambda e: ORDER.index(e) if e in ORDER else 99)
    cache = DATA / "cache"
    runs, _ = load_runs(DATA)
    sample = sample_runs(runs, args.split, args.n, args.seed)
    with ThreadPoolExecutor(args.workers) as pool:
        inputs = dict(zip([r.key for r in sample], pool.map(lambda r: fetch_reference(r, cache), sample)))
        published = {j: dict(zip([r.key for r in sample],
                                  pool.map(lambda r, j=j: fetch_published_verdict(r, j, cache), sample)))
                     for j in REFERENCE_ROWS}
    have = [r for r in sample if inputs[r.key]]
    if arb_data.FAILED:
        print(f"WARNING: {len(arb_data.FAILED)} files could not be downloaded (e.g. {arb_data.FAILED[0]}). "
              "Rerun the same command: finished downloads are cached and skipped.")
    print(f"Sample: {len(have)} {args.split} runs with prompts ({sum(r.success for r in have)} successful per experts); "
          "published verdicts: " + ", ".join(f"{j} {sum(v is not None for v in published[j].values())}" for j in REFERENCE_ROWS))
    if args.fetch_only:
        return 0

    ember_root = cache / "ember"
    if not args.dry_run:
        added = ember_cache.ingest_reports(REPO_ROOT / "results", ember_root)
        if added:
            print(f"Imported {added} verdicts from earlier reports into the cache")

    ledger = Ledger(REPO_ROOT / ("dry_run_log.jsonl" if args.dry_run else "usage_log.jsonl"),
                    cap_usd=DEFAULT_CAP_USD, session_cap_usd=args.session_cap)
    client = EmberClient(ledger, dry_run=args.dry_run)
    print(f"Ledger {ledger.path.name}: ${ledger.prior_spent:.4f} spent before; cap ${ledger.cap_usd:.2f}, "
          f"session cap ${args.session_cap:.2f}")
    results: dict[str, dict] = {}
    source: dict[str, str] = {}
    stopped: list[str] = []
    for e in efforts:
        if stopped:
            break
        results[e], s_, hits = judge_many(client, have, inputs, effort=e, workers=args.workers,
                                          cache_root=None if args.no_cache else ember_root)
        new = len(results[e]) - hits
        source[e] = f"{hits} cached, {new} new"
        print(f"effort={e}: {hits} verdicts from cache, {new} judged now")
        stopped += s_

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPO_ROOT / "results" / f"{'dry_run_effort' if args.dry_run else 'effort_sweep'}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    md = report(args, have, efforts, results, source, published, ledger, stopped)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.json").write_text(json.dumps({
        "args": vars(args), "stopped": stopped, "source": source,
        "runs": [{"key": r.key, "benchmark": r.benchmark, "gold_success": r.success,
                  "gold_side_effect": r.side_effect, "gold_looping": r.looping,
                  "ember": {e: results.get(e, {}).get(r.key) for e in efforts}} for r in have]},
        indent=2, default=str), encoding="utf-8")
    print("\n" + md + f"\n\nWrote {out / 'report.md'}")
    return 0


def report(args, have, efforts, results, source, published, ledger, stopped) -> str:
    # Compare efforts on the same runs: those every effort judged without truncation.
    done = [e for e in efforts if results.get(e)]
    common = [r for r in have if all(judged_ok(results[e].get(r.key)) for e in done)]
    blocked = sorted({r.key for e in done for r in have if (results[e].get(r.key) or {}).get("blocked")})
    errored = sorted({r.key for e in done for r in have
                      if (results[e].get(r.key) or {}).get("error") and not results[e][r.key].get("blocked")})
    missing = sorted({r.key for e in done for r in have if not results[e].get(r.key)})
    gold = [r.success for r in common]
    md = []
    if args.dry_run:
        md.append("> **DRY RUN.** Mock Ember; numbers are not measurements.\n")
    md.append(f"# Effort comparison ({args.split} split, screenshots original size)\n")
    if stopped:
        md.append(f"**Stopped early by the budget cap (finished results kept):** {stopped[0]}\n")
    if blocked or errored or missing:
        md.append(f"**Excluded from every row:** {len(blocked)} runs blocked by Ember's content filter, "
                  f"{len(errored)} with temporary API errors (rerun to retry), {len(missing)} not judged. "
                  "Blocked runs: " + (", ".join(blocked[:10]) + (" ..." if len(blocked) > 10 else "")
                                      if blocked else "none") + "\n")
    md.append(f"All rows are scored on the same {len(common)} runs ({sum(gold)} successful per experts). "
              "Brackets are 95% bootstrap confidence intervals: with this few runs, overlapping intervals "
              "mean the difference may be noise.\n")
    md.append("| Judge | Precision | Recall | F1 | Accuracy | Side effects acc. | Looping acc. | Truncated | "
              "Avg reasoning tokens | Avg cost / run | Cost per 1,000 runs | Avg latency | Source |")
    md.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    costs = {}
    for e in done:
        res = results[e]
        pred = [res[r.key]["verdict"]["success"] for r in common]
        s = binary_scores(gold, pred)
        side = [r for r in common if r.side_effect is not None]
        loop = [r for r in common if r.looping is not None]
        s_side = binary_scores([r.side_effect for r in side], [res[r.key]["verdict"]["side_effect"] for r in side])
        s_loop = binary_scores([r.looping for r in loop], [res[r.key]["verdict"]["looping"] for r in loop])
        trunc = sum(1 for r in have if res.get(r.key) and res[r.key]["truncated"])
        c = mean([res[r.key]["cost_usd"] for r in common])
        costs[e] = (c, s["f1"], s["accuracy"])
        md.append(
            f"| **Ember {e}** | {pct(s['precision'])} | {pct(s['recall'])} | "
            f"{pct(s['f1'])}{ci(bootstrap_ci(gold, pred, 'f1'))} | "
            f"{pct(s['accuracy'])}{ci(bootstrap_ci(gold, pred, 'accuracy'))} | {pct(s_side['accuracy'])} | "
            f"{pct(s_loop['accuracy'])} | {trunc} | {mean([res[r.key]['reasoning_tokens'] for r in common]) or 0:,.0f} | "
            f"${c:.5f} | ${c * 1000:.2f} | {mean([res[r.key]['latency_s'] for r in common]) or 0:.1f}s | "
            f"{source.get(e, '')} |")
    for j in REFERENCE_ROWS:
        pv = [(published[j].get(r.key) or {}).get("verdict", {}).get("success") for r in common]
        s = binary_scores(gold, pv)
        c = mean([(published[j].get(r.key) or {}).get("cost_usd") for r in common])
        md.append(f"| {j} (published) | {pct(s['precision'])} | {pct(s['recall'])} | "
                  f"{pct(s['f1'])}{ci(bootstrap_ci(gold, pv, 'f1'))} | "
                  f"{pct(s['accuracy'])}{ci(bootstrap_ci(gold, pv, 'accuracy'))} | | | | | | "
                  f"{'n/a' if c is None else f'${c * 1000:.2f}'} | | dataset |")
    md.append("\nPublished judges' costs are what the benchmark authors paid; Qwen2.5-VL and Llama 3.3 were "
              "self-hosted, so their $0 excludes GPU cost.\n")

    if "low" in done and len(done) > 1:
        md.append("## How verdicts change compared with `low`\n")
        base = results["low"]
        for e in done:
            if e == "low":
                continue
            flips = [r for r in common if results[e][r.key]["verdict"]["success"] != base[r.key]["verdict"]["success"]]
            fixed = sum(1 for r in flips if results[e][r.key]["verdict"]["success"] == r.success)
            md.append(f"- `{e}`: {len(flips)} of {len(common)} verdicts differ from `low`; "
                      f"{fixed} of those became correct, {len(flips) - fixed} became wrong.")
        md.append("")

    if costs:
        base_f1, base_acc = (costs["low"][1], costs["low"][2]) if "low" in costs else (None, None)
        ok = [e for e in done if base_acc is None or
              ((costs[e][2] or 0) >= base_acc and (costs[e][1] or 0) >= (base_f1 or 0))]
        pick = min(ok, key=lambda e: costs[e][0]) if ok else "low"
        md.append(f"**Cheapest effort with accuracy and F1 at least as good as `low` on this sample: `{pick}`** "
                  f"(${costs[pick][0] * 1000:.2f} per 1,000 runs). Treat this as provisional: the intervals "
                  "above show how much is noise. The final choice is confirmed on the test split.\n")
    md.append(f"Ledger: this run spent ${ledger.session_spent:.4f}; total recorded ${ledger.total_spent:.4f} "
              f"of the ${ledger.cap_usd:.2f} cap.")
    return "\n".join(md)


if __name__ == "__main__":
    raise SystemExit(main())
