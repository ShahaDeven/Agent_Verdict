"""Verdict v2 evaluation: our own judge vs the fair-comparison judge (v1, the benchmark prompt) on the
same runs, against the same expert labels.

v2 sees the goal, every step, and several screenshots (FINAL plus states just before it), and returns
a JSON verdict with failure type, evidence, confidence and a needs-a-person flag. v1's verdicts are
read from the cache (no new spend for the baseline).

Usage (from the repo root):
  python scripts\\verdict_v2_eval.py --fetch-only     # download screenshots only ($0)
  python scripts\\verdict_v2_eval.py --dry-run        # mock Ember ($0)
  python scripts\\verdict_v2_eval.py                  # 60 dev runs, stops itself at $0.25
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

from agent_verdict import arb_data, ember_cache  # noqa: E402
from agent_verdict.arb_data import fetch_reference, fetch_step_screenshot, load_runs, sample_runs  # noqa: E402
from agent_verdict.ember_judge import judge_many, judged_ok  # noqa: E402
from agent_verdict.metrics import binary_scores, bootstrap_ci, paired_bootstrap  # noqa: E402
from agent_verdict.trace import from_arb_messages  # noqa: E402
from agent_verdict.verdict_v2 import judge_v2, needs_person, select_states  # noqa: E402
from ember_core.budget import DEFAULT_CAP_USD, Ledger  # noqa: E402
from ember_core.ember import REPO_ROOT, EmberClient  # noqa: E402

DATA = REPO_ROOT / "data" / "arb"


def pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def ci(c):
    return "" if c is None else f" ({c[0]:.0%}–{c[1]:.0%})"


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fetch-only", action="store_true", help="download screenshots, then stop ($0)")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--effort", default="minimal")
    ap.add_argument("--frames", type=int, default=4, help="screenshots per run, including FINAL")
    ap.add_argument("--baseline", default="minimal", help="v1 effort to compare against (from cache)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--session-cap", type=float, default=0.25)
    args = ap.parse_args()

    cache = DATA / "cache"
    runs, _ = load_runs(DATA)
    sample = sample_runs(runs, args.split, args.n, args.seed)
    with ThreadPoolExecutor(args.workers) as pool:
        inputs = dict(zip([r.key for r in sample], pool.map(lambda r: fetch_reference(r, cache), sample)))
    have = [r for r in sample if inputs[r.key]]
    traces = {r.key: from_arb_messages(inputs[r.key]["messages"]) for r in have}

    # screenshots: FINAL comes with the prompt; the others are downloaded once and cached
    def shots_for(r):
        t = traces[r.key]
        out = {}
        for i in select_states(t.n_states, args.frames):
            url = t.final_screenshot if i == t.n_states - 1 else fetch_step_screenshot(r, i, cache)
            if url:
                out[i] = url
        return r.key, out

    print(f"Preparing {len(have)} {args.split} runs with up to {args.frames} screenshots each "
          "(first time downloads from Hugging Face; cached after)...")
    with ThreadPoolExecutor(args.workers) as pool:
        shots = dict(pool.map(shots_for, have))
    got = Counter(len(v) for v in shots.values())
    print(f"Screenshots per run: {dict(sorted(got.items()))}")
    if arb_data.FAILED:
        print(f"WARNING: {len(arb_data.FAILED)} downloads failed (rerun to retry; finished ones are cached).")
    if args.fetch_only:
        return 0

    ledger = Ledger(REPO_ROOT / ("dry_run_log.jsonl" if args.dry_run else "usage_log.jsonl"),
                    cap_usd=DEFAULT_CAP_USD, session_cap_usd=args.session_cap)
    client = EmberClient(ledger, dry_run=args.dry_run)
    print(f"Ledger {ledger.path.name}: ${ledger.prior_spent:.4f} spent before; cap ${ledger.cap_usd:.2f}, "
          f"session cap ${args.session_cap:.2f}")
    variant = f"v2-{args.effort}-f{args.frames}"
    v2, stopped, hits = judge_many(
        client, have, inputs, effort=args.effort, workers=args.workers, cache_root=cache / "ember",
        variant=variant,
        judge_fn=lambda r: judge_v2(client, traces[r.key], shots[r.key], effort=args.effort, run_key=r.key))
    print(f"v2 ({variant}): {hits} from cache, {len(v2) - hits} judged now")
    v1 = {r.key: ember_cache.load(cache / "ember", args.baseline, 0, r.key) for r in have}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPO_ROOT / "results" / f"{'dry_run_v2' if args.dry_run else 'verdict_v2'}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    md = report(args, have, traces, v1, v2, ledger, stopped)
    (out / "report.md").write_text(md, encoding="utf-8")
    (out / "report.json").write_text(json.dumps({
        "args": vars(args), "stopped": stopped,
        "runs": [{"key": r.key, "benchmark": r.benchmark, "gold_success": r.success,
                  "gold_side_effect": r.side_effect, "gold_looping": r.looping,
                  "v2": v2.get(r.key), "v1": v1.get(r.key)} for r in have]},
        indent=2, default=str), encoding="utf-8")
    print("\n" + md + f"\n\nWrote {out / 'report.md'}")
    return 0


def report(args, have, traces, v1, v2, ledger, stopped) -> str:
    md = []
    if args.dry_run:
        md.append("> **DRY RUN.** Mock Ember; numbers are not measurements.\n")
    md.append(f"# Verdict v2 evaluation ({args.split} split, effort {args.effort}, {args.frames} screenshots)\n")
    if stopped:
        md.append(f"**Stopped early by the budget cap (finished results kept):** {stopped[0]}\n")
    ok2 = [r for r in have if judged_ok(v2.get(r.key))]
    common = [r for r in ok2 if judged_ok(v1.get(r.key))]
    bad = [r for r in have if not judged_ok(v2.get(r.key))]
    if bad:
        reasons = Counter("blocked" if (v2.get(r.key) or {}).get("blocked") else
                          "error" if (v2.get(r.key) or {}).get("error") else
                          "truncated" if (v2.get(r.key) or {}).get("truncated") else "not judged" for r in bad)
        md.append(f"**Not usable from v2:** {dict(reasons)} (excluded).\n")
    md.append(f"v2 judged {len(ok2)} runs; {len(common)} also have a v1 (`{args.baseline}`) verdict for the "
              "side-by-side.\n")

    # ---- success: v2 vs v1 on the same runs
    gold = [r.success for r in common]
    p1 = [v1[r.key]["verdict"]["success"] for r in common]
    p2 = [v2[r.key]["verdict"]["success"] for r in common]
    md.append("## Did the agent succeed? (same runs, expert labels)\n")
    md.append("| Judge | Precision | Recall | F1 | Accuracy | Cost per 1,000 runs |")
    md.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name, pred, src in ((f"v1 fair-comparison prompt (`{args.baseline}`)", p1, v1), ("**Verdict v2**", p2, v2)):
        s = binary_scores(gold, pred)
        c = mean([src[r.key]["cost_usd"] for r in common])
        md.append(f"| {name} | {pct(s['precision'])} | {pct(s['recall'])} | "
                  f"{pct(s['f1'])}{ci(bootstrap_ci(gold, pred, 'f1'))} | "
                  f"{pct(s['accuracy'])}{ci(bootstrap_ci(gold, pred, 'accuracy'))} | "
                  f"{'n/a' if c is None else f'${c * 1000:.2f}'} |")
    md.append("")
    for metric in ("accuracy", "f1", "precision", "recall"):
        d = paired_bootstrap(gold, p2, p1, metric)
        if d["diff"] is not None:
            md.append(f"- v2 minus v1, {metric}: {d['diff'] * 100:+.1f} points "
                      f"(95% CI {d['lo'] * 100:+.1f} to {d['hi'] * 100:+.1f}){' **significant**' if d['significant'] else ''}")
    md.append("")

    # ---- side effects and looping
    md.append("## Side effects and looping (v1 vs v2, same runs)\n")
    md.append("| Question | Judge | Accuracy | Precision | Recall | Judge said yes | Experts said yes |")
    md.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for field, name in (("side_effect", "Side effects"), ("looping", "Looping")):
        ks = [r for r in common if getattr(r, field) is not None]
        g = [getattr(r, field) for r in ks]
        for jn, src in (("v1", v1), ("v2", v2)):
            pr = [src[r.key]["verdict"][field] for r in ks]
            s = binary_scores(g, pr)
            md.append(f"| {name} | {jn} | {pct(s['accuracy'])} | {pct(s['precision'])} | {pct(s['recall'])} | "
                      f"{sum(1 for x in pr if x)} | {sum(g)} |")
    md.append("")

    # ---- claimed done but failed
    md.append("## \"Claimed done, but failed\"\n")
    flagged = [r for r in ok2 if v2[r.key]["verdict"].get("claimed_success") and not v2[r.key]["verdict"]["success"]]
    right = sum(1 for r in flagged if not r.success)
    claimed = sum(1 for r in ok2 if v2[r.key]["verdict"].get("claimed_success"))
    md.append(f"- The agent claimed success in {claimed} of {len(ok2)} runs (per v2).")
    md.append(f"- v2 flagged {len(flagged)} of those as **claimed done but failed**; experts agree the run failed "
              f"in {right} of {len(flagged)} ({pct(right / len(flagged)) if flagged else 'n/a'}).\n")

    # ---- failure types
    ft = Counter(v2[r.key]["verdict"].get("failure_type") for r in ok2 if not v2[r.key]["verdict"]["success"])
    md.append("## Failure types (v2, failed runs)\n")
    md.append(", ".join(f"{k}: {v}" for k, v in ft.most_common()) or "none")
    md.append("")

    # ---- confidence and escalation
    md.append("\n## Confidence and escalation\n")
    md.append("| Confidence | Runs | Accuracy vs experts |")
    md.append("| --- | ---: | ---: |")
    for level in ("high", "medium", "low"):
        ks = [r for r in ok2 if v2[r.key]["verdict"].get("confidence") == level]
        s = binary_scores([r.success for r in ks], [v2[r.key]["verdict"]["success"] for r in ks])
        md.append(f"| {level} | {len(ks)} | {pct(s['accuracy'])} |")
    def acc(ks):
        return binary_scores([r.success for r in ks], [v2[r.key]["verdict"]["success"] for r in ks])["accuracy"]

    md.append("\n**Escalation options** (a person settles every run sent to review):\n")
    md.append("| Send to a person | Runs reviewed | Accuracy on the rest | Overall accuracy |")
    md.append("| --- | ---: | ---: | ---: |")
    rules = [("nothing", lambda v: False),
             ("low confidence only", lambda v: v.get("confidence") == "low"),
             ("**anything below high confidence (chosen rule)**", needs_person)]
    for name, rule in rules:
        review = [r for r in ok2 if rule(v2[r.key]["verdict"])]
        auto = [r for r in ok2 if not rule(v2[r.key]["verdict"])]
        correct = sum(1 for r in auto if v2[r.key]["verdict"]["success"] == r.success) + len(review)
        md.append(f"| {name} | {len(review)} ({pct(len(review) / len(ok2) if ok2 else None)}) | {pct(acc(auto))} | "
                  f"{pct(correct / len(ok2) if ok2 else None)} |")
    md.append("")

    # ---- cost
    c = mean([v2[r.key]["cost_usd"] for r in ok2])
    md.append("## Cost\n")
    md.append(f"- v2: ${c * 1000:.2f} per 1,000 runs; {mean([v2[r.key]['prompt_tokens'] for r in ok2]) or 0:,.0f} input "
              f"tokens, {mean([v2[r.key]['completion_tokens'] for r in ok2]) or 0:,.0f} output "
              f"({mean([v2[r.key]['reasoning_tokens'] for r in ok2]) or 0:,.0f} reasoning), "
              f"{mean([v2[r.key]['latency_s'] for r in ok2]) or 0:.1f}s per run, "
              f"{mean([len(v2[r.key].get('frames', [])) for r in ok2]) or 0:.1f} screenshots per run.\n"
              if c is not None else "- no v2 verdicts")

    # ---- examples
    wrong = [r for r in common if v2[r.key]["verdict"]["success"] != r.success]
    md.append(f"## Where v2 disagrees with the experts ({len(wrong)})\n")
    for r in wrong[:8]:
        v = v2[r.key]["verdict"]
        md.append(f"- **{r.key}**: experts {'Successful' if r.success else 'Unsuccessful'}, v2 "
                  f"{'Successful' if v['success'] else 'Unsuccessful'} ({v.get('failure_type')}, confidence "
                  f"{v.get('confidence')}{', flagged for review' if v.get('needs_review') else ''}). Goal: "
                  f"\"{traces[r.key].goal[:110]}\". Evidence: step {v.get('evidence_step')}, "
                  f"{v.get('evidence_screenshot') or '-'}: \"{(v.get('evidence_quote') or '')[:140]}\"")
    md.append(f"\nLedger: this run spent ${ledger.session_spent:.4f}; total recorded ${ledger.total_spent:.4f} "
              f"of the ${ledger.cap_usd:.2f} cap.")
    return "\n".join(md)


if __name__ == "__main__":
    raise SystemExit(main())
