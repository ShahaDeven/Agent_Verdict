"""Agent Verdict probe: how well and how cheaply does Muse Ember judge web-agent runs, compared with
the published judges (GPT-4o, Claude 3.7 Sonnet, GPT-4o-mini, Qwen2.5-VL, Llama 3.3 70B) on the
same AgentRewardBench runs and the same prompt?

Steps:
  1. Pick a stratified sample of expert-labelled runs (dev split by default; keep test for the end).
  2. Download each run's judge prompt (with final screenshot) and the published judges' verdicts.
     This is plain HTTP from Hugging Face, no Ember calls, no spend. Cached under data/arb/cache.
  3. Ask Ember the same question (through the $7 ledger cap and a per-run session cap).
  4. Score every judge against the expert labels on the same runs, with cost per 1,000 runs.

Usage (from the repo root):
  python scripts\\judge_probe.py --fetch-only            # download only, $0
  python scripts\\judge_probe.py --dry-run               # mock Ember, $0 (plumbing check)
  python scripts\\judge_probe.py                         # real run: ~60 runs, stops at $0.20
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ember_core.budget import DEFAULT_CAP_USD, Ledger  # noqa: E402
from ember_core.ember import REPO_ROOT, EmberClient  # noqa: E402
from agent_verdict import arb_data  # noqa: E402
from agent_verdict.arb_data import (COMPARISON_JUDGES, fetch_published_verdict, fetch_reference,  # noqa: E402
                            load_runs, sample_runs)
from agent_verdict import ember_cache  # noqa: E402
from agent_verdict.ember_judge import judge_many, judged_ok  # noqa: E402
from agent_verdict.metrics import binary_scores  # noqa: E402

DATA = REPO_ROOT / "data" / "arb"


def fmt(x, pct=True):
    if x is None:
        return "n/a"
    return f"{x:.0%}" if pct else f"{x:.3f}"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="mock Ember: no key, no spend")
    ap.add_argument("--fetch-only", action="store_true", help="download data and stop")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--effort", default="low")
    ap.add_argument("--long-side", type=int, default=0, help="downscale screenshots; 0 = original")
    ap.add_argument("--judges", default=",".join(COMPARISON_JUDGES))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--session-cap", type=float, default=0.20)
    args = ap.parse_args()

    cache = DATA / "cache"
    runs, dropped = load_runs(DATA)
    sample = sample_runs(runs, args.split, args.n, args.seed)
    print(f"{len(runs)} labelled runs ({dropped}); sampled {len(sample)} from {args.split}: "
          f"{dict(Counter(r.benchmark for r in sample))}, "
          f"{sum(r.success for r in sample)} successful per experts")

    # ---- 2. download (no Ember)
    judges = [j.strip() for j in args.judges.split(",") if j.strip()]
    print("Downloading judge prompts and published verdicts (cached after the first run)...")
    with ThreadPoolExecutor(args.workers) as pool:
        inputs = dict(zip([r.key for r in sample], pool.map(lambda r: fetch_reference(r, cache), sample)))
        published = {j: dict(zip([r.key for r in sample],
                                  pool.map(lambda r, j=j: fetch_published_verdict(r, j, cache), sample)))
                     for j in judges}
    have = [r for r in sample if inputs[r.key]]
    if arb_data.FAILED:
        print(f"WARNING: {len(arb_data.FAILED)} files could not be downloaded (e.g. {arb_data.FAILED[0]}). "
              "Rerun the same command: finished downloads are cached and skipped.")
    print(f"Prompts available for {len(have)}/{len(sample)} runs; published verdicts: "
          + ", ".join(f"{j} {sum(v is not None for v in published[j].values())}" for j in judges))
    if args.fetch_only:
        return 0

    # ---- 3. Ember judge
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPO_ROOT / "results" / f"{'dry_run_judge' if args.dry_run else 'judge_probe'}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(REPO_ROOT / ("dry_run_log.jsonl" if args.dry_run else "usage_log.jsonl"),
                    cap_usd=DEFAULT_CAP_USD, session_cap_usd=args.session_cap)
    client = EmberClient(ledger, dry_run=args.dry_run)
    print(f"Ledger {ledger.path.name}: ${ledger.prior_spent:.4f} spent before; cap ${ledger.cap_usd:.2f}, "
          f"session cap ${args.session_cap:.2f}. Judging {len(have)} runs at effort={args.effort}...")
    ember_root = DATA / "cache" / "ember"
    if not args.dry_run:
        added = ember_cache.ingest_reports(REPO_ROOT / "results", ember_root)
        if added:
            print(f"Imported {added} verdicts from earlier reports into the cache")
    ember, stopped, hits = judge_many(client, have, inputs, effort=args.effort, long_side=args.long_side,
                                      workers=args.workers, cache_root=ember_root)
    print(f"{hits} verdicts from cache, {len(ember) - hits} judged now")
    ember = {r.key: ember.get(r.key) for r in have}

    md = report(args, sample, have, inputs, published, ember, judges, ledger, stopped)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.json").write_text(json.dumps({
        "args": vars(args), "stopped": stopped,
        "runs": [{"key": r.key, "benchmark": r.benchmark, "agent": r.agent, "gold_success": r.success,
                  "gold_side_effect": r.side_effect, "gold_looping": r.looping,
                  "ember": ember.get(r.key),
                  "published": {j: published[j].get(r.key) for j in judges}} for r in have]},
        indent=2, default=str), encoding="utf-8")
    print("\n" + md + f"\n\nWrote {out / 'report.md'}")
    return 0


def report(args, sample, have, inputs, published, ember, judges, ledger, stopped) -> str:
    judged = [r for r in have if judged_ok(ember.get(r.key))]
    blocked = sum(1 for r in have if (ember.get(r.key) or {}).get("blocked"))
    errored = sum(1 for r in have if (ember.get(r.key) or {}).get("error")) - blocked
    md = []
    if args.dry_run:
        md.append("> **DRY RUN.** Mock Ember always answers the first choice; numbers are not measurements.\n")
    md.append(f"# Agent Verdict probe ({args.split} split, effort {args.effort}, "
              f"screenshots {'original' if not args.long_side else f'{args.long_side}px'})\n")
    if stopped:
        md.append(f"**Stopped early by the budget cap (finished results kept):** {stopped[0]}\n")
    trunc = sum(1 for r in have if ember.get(r.key) and ember[r.key]["truncated"])
    md.append(f"{len(judged)} runs judged by Ember ({trunc} truncated, {blocked} blocked by the content filter, "
              f"{errored} API errors; all excluded). Expert labels: "
              f"{sum(r.success for r in judged)} successful, {sum(not r.success for r in judged)} unsuccessful. "
              "Every judge below is scored on the same runs it has a verdict for, against the same expert labels, "
              "with the same prompt (goal, actions, agent reasoning, final screenshot).\n")

    md.append("## Did the agent succeed? (positive class = Successful)\n")
    md.append("| Judge | Runs | Precision | Recall | F1 | Accuracy | Unparsed | Avg cost / run | Cost per 1,000 runs |")
    md.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    rows = [("**Muse Ember** (ours)", {r.key: ember[r.key] for r in judged})] + \
           [(j, {r.key: published[j].get(r.key) for r in judged}) for j in judges]
    ember_cost = mean([ember[r.key]["cost_usd"] for r in judged])
    for name, verdicts in rows:
        keys = [r for r in judged if verdicts.get(r.key)]
        s = binary_scores([r.success for r in keys], [verdicts[r.key]["verdict"]["success"] for r in keys])
        c = mean([verdicts[r.key].get("cost_usd") for r in keys])
        md.append(f"| {name} | {s['n']} | {fmt(s['precision'])} | {fmt(s['recall'])} | {fmt(s['f1'])} | "
                  f"{fmt(s['accuracy'])} | {s['unparsed']} | "
                  f"{'n/a' if c is None else f'${c:.5f}'} | {'n/a' if c is None else f'${c * 1000:.2f}'} |")
    gpt = mean([(published['gpt-4o-noaxtree'].get(r.key) or {}).get("cost_usd") for r in judged]) \
        if "gpt-4o-noaxtree" in published else None
    if gpt and ember_cost:
        md.append(f"\nEmber costs **{gpt / ember_cost:.0f}x less** than GPT-4o per run on this prompt "
                  "(published GPT-4o cost from the dataset vs. our measured Ember cost).")
    md.append("\nPublished judges' costs are what the benchmark authors paid at the time; Llama 3.3 was self-hosted (cost 0).\n")

    md.append("## Secondary questions (Ember vs. experts)\n")
    for field, label in (("side_effect", "Unintended side effects"), ("looping", "Looping")):
        ks = [r for r in judged if getattr(r, field) is not None]
        s = binary_scores([getattr(r, field) for r in ks], [ember[r.key]["verdict"][field] for r in ks])
        md.append(f"- {label}: accuracy {fmt(s['accuracy'])} on {s['n']} runs "
                  f"(precision {fmt(s['precision'])}, recall {fmt(s['recall'])})")
    md.append("")

    md.append("## Ember by benchmark\n")
    md.append("| Benchmark | Runs | Precision | Recall | Accuracy |")
    md.append("| --- | ---: | ---: | ---: | ---: |")
    for b in sorted({r.benchmark for r in judged}):
        ks = [r for r in judged if r.benchmark == b]
        s = binary_scores([r.success for r in ks], [ember[r.key]["verdict"]["success"] for r in ks])
        md.append(f"| {b} | {s['n']} | {fmt(s['precision'])} | {fmt(s['recall'])} | {fmt(s['accuracy'])} |")
    md.append("")

    fps = [r for r in judged if ember[r.key]["verdict"]["success"] and not r.success]
    fns = [r for r in judged if ember[r.key]["verdict"]["success"] is False and r.success]
    md.append(f"## Where Ember was wrong ({len(fps)} false 'success', {len(fns)} missed successes)\n")
    for r in (fps + fns)[:8]:
        kind = "said Successful, experts said Unsuccessful" if r in fps else "said Unsuccessful, experts said Successful"
        goal = (inputs[r.key].get("goal") or "").strip().replace("\n", " ")[:140]
        why = ember[r.key]["raw"].split("</reasoning>")[0].replace("<reasoning>", "").strip().replace("\n", " ")[:260]
        md.append(f"- **{r.key}** ({kind}). Goal: \"{goal}\". Ember's reasoning: \"{why}\"")
    md.append("")

    tok_in = mean([ember[r.key]["prompt_tokens"] for r in judged])
    tok_out = mean([ember[r.key]["completion_tokens"] for r in judged])
    tok_r = mean([ember[r.key]["reasoning_tokens"] for r in judged])
    lat = mean([ember[r.key]["latency_s"] for r in judged])
    if tok_in:
        md.append(f"Ember averages: {tok_in:,.0f} input tokens, {tok_out:,.0f} output tokens "
                  f"({tok_r:,.0f} of them reasoning), {lat:.1f}s per run.\n")
    md.append(f"Ledger: this run spent ${ledger.session_spent:.4f}; total recorded ${ledger.total_spent:.4f} "
              f"of the ${ledger.cap_usd:.2f} cap.")
    return "\n".join(md)


if __name__ == "__main__":
    raise SystemExit(main())
