"""Agent Verdict's Python API: judge one agent run.

    from agent_verdict import api
    trace = api.load_trace("run.json")          # generic JSON or an AgentRewardBench prompt file
    result = api.judge(trace, max_usd=0.05)     # Verdict v2 on Muse Ember, spend-capped
    result["verdict"]["success"], result["verdict"]["needs_review"], api.flag(result["verdict"])

Every call goes through the same spend ledger as the evaluation scripts (usage_log.jsonl, hard
$7.00 cap; each call's worst case is reserved before it is sent).
"""

from __future__ import annotations

import json
from pathlib import Path

from ember_core.budget import DEFAULT_CAP_USD, Ledger
from ember_core.ember import REPO_ROOT, EmberClient

from .trace import Trace, from_arb_messages, from_generic
from .verdict_v2 import judge_v2, select_states

DEFAULT_EFFORT = "minimal"   # chosen on the dev split; confirmed on the test split
DEFAULT_FRAMES = 4

# Race Control flags: the outcome at a glance. Colour is never the only signal; the UI always shows
# the label too. Looping and side effects are secondary tags on top of the flag, because a run can loop
# and still succeed or fail.
FLAGS = {
    "yellow": "Needs review",
    "green": "Succeeded",
    "red": "Failed",
}


def flag(verdict: dict) -> str:
    """One outcome flag per verdict. Anything sent to a person is yellow, whatever the judge leaned to."""
    if verdict.get("needs_review"):
        return "yellow"
    return "green" if verdict.get("success") else "red"


def load_trace(path: str | Path) -> Trace:
    """Read a run from disk. Accepts the generic format ({"goal", "steps", ...}; screenshot paths
    are relative to the file) or an AgentRewardBench judge file ({"messages": [...]} or a list)."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "goal" in data and "steps" in data:
        return from_generic(data, path.parent)
    messages = data.get("messages") if isinstance(data, dict) else data
    if isinstance(messages, list):
        return from_arb_messages(messages)
    raise ValueError(f"{path}: not a generic trace (goal + steps) or an AgentRewardBench prompt")


def pick_screenshots(trace: Trace, frames: int = DEFAULT_FRAMES) -> dict[int, str]:
    """The page states the judge sees: FINAL plus the states just before it (see select_states)."""
    out = {}
    for i in select_states(trace.n_states, frames):
        url = trace.final_screenshot if i == trace.n_states - 1 else trace.screenshots.get(i)
        if url:
            out[i] = url
    return out


def make_client(*, dry_run: bool = False, max_usd: float = 0.05, ledger_path: str | Path | None = None,
                cap_usd: float = DEFAULT_CAP_USD) -> EmberClient:
    """An Ember client with a spend cap for this session (max_usd) on top of the hard total cap."""
    path = Path(ledger_path) if ledger_path else REPO_ROOT / ("dry_run_log.jsonl" if dry_run else "usage_log.jsonl")
    return EmberClient(Ledger(path, cap_usd=cap_usd, session_cap_usd=max_usd), dry_run=dry_run)


def judge(trace: Trace, *, client: EmberClient | None = None, effort: str = DEFAULT_EFFORT,
          frames: int = DEFAULT_FRAMES, run_key: str = "local", dry_run: bool = False,
          max_usd: float = 0.05) -> dict:
    """Judge one run with Verdict v2. Returns the judge result: {"verdict": {...}, "cost_usd", ...};
    an unusable answer comes back with an "error" key instead of raising.
    Raises ember_core.budget.BudgetExceeded if the call would pass a spend cap (nothing is sent)."""
    if not trace.steps:
        raise ValueError("the run has no steps to judge")
    client = client or make_client(dry_run=dry_run, max_usd=max_usd)
    return judge_v2(client, trace, pick_screenshots(trace, frames), effort=effort, run_key=run_key)
