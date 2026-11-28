"""Play back recorded live runs (demo_replay/) into a fresh database: no API key, no network, $0.

Most runs are loaded at once, so every screen has data from the start. The runs marked for streaming then
"arrive" one by one: each appears as judging, and gets its real recorded verdict a moment later, like the
live demo. Built by scripts/export_replay.py from our own agent's runs on the demo sites.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ember_core.ember import REPO_ROOT

from .store import Store
from .trace import Step, Trace

BUNDLE = REPO_ROOT / "demo_replay"


def load_bundle(bundle: Path = BUNDLE) -> list[dict]:
    p = bundle / "runs.json"
    if not p.exists():
        raise FileNotFoundError(f"no replay bundle at {bundle} (build it with python scripts/export_replay.py)")
    return json.loads(p.read_text(encoding="utf-8"))["runs"]


def _add_run(store: Store, r: dict, bundle: Path) -> int:
    trace = Trace(goal=r["goal"], steps=[Step(s["n"], s["url"], s["action"], s["reasoning"]) for s in r["steps"]],
                  final_screenshot=None)
    screens = {int(i): bundle / path for i, path in r["screens"].items()}
    run_id = store.add_run(f"replay/{r['id']}", trace, source="live", screens=screens, agent=r["agent"], task=r["task"],
                           reference=r["reference"])
    with store.conn() as c:  # final_message came from the agent's own message, keep it exactly
        c.execute("UPDATE runs SET final_message = ? WHERE id = ?", (r["final_message"], run_id))
    return run_id


def play(store: Store, *, bundle: Path = BUNDLE, judging_s: float = 2.5, gap_s: float = 3.0, log=print) -> int:
    """Load the bundle into `store`; stream the marked runs. Returns the number of runs."""
    runs = load_bundle(bundle)
    upfront = [r for r in runs if r["stream_order"] is None]
    stream = sorted((r for r in runs if r["stream_order"] is not None), key=lambda r: r["stream_order"])
    with store.batch():
        for r in upfront:
            store.add_verdict(_add_run(store, r, bundle), r["judge"], r["result"])
    log(f"Loaded {len(upfront)} recorded runs; {len(stream)} more will arrive one by one.")
    for r in stream:
        time.sleep(gap_s)
        run_id = _add_run(store, r, bundle)
        log(f"  run #{run_id} finished: {r['goal'][:70]}  (judging...)")
        time.sleep(judging_s)
        f = store.add_verdict(run_id, r["judge"], r["result"])
        v = r["result"]["verdict"]
        log(f"  run #{run_id} verdict: {f} ({'succeeded' if v['success'] else 'failed'}, {v['confidence']} confidence)")
    return len(runs)
