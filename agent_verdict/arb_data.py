"""AgentRewardBench data: expert labels, splits, judge inputs and published judge verdicts.

Dataset: McGill-NLP/agent-reward-bench on Hugging Face (public, not gated; no license is stated
on the dataset card or the GitHub repo, so we use it for its intended purpose, evaluating judges,
and do not redistribute it). Paper: https://arxiv.org/abs/2504.08942

Each published judgment file holds the exact prompt a judge received (system prompt, goal, the
agent's actions and reasoning, and the final screenshot as a data URL) plus that judge's answer.
We send Ember the identical prompt, so its numbers are directly comparable with the published
judges on the same runs.

The files are ~0.75 MB because of the screenshot, but the "response" field comes before
"chat_messages", so for comparison judges we download only the first few KB (HTTP Range).
"""

from __future__ import annotations

import csv
import json
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import requests

HF = "https://huggingface.co/datasets/McGill-NLP/agent-reward-bench/resolve/main"
USER_AGENT = "agent-verdict-hackathon/0.1"
REFERENCE_JUDGE = "gpt-4o-noaxtree"  # its file supplies the prompt Ember gets (goal, actions, final screenshot)
COMPARISON_JUDGES = ["gpt-4o-noaxtree", "claude-3.7-sonnet-noaxtree", "gpt-4o-mini-noaxtree",
                     "qwen-2.5-vl-noaxtree", "llama-3.3-70b-noscreen"]


@dataclass(frozen=True)
class Run:
    """One agent trajectory with its expert label."""
    benchmark: str
    agent: str
    task_id: str
    split: str
    success: bool         # expert label (majority of annotators)
    side_effect: bool | None
    looping: bool | None
    n_annotators: int

    @property
    def key(self) -> str:
        return f"{self.benchmark}/{self.agent}/{self.task_id}"


# ---------------------------------------------------------------- labels and sampling

def _split_key(task_id: str) -> str:
    """Annotation ids differ from splits.csv ids for two benchmarks:
    assistantbench.improved.validation.N -> assistantbench.validation.N,
    visualwebarena.resized.N -> visualwebarena.N."""
    return (task_id.replace("assistantbench.improved.validation", "assistantbench.validation")
                   .replace("visualwebarena.resized.", "visualwebarena."))


def ensure_metadata(data_dir: Path) -> None:
    """Download the label and split CSVs if they aren't here yet (they are not committed)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("annotations.csv", "splits.csv"):
        path = data_dir / name
        if not path.exists():
            r = _get(f"{HF}/data/{name}")
            if r is None:
                raise RuntimeError(f"could not download {name} from Hugging Face")
            path.write_bytes(r.content)


def load_runs(data_dir: Path) -> tuple[list[Run], dict]:
    """Expert-labelled runs, one per (benchmark, agent, task). Multiple annotators are combined by
    majority; ties and 'Unsure' are dropped (counted in the returned stats)."""
    ensure_metadata(data_dir)
    splits = {r["task_id"]: r["split"] for r in csv.DictReader(open(data_dir / "splits.csv", encoding="utf-8"))}
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in csv.DictReader(open(data_dir / "annotations.csv", encoding="utf-8")):
        groups[(r["benchmark"], r["model_name"], r["task_id"])].append(r)

    def vote(rows, field, yes):
        vals = [r[field] for r in rows if r[field] in yes]
        if not vals:
            return None
        pos = sum(v == yes[0] for v in vals)
        return None if pos * 2 == len(vals) else pos * 2 > len(vals)

    runs, dropped = [], {"tie_or_unsure": 0, "no_split": 0}
    for (bench, agent, task), rows in groups.items():
        success = vote(rows, "trajectory_success", ("Successful", "Unsuccessful"))
        split = splits.get(task) or splits.get(_split_key(task))
        if success is None:
            dropped["tie_or_unsure"] += 1
            continue
        if split is None:
            dropped["no_split"] += 1
            continue
        runs.append(Run(bench, agent, task, split, success,
                        vote(rows, "trajectory_side_effect", ("Yes", "No")),
                        vote(rows, "trajectory_looping", ("Yes", "No")), len(rows)))
    return runs, dropped


def sample_runs(runs: list[Run], split: str, n: int, seed: int = 0) -> list[Run]:
    """Stratified by benchmark and agent so one website or one agent doesn't dominate."""
    pool = [r for r in runs if r.split == split]
    rng = random.Random(seed)
    strata: dict[tuple, list[Run]] = defaultdict(list)
    for r in pool:
        strata[(r.benchmark, r.agent)].append(r)
    for s in strata.values():
        rng.shuffle(s)
    out, keys = [], sorted(strata)
    while len(out) < min(n, len(pool)):
        for k in keys:
            if strata[k] and len(out) < n:
                out.append(strata[k].pop())
    return out


