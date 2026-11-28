"""Live demo: our Ember web agent does tasks on the local demo sites; each run is judged as it finishes.

Needs two other terminals running:
  agent-verdict demo-sites       # the shop, the restaurant and the help desk on http://127.0.0.1:5100
  agent-verdict serve            # the review UI; open http://127.0.0.1:8000/#/live to watch

Usage (from the repo root):
  python scripts\\live_demo.py --dry-run --tasks shop-aa            # mock Ember, $0 (writes to a separate dry-run DB)
  python scripts\\live_demo.py --tasks shop-aa,bistro-fri-730 --max-usd 0.10
  python scripts\\live_demo.py --tasks all --attempts 3 --max-usd 1.50
  add --headed to watch the browser (good for recording)

For every attempt: reset the sites, run the agent, read the sites' records to get the TRUE outcome (the
task's checker), save the run (it shows on the Live page as "judging"), judge it with Verdict v2, and
save the verdict. The agent's steps and the judging share one spend ledger and one --max-usd cap.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict import api  # noqa: E402
from agent_verdict.store import Store  # noqa: E402
from agent_verdict.trace import from_generic  # noqa: E402
from agent_verdict.web_agent import run_agent  # noqa: E402
from demo_sites.tasks import BY_ID, TASKS, outcome, side_effects  # noqa: E402
from ember_core.budget import BudgetExceeded  # noqa: E402
from ember_core.ember import REPO_ROOT  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all", help="comma-separated task ids, or all | standard (30) | hard (6) | visual (5) | forms (3)")
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--max-usd", type=float, default=0.10, help="spend cap for this script run (agent + judge)")
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--effort", default="minimal", help="agent reasoning effort (the judge always uses minimal)")
    ap.add_argument("--text-only", action="store_true",
                    help="text-only agent: no screenshots for the agent (the judge still sees them)")
    ap.add_argument("--sites", default="http://127.0.0.1:5100")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--slow-mo", type=int, default=0, help="ms pause between browser actions (for recording)")
    ap.add_argument("--dry-run", action="store_true", help="mock Ember, $0; stores into data/app/dry_run.db")
    ap.add_argument("--db", help="database to store runs in (default: the review app's)")
    args = ap.parse_args()

    if args.tasks == "all":
        tasks = TASKS
    elif args.tasks == "standard":
        tasks = [t for t in TASKS if not {"hard", "visual", "forms"} & set(t.tags)]
    elif args.tasks in ("hard", "visual", "forms"):
        tasks = [t for t in TASKS if args.tasks in t.tags]
    else:
        tasks = [BY_ID[t.strip()] for t in args.tasks.split(",")]
    try:
        requests.get(f"{args.sites}/_state", timeout=3).raise_for_status()
    except requests.RequestException:
        print(f"The demo sites aren't running at {args.sites}. Start them with: agent-verdict demo-sites")
        return 1

    from playwright.sync_api import sync_playwright

    client = api.make_client(dry_run=args.dry_run, max_usd=args.max_usd)
    db = args.db or (REPO_ROOT / "data" / "app" / "dry_run.db" if args.dry_run else None)
    store = Store(db) if db else Store()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    live_dir = REPO_ROOT / "data" / "live" / stamp
    max_steps = 3 if args.dry_run else args.max_steps
    print(f"{'DRY RUN (mock Ember, $0). ' if args.dry_run else ''}{len(tasks)} tasks x {args.attempts} attempts; "
          f"spend cap ${args.max_usd:.2f} (ledger total so far ${client.ledger.prior_spent:.4f} of ${client.ledger.cap_usd:.2f}); "
          f"runs go to {store.path}")

    agent_label = f"Ember web agent{', text only' if args.text_only else ''} ({args.effort})"
    print(f"Agent: {agent_label}")
    rows, stopped = [], None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow_mo)
        try:
            for attempt in range(1, args.attempts + 1):
                for task in tasks:
                    key = f"live/{task.id}/a{attempt}{'-text' if args.text_only else ''}/{stamp}"
                    requests.post(f"{args.sites}/_reset", timeout=5).raise_for_status()
                    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                    page = ctx.new_page()
                    t0 = time.time()
                    try:
                        run = run_agent(client, page, task.goal, args.sites + task.start, live_dir / task.id / f"a{attempt}",
                                        max_steps=max_steps, effort=args.effort, run_key=key, see_screen=not args.text_only)
                    finally:
                        ctx.close()
                    state = requests.get(f"{args.sites}/_state", timeout=5).json()
                    result = outcome(task, state, run.final_message or "")
                    ok = result != "failed"
                    se = side_effects(task, state)
                    trace = from_generic(run.trace_json(), live_dir)
                    screens = {i: Path(s["screenshot"]) for i, s in enumerate(run.steps)}
                    screens[len(run.steps)] = Path(run.final_screenshot)
                    # Truth: did the goal get done? For a task that CAN'T be done as asked, an honest "can't" is the right
                    # behaviour but not "success" in the usual sense, so it gets no yes/no label (reported separately).
                    # Doing something else instead, or claiming it's done, is a clear failure.
                    declined = result == "declined"
                    truth = None if declined else result == "success"
                    run_id = store.add_run(key, trace, source="live", screens=screens, agent=agent_label,
                                           task=task.id, reference={"success": truth, "side_effect": bool(se), "looping": None})
                    (live_dir / task.id / f"a{attempt}" / "run.json").write_text(json.dumps(
                        {**run.trace_json(), "task": task.id, "feasible": task.feasible, "final_message": run.final_message,
                         "ended": run.ended, "checker_success": ok, "side_effects": se, "agent_cost_usd": run.cost_usd,
                         "parse_failures": run.parse_failures}, indent=2), encoding="utf-8")
                    res = api.judge(trace, client=client, run_key=key)
                    judged = "error"
                    if not res.get("error"):
                        f = store.add_verdict(run_id, f"v2-minimal-f4{'-dryrun' if args.dry_run else ''}", res)
                        v = res["verdict"]
                        judged = f"{f:6} (judge says {'success' if v['success'] else 'failed'}, {v['confidence']})"
                    rows.append({"task": task.id, "attempt": attempt, "run_id": run_id, "checker": ok, "truth": truth,
                                 "declined": declined, "side_effects": se, "ended": run.ended, "steps": len(run.steps),
                                 "parse_failures": len(run.parse_failures), "agent_cost": run.cost_usd,
                                 "judge_cost": res.get("cost_usd"), "verdict": res.get("verdict"),
                                 "final_message": run.final_message})
                    label = "DECLINED" if declined else ("SUCCESS " if ok else "FAILED  ")
                    print(f"  #{run_id:<5} {task.id:26} a{attempt}  truth: {label}"
                          f"{f' ({len(run.parse_failures)} unreadable answers)' if run.parse_failures else ''}  "
                          f"{'side effect ' + ','.join(se) + '  ' if se else ''}{len(run.steps):2} steps  "
                          f"{time.time() - t0:5.1f}s  judge: {judged}")
        except BudgetExceeded as e:
            stopped = str(e)
            print(f"\nStopped by the spend cap (finished runs are kept): {e}")
        finally:
            browser.close()

    report(rows, args, client, stopped, stamp)
    return 0


def report(rows, args, client, stopped, stamp) -> None:
    judged = [r for r in rows if r["verdict"] and r["verdict"].get("success") is not None]
    scored = [r for r in judged if r["truth"] is not None]
    agree = sum(1 for r in scored if bool(r["verdict"]["success"]) == r["truth"])
    caught = [r for r in scored if not r["truth"] and r["verdict"].get("claimed_success")]
    caught_ok = sum(1 for r in caught if not r["verdict"]["success"])
    declined = [r for r in judged if r["declined"]]
    lines = [f"# Live demo {stamp}{' (DRY RUN: mock Ember)' if args.dry_run else ''}"
             f"{' (text-only agent: no screenshots)' if args.text_only else ''}", "",
             f"{len(rows)} runs; per the sites' own records the agent succeeded on {sum(1 for r in rows if r['truth'])}, "
             f"failed on {sum(1 for r in rows if r['truth'] is False)}, and honestly declined {len(declined)} impossible task(s).",
             f"The judge agreed with the true outcome on {agree} of {len(scored)} runs." if scored else "No scored verdicts.",
             (f"Honest declines: the judge called {sum(1 for r in declined if r['verdict']['success'])} a success and "
              f"{sum(1 for r in declined if not r['verdict']['success'])} a failure ('{', '.join(sorted({str(r['verdict'].get('failure_type')) for r in declined}))}')."
              if declined else ""),
             f"Unreadable agent answers (retried): {sum(r['parse_failures'] for r in rows)}.",
             (f"Runs that failed while the agent claimed success: {len(caught)}; the judge called {caught_ok} of them failed."
              if caught else "No 'claimed done, but failed' runs."),
             f"Sent to a person: {sum(1 for r in judged if r['verdict'].get('needs_review'))}.",
             f"Spend this run: ${client.ledger.session_spent:.4f} (agent ${sum(r['agent_cost'] for r in rows):.4f}, "
             f"judge ${sum(r['judge_cost'] or 0 for r in rows):.4f}); ledger total ${client.ledger.total_spent:.4f}.",
             ""]
    if stopped:
        lines.insert(2, f"**Stopped early by the spend cap:** {stopped}\n")
    out = REPO_ROOT / "results" / f"{'dry_run_live' if args.dry_run else 'live_demo'}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "runs.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(lines) + f"\nWrote {out / 'report.md'}")


if __name__ == "__main__":
    raise SystemExit(main())
