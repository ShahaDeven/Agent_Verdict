"""Load cached AgentRewardBench runs and their Verdict v2 verdicts into the store.

Cache only: it reads files already downloaded and verdicts already paid for. It never calls Ember and
never touches the network, so it costs $0. Runs without a cached prompt or usable verdict are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

from ember_core.ember import REPO_ROOT

from . import ember_cache
from .arb_data import load_runs
from .ember_judge import judged_ok
from .store import Store, save_data_url
from .trace import from_arb_messages

ARB = REPO_ROOT / "data" / "arb"
DEFAULT_VARIANT = "v2-minimal-f4"


def seed(store: Store, *, split: str = "test", variant: str = DEFAULT_VARIANT, data_dir: Path = ARB,
         limit: int | None = None, progress: bool = False) -> dict:
    cache = data_dir / "cache"
    runs, _ = load_runs(data_dir)
    runs = [r for r in runs if split == "all" or r.split == split]
    counts = {"added": 0, "no_prompt": 0, "no_verdict": 0}
    chunk = 200  # one transaction (one disk sync) per 200 runs
    for start in range(0, len(runs), chunk):
        with store.batch():
            for r in runs[start:start + chunk]:
                if limit is not None and counts["added"] >= limit:
                    return counts
                _seed_one(store, r, cache, variant, counts)
        if progress:
            print(f"  {min(start + chunk, len(runs))} of {len(runs)} runs...", flush=True)
    return counts


def _seed_one(store: Store, r, cache: Path, variant: str, counts: dict) -> None:
    inp = cache / "inputs" / f"{r.key}.json"
    res = ember_cache.load(cache / "ember", variant, 0, r.key)
    if not inp.exists():
        counts["no_prompt"] += 1
        return
    if not judged_ok(res):
        counts["no_verdict"] += 1
        return
    trace = from_arb_messages(json.loads(inp.read_text(encoding="utf-8"))["messages"])
    shots_dir = cache / "screens" / r.key
    files = {f.name: f for f in shots_dir.iterdir()} if shots_dir.is_dir() else {}
    screens: dict[int, Path] = {i: files[f"step_{i}.jpg"] for i in range(trace.n_states - 1)
                                if f"step_{i}.jpg" in files}
    if trace.final_screenshot:
        final = files.get("final.jpg") or files.get("final.png")
        if final is None:
            final = save_data_url(trace.final_screenshot, shots_dir / "final")
        screens[trace.n_states - 1] = final
    run_id = store.add_run(r.key, trace, source="agentrewardbench", screens=screens,
                           benchmark=r.benchmark, agent=r.agent, task=r.task_id,
                           reference={"success": r.success, "side_effect": r.side_effect, "looping": r.looping})
    store.add_verdict(run_id, variant, res)
    counts["added"] += 1