# ---------------------------------------------------------------- downloading

def _candidates(run: Run, judge: str) -> list[str]:
    ids = [run.task_id]
    if run.benchmark == "assistantbench" and ".improved." not in run.task_id:
        ids.append(run.task_id.replace("assistantbench.validation", "assistantbench.improved.validation"))
    return [f"{HF}/judgments/{run.benchmark}/{run.agent}/{judge}/{t}.json" for t in ids]


def _get(url: str, byte_range: int | None = None) -> requests.Response | None:
    headers = {"User-Agent": USER_AGENT}
    if byte_range:
        headers["Range"] = f"bytes=0-{byte_range - 1}"
    for attempt in range(4):
        try:
            r = requests.get(url, headers=headers, timeout=60)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(2 * 2 ** attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * 2 ** attempt)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"failed to download {url}")


def fetch_reference(run: Run, cache: Path) -> dict | None:
    """The reference judge's file: the exact prompt (with screenshot) plus that judge's verdict."""
    path = cache / "inputs" / f"{run.key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for url in _candidates(run, REFERENCE_JUDGE):
        r = _get(url)
        if r is not None:
            full = r.json()
            keep = {"messages": full["chat_messages"]["regular"], "goal": full.get("goal"),
                    "reference_verdict": parse_verdict(_response_text(full)),
                    "reference_cost_usd": (full.get("cost") or {}).get("total_price")}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(keep), encoding="utf-8")
            return keep
    return None


_RESP = re.compile(r'"response":\s*\{.*?"content":\s*"((?:[^"\\]|\\.)*)"', re.S)
_COST = re.compile(r'"cost":\s*\{[^}]*"total_price":\s*([0-9.eE+-]+)')


def fetch_published_verdict(run: Run, judge: str, cache: Path) -> dict | None:
    """A comparison judge's verdict and cost, from the first few KB of its file."""
    path = cache / "verdicts" / judge / f"{run.key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    for url in _candidates(run, judge):
        for size in (16_000, 64_000, None):
            r = _get(url, size)
            if r is None:
                break  # 404: try the next candidate id
            text = r.content.decode("utf-8", errors="replace")
            m = _RESP.search(text)
            if not m:
                continue  # response cut off; fetch more
            content = json.loads(f'"{m.group(1)}"')
            cost = _COST.search(text)
            out = {"verdict": parse_verdict(content), "cost_usd": float(cost.group(1)) if cost else None}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out), encoding="utf-8")
            return out
    return None


def _response_text(full: dict) -> str:
    try:
        return full["response"]["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ---------------------------------------------------------------- parsing the judge format

def _tag(text: str, name: str) -> str | None:
    m = re.findall(rf"<{name}>\s*(.*?)\s*</{name}>", text or "", re.S | re.I)
    return m[-1].strip() if m else None  # last one: some judges restate the choices first


def parse_verdict(text: str) -> dict:
    """Parse the benchmark's answer format. Missing or unrecognised answers become None."""
    s, side, opt, loop = (_tag(text, t) for t in ("success", "side", "optimal", "loop"))

    def yn(v):
        v = (v or "").lower()
        return True if v.startswith("yes") else False if v.startswith("no") else None

    sl = (s or "").lower()
    success = False if sl.startswith("unsuccess") else True if sl.startswith("success") else None
    m = re.match(r"\s*(\d)", opt or "")
    return {"success": success, "side_effect": yn(side), "looping": yn(loop),
            "optimal": int(m.group(1)) if m else None}
