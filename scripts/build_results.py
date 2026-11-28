"""Build results/summary.json for the Results page ($0: cached verdicts + the local database, no API calls).

Everything in it is an aggregate (rates, intervals, counts), never a per-run expert label, so it is safe to
commit. Rerun after new live runs:  python scripts\\build_results.py
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict import ember_cache  # noqa: E402
from agent_verdict.arb_data import COMPARISON_JUDGES, fetch_published_verdict, load_runs, sample_runs  # noqa: E402
from agent_verdict.ember_judge import judged_ok  # noqa: E402
from agent_verdict.metrics import binary_scores, bootstrap_ci, paired_bootstrap  # noqa: E402
from agent_verdict.selection import best_of_attempts  # noqa: E402
from agent_verdict.store import DEFAULT_DB  # noqa: E402
from agent_verdict.verdict_v2 import needs_person  # noqa: E402
from ember_core.ember import REPO_ROOT  # noqa: E402

DATA = REPO_ROOT / "data" / "arb"
NAMES = {"gpt-4o-noaxtree": "GPT-4o", "claude-3.7-sonnet-noaxtree": "Claude 3.7 Sonnet", "gpt-4o-mini-noaxtree": "GPT-4o-mini",
         "qwen-2.5-vl-noaxtree": "Qwen2.5-VL 72B (self-hosted)", "llama-3.3-70b-noscreen": "Llama 3.3 70B (self-hosted, text only)"}
N_BOOT = 2000


def fair_comparison() -> dict:
    """Ember (v1, the benchmark's own prompt) vs the five published judges, same runs, same prompt."""
    cache = DATA / "cache"
    runs, _ = load_runs(DATA)
    rows = []
    for r in sample_runs(runs, "test", 10_000):
        e = ember_cache.load(cache / "ember", "minimal", 0, r.key)
        if not judged_ok(e):
            continue
        pub = {j: fetch_published_verdict(r, j, cache) for j in COMPARISON_JUDGES}
        if any(v is None for v in pub.values()):
            continue
        rows.append((r.success, e, pub))
    gold = [g for g, _, _ in rows]
    preds = {"Muse Ember (minimal)": [e["verdict"]["success"] for _, e, _ in rows]}
    costs = {"Muse Ember (minimal)": statistics.fmean(e["cost_usd"] for _, e, _ in rows)}
    for j in COMPARISON_JUDGES:
        preds[NAMES[j]] = [p[j]["verdict"]["success"] for _, _, p in rows]
        cs = [p[j].get("cost_usd") for _, _, p in rows if p[j].get("cost_usd") is not None]
        costs[NAMES[j]] = statistics.fmean(cs) if cs else None
    ember = preds["Muse Ember (minimal)"]
    judges = []
    for name, pred in preds.items():
        s = binary_scores(gold, pred)
        row = {"judge": name, **{k: s[k] for k in ("precision", "recall", "f1", "accuracy")},
               "f1_ci": bootstrap_ci(gold, pred, "f1", n_boot=N_BOOT), "accuracy_ci": bootstrap_ci(gold, pred, "accuracy", n_boot=N_BOOT),
               "cost_per_1000": costs[name] * 1000 if costs[name] else 0.0, "self_hosted": "self-hosted" in name}
        if name != "Muse Ember (minimal)":
            row["ember_minus"] = {m: paired_bootstrap(gold, ember, pred, m, n_boot=N_BOOT) for m in ("precision", "accuracy", "f1")}
        judges.append(row)
    return {"runs": len(rows), "successes": sum(gold), "judges": judges}


def verdict_v2_and_escalation() -> dict:
    cache = DATA / "cache" / "ember"
    runs, _ = load_runs(DATA)
    rows = []
    for r in sample_runs(runs, "test", 10_000):
        v = ember_cache.load(cache, "v2-minimal-f4", 0, r.key)
        if judged_ok(v):
            rows.append((r.success, v["verdict"], v["cost_usd"]))
    acc = lambda rs: sum(bool(v["success"]) == g for g, v, _ in rs) / len(rs) if rs else None  # noqa: E731
    by_conf = {lvl: {"runs": len(rs), "accuracy": acc(rs)} for lvl in ("high", "medium", "low")
               for rs in [[x for x in rows if x[1].get("confidence") == lvl]]}
    rules = [("Nothing", lambda v: False), ("Low confidence only", lambda v: v.get("confidence") == "low"),
             ("Anything below high confidence (the product's rule)", needs_person), ("Everything", lambda v: True)]
    curve = []
    for name, rule in rules:
        review = [x for x in rows if rule(x[1])]
        auto = [x for x in rows if not rule(x[1])]
        correct = sum(bool(v["success"]) == g for g, v, _ in auto) + len(review)
        curve.append({"rule": name, "reviewed": len(review) / len(rows), "accuracy_auto": acc(auto),
                      "accuracy_overall": correct / len(rows)})
    s = binary_scores([g for g, _, _ in rows], [v["success"] for _, v, _ in rows])
    return {"runs": len(rows), "precision": s["precision"], "recall": s["recall"], "accuracy": s["accuracy"],
            "cost_per_1000": statistics.fmean(c for _, _, c in rows) * 1000, "by_confidence": by_conf, "escalation": curve}


def live() -> dict:
    if not DEFAULT_DB.exists():
        return {"agents": []}
    c = sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    latest = "v.rowid = (SELECT MAX(rowid) FROM verdicts WHERE run_id = v.run_id)"
    rows = c.execute(f"""SELECT r.agent, r.ref_success, v.success, v.claimed_success, v.needs_review, v.cost_usd
                         FROM runs r JOIN verdicts v ON v.run_id = r.id AND {latest}
                         WHERE r.source = 'live' AND v.judge NOT LIKE '%dryrun%'""").fetchall()
    out = []
    for agent in sorted({r["agent"] for r in rows}):
        rs = [r for r in rows if r["agent"] == agent]
        scored = [r for r in rs if r["ref_success"] is not None]
        false_claims = [r for r in scored if not r["ref_success"] and r["claimed_success"]]
        out.append({"agent": agent, "runs": len(rs), "scored": len(scored),
                    "agree": sum(bool(r["success"]) == bool(r["ref_success"]) for r in scored),
                    "agent_succeeded": sum(bool(r["ref_success"]) for r in scored), "declined": len(rs) - len(scored),
                    "false_claims": len(false_claims), "false_claims_caught": sum(not r["success"] for r in false_claims),
                    "sent_to_person": sum(bool(r["needs_review"]) for r in rs),
                    "cost_per_verdict": statistics.fmean(r["cost_usd"] for r in rs if r["cost_usd"] is not None) if rs else None})
    return {"agents": out}


def spend() -> float:
    p = REPO_ROOT / "usage_log.jsonl"
    return sum(float(json.loads(x).get("cost_usd", 0)) for x in p.read_text(encoding="utf-8").splitlines() if x.strip())


def main() -> int:
    print("Fair comparison (paired bootstrap, takes a minute)...")
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fair": fair_comparison()}
    print("Verdict v2 and escalation...")
    out["v2"] = verdict_v2_and_escalation()
    print("Best of several attempts...")
    out["best_attempt"] = best_of_attempts(n_boot=N_BOOT)
    out["live"] = live()
    out["total_spend_usd"] = spend()
    p = REPO_ROOT / "results" / "summary.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
