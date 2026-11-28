"""The agent-verdict command.

  agent-verdict judge run.json [more.json ...] [--dry-run] [--max-usd 0.05] [--json] [--save]
  agent-verdict seed-arb [--split test]        # load cached benchmark verdicts into the store ($0)
  agent-verdict serve [--allow-spend --max-usd 0.10] [--dry-run]

Judging calls Muse Ember (about $0.001 per run); every call is capped by --max-usd for this command
and by the ledger's $7.00 total cap. --dry-run uses a mock and costs nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ember_core.budget import BudgetExceeded

from . import api

MARK = {"yellow": "[YELLOW] Needs review", "green": "[GREEN]  Succeeded", "red": "[RED]    Failed"}


def _print_verdict(path: Path, trace, res: dict) -> None:
    v = res["verdict"]
    f = api.flag(v)
    print(f"\n{path.name}  {MARK[f]}")
    print(f"  Goal: {trace.goal[:160]}")
    lean = "succeeded" if v["success"] else f"failed ({v['failure_type']})"
    print(f"  Judge: {lean}, confidence {v['confidence']}"
          + (", claimed success" if v.get("claimed_success") else ""))
    if v.get("side_effect"):
        print(f"  Side effect (hint): {v.get('side_effect_detail') or 'yes'}")
    if v.get("looping"):
        print("  Looping: yes")
    print(f"  Evidence: step {v.get('evidence_step')}, screenshot {v.get('evidence_screenshot') or '-'}: "
          f"\"{(v.get('evidence_quote') or '')[:200]}\"")
    print(f"  Reasoning: {v.get('reasoning', '')}")
    print(f"  Cost ${res.get('cost_usd', 0):.5f}, {res.get('latency_s', 0):.1f}s, screenshots {res.get('frames')}")


def cmd_judge(args) -> int:
    client = api.make_client(dry_run=args.dry_run, max_usd=args.max_usd)
    if args.dry_run:
        print("DRY RUN: mock Ember, verdicts are placeholders, $0.")
    store = None
    if args.save:
        from .store import Store
        store = Store(args.db) if args.db else Store()
    out, rc = [], 0
    for p in map(Path, args.files):
        try:
            trace = api.load_trace(p)
            res = api.judge(trace, client=client, effort=args.effort, frames=args.frames, run_key=str(p))
        except BudgetExceeded as e:
            print(f"\nStopped: spend cap reached, nothing sent for {p.name} or later files. {e}", file=sys.stderr)
            return 2
        except (OSError, ValueError) as e:
            print(f"\n{p}: {e}", file=sys.stderr)
            rc = 1
            continue
        if res.get("error"):
            print(f"\n{p.name}: {res['error']}", file=sys.stderr)
            rc = 1
            continue
        if store is not None:
            from .store import save_data_url
            from .server import screens_dir
            key = f"cli/{p.resolve().as_posix()}"
            safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in p.stem)
            folder = screens_dir(store) / safe
            screens = {i: save_data_url(u, folder / f"state_{i}") for i, u in trace.screenshots.items()}
            if trace.final_screenshot and trace.n_states - 1 not in screens:
                screens[trace.n_states - 1] = save_data_url(trace.final_screenshot,
                                                            folder / f"state_{trace.n_states - 1}")
            run_id = store.add_run(key, trace, source="generic", screens=screens)
            store.add_verdict(run_id, f"v2-{args.effort}-f{args.frames}" + ("-dryrun" if args.dry_run else ""), res)
        out.append({"file": str(p), "flag": api.flag(res["verdict"]), **res["verdict"],
                    "cost_usd": res.get("cost_usd")})
        if not args.json:
            _print_verdict(p, trace, res)
    if args.json:
        print(json.dumps(out, indent=2))
    led = client.ledger
    print(f"\nSpent ${led.session_spent:.4f} this command; total ${led.total_spent:.4f} of the ${led.cap_usd:.2f} cap.",
          file=sys.stderr)
    return rc


def cmd_seed(args) -> int:
    from .seed_arb import seed
    from .store import Store
    store = Store(args.db) if args.db else Store()
    print("Reading cached runs from disk (about 1 to 5 minutes for the test split; no network, $0)...", flush=True)
    counts = seed(store, split=args.split, variant=args.variant, limit=args.limit, progress=True)
    print(f"Loaded {counts['added']} runs into {store.path} "
          f"(skipped: {counts['no_prompt']} not downloaded, {counts['no_verdict']} without a usable verdict). $0.")
    s = store.summary()
    print(f"Queue: {s['to_review']} need review; {s['auto_decided']} decided by the judge; flags {s['flags']}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .server import create_app
    from .store import Store
    store = Store(args.db) if args.db else Store()
    app = create_app(store, allow_spend=args.allow_spend, max_usd=args.max_usd, dry_run=args.dry_run)
    mode = ("judging ON (mock, $0)" if args.dry_run else
            f"judging ON, capped at ${args.max_usd:.2f} for this session" if args.allow_spend else
            "judging OFF (read, review and import only, $0)")
    print(f"Agent Verdict on http://{args.host}:{args.port}  ({mode}); API docs at /docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_demo_sites(args) -> int:
    import uvicorn

    from demo_sites.app import app
    print(f"Demo sites on http://{args.host}:{args.port}: /shop (Lakeshore Supply), /bistro (Harbor Bistro), "
          f"/desk (Northpoint Help Desk). Data resets on restart or POST /_reset.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent-verdict", description="Muse Ember judge for AI agent runs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser("judge", help="judge run files (generic JSON or AgentRewardBench prompt)")
    j.add_argument("files", nargs="+")
    j.add_argument("--effort", default=api.DEFAULT_EFFORT)
    j.add_argument("--frames", type=int, default=api.DEFAULT_FRAMES)
    j.add_argument("--max-usd", type=float, default=0.05, help="spend cap for this command (default $0.05)")
    j.add_argument("--dry-run", action="store_true", help="mock Ember, $0")
    j.add_argument("--json", action="store_true", help="print verdicts as JSON")
    j.add_argument("--save", action="store_true", help="also add the runs and verdicts to the review queue")
    j.add_argument("--db")
    j.set_defaults(fn=cmd_judge)

    s = sub.add_parser("seed-arb", help="load cached AgentRewardBench verdicts into the store ($0)")
    s.add_argument("--split", default="test", choices=["dev", "test", "all"])
    s.add_argument("--variant", default="v2-minimal-f4")
    s.add_argument("--limit", type=int)
    s.add_argument("--db")
    s.set_defaults(fn=cmd_seed)

    v = sub.add_parser("serve", help="run the local backend for the review UI")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.add_argument("--allow-spend", action="store_true", help="allow POST /api/runs/{id}/judge to call Ember")
    v.add_argument("--max-usd", type=float, default=0.10, help="spend cap for this server session")
    v.add_argument("--dry-run", action="store_true", help="judge endpoint uses mock Ember ($0)")
    v.add_argument("--db")
    v.set_defaults(fn=cmd_serve)

    d = sub.add_parser("demo-sites", help="run the local demo sites the live agent works on")
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=5100)
    d.set_defaults(fn=cmd_demo_sites)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
