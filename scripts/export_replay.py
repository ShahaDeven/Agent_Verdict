"""Export recorded live runs into demo_replay/, the bundle `agent-verdict demo --replay` plays back ($0, local only).

The runs are our own (our demo sites, our Ember agent, Ember's real verdicts), so they can ship in the repo,
unlike the AgentRewardBench data. Screenshots are resized to 1024 px wide and saved as JPEG to keep the
bundle small (~11 MB). Usage:  python scripts\\export_replay.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_verdict.store import DEFAULT_DB, resolve  # noqa: E402
from ember_core.ember import REPO_ROOT  # noqa: E402

OUT = REPO_ROOT / "demo_replay"
# Which recorded runs to ship: one attempt of every task with the main agent, and all text-only runs.
BATCHES = [("live/%/a1/20261127_142305", "standard"), ("live/%/a1/20261127_233614", "hard"),
           ("live/%/a1/20261128_001409", "visual"), ("live/%/a1/20261128_001705", "forms"),
           ("live/%/20261128_002527", "text-only")]
# The last runs to "arrive" while the replay plays (the rest are there from the start). Spread the false claims.
STREAM = ["shop-aa", "text:shop-umbrella-red:a1", "bistro-sat-waitlist", "shop-mug-lighthouse", "text:shop-bottle-blue:a2",
          "desk-new-ortiz", "shop-lamp", "desk-close-4482"]
LATEST = "v.rowid = (SELECT MAX(rowid) FROM verdicts WHERE run_id = v.run_id)"


def _b(x):
    return None if x is None else bool(x)


def main() -> int:
    c = sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "screens").mkdir(parents=True)
    runs, total = [], 0
    for pattern, batch in BATCHES:
        for r in c.execute(f"""SELECT r.*, v.judge, v.success, v.claimed_success, v.failure_type, v.side_effect,
                                      v.side_effect_detail, v.looping, v.evidence_step, v.evidence_screenshot,
                                      v.evidence_quote, v.confidence, v.needs_review, v.reasoning, v.frames_json,
                                      v.cost_usd, v.latency_s, v.tokens_in, v.tokens_out, v.reasoning_tokens
                               FROM runs r JOIN verdicts v ON v.run_id = r.id AND {LATEST}
                               WHERE r.key LIKE ? AND v.judge NOT LIKE '%dryrun%' ORDER BY r.id""", (pattern,)):
            attempt = r["key"].split("/")[2]
            slug = f"{batch}-{r['task']}-{attempt}"
            screens = {}
            for state, path in json.loads(r["screens_json"]).items():
                src = resolve(path)
                if not src.exists():
                    continue
                dst = OUT / "screens" / slug / f"{state}.jpg"
                dst.parent.mkdir(parents=True, exist_ok=True)
                im = Image.open(src).convert("RGB")
                im.thumbnail((1024, 1024))
                im.save(dst, "JPEG", quality=65, optimize=True)
                total += dst.stat().st_size
                screens[state] = dst.relative_to(OUT).as_posix()
            stream_id = f"text:{r['task']}:{attempt.split('-')[0]}" if batch == "text-only" else r["task"]
            runs.append({
                "id": slug, "batch": batch, "task": r["task"], "agent": r["agent"], "goal": r["goal"],
                "steps": json.loads(r["steps_json"]), "n_states": r["n_states"], "final_message": r["final_message"],
                "screens": screens,
                "reference": {"success": _b(r["ref_success"]), "side_effect": _b(r["ref_side_effect"]), "looping": None},
                "judge": r["judge"], "stream_order": STREAM.index(stream_id) if stream_id in STREAM else None,
                "result": {"verdict": {k: (_b(r[k]) if k in ("success", "claimed_success", "side_effect", "looping", "needs_review") else r[k])
                                       for k in ("success", "claimed_success", "failure_type", "side_effect", "side_effect_detail",
                                                 "looping", "evidence_step", "evidence_screenshot", "evidence_quote",
                                                 "confidence", "needs_review", "reasoning")},
                           "frames": json.loads(r["frames_json"] or "[]"), "cost_usd": r["cost_usd"], "latency_s": r["latency_s"],
                           "prompt_tokens": r["tokens_in"], "completion_tokens": r["tokens_out"],
                           "reasoning_tokens": r["reasoning_tokens"]},
            })
    missing = [s for s in STREAM if not any((f"text:{x['task']}:{x['id'].rsplit('-', 2)[-2]}" if x["batch"] == "text-only" else x["task"]) == s
                                             for x in runs)]
    (OUT / "runs.json").write_text(json.dumps({"runs": runs}, indent=1), encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Replay bundle\n\nReal runs of our Ember web agent on the local demo sites, with Ember's real verdicts and the sites'\n"
        "true outcomes. `agent-verdict demo --replay` plays them back with no API key. Rebuild with\n"
        "`python scripts/export_replay.py`. All of this is our own data (no AgentRewardBench content).\n", encoding="utf-8")
    print(f"Exported {len(runs)} runs, {sum(len(r['screens']) for r in runs)} screenshots, {total / 1e6:.1f} MB to {OUT}")
    if missing:
        print("WARNING: stream runs not found:", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
