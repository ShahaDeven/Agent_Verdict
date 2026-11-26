"""Never pay twice for the same Ember verdict.

Each judgment is stored under data/arb/cache/ember/<effort>_<long_side>/<run key>.json. Any script
that judges runs checks the cache first and only calls Ember for what's missing. Verdicts from
earlier real reports in results/ are imported on first use, so runs paid for before this cache
existed are reused too. Dry runs are never cached.
"""

from __future__ import annotations

import json
from pathlib import Path


def _path(root: Path, effort: str, long_side: int, key: str) -> Path:
    return root / f"{effort}_{long_side or 0}" / f"{key}.json"


def _retryable(res: dict) -> bool:
    """A temporary failure (API error, unparseable answer): never served from the cache, so a rerun
    retries it. Content-filter blocks are permanent and stay cached."""
    return bool(res.get("error")) and not res.get("blocked")


def load(root: Path, effort: str, long_side: int, key: str) -> dict | None:
    p = _path(root, effort, long_side, key)
    if not p.exists():
        return None
    res = json.loads(p.read_text(encoding="utf-8"))
    return None if _retryable(res) else res


def save(root: Path, effort: str, long_side: int, key: str, result: dict) -> None:
    p = _path(root, effort, long_side, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result), encoding="utf-8")


def ingest_reports(results_dir: Path, root: Path) -> int:
    """Import verdicts from earlier real judge_probe / effort_sweep reports. Returns how many were new."""
    added = 0
    for rep_path in sorted(results_dir.glob("*/report.json")):
        if rep_path.parent.name.startswith("dry_run"):
            continue
        try:
            rep = json.loads(rep_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        args = rep.get("args", {})
        if args.get("dry_run"):
            continue
        long_side = args.get("long_side") or 0
        for run in rep.get("runs", []):
            ember = run.get("ember")
            if not ember:
                continue
            # judge_probe stores one result; effort_sweep stores {effort: result}
            per_effort = {args.get("effort"): ember} if "verdict" in ember else ember
            for effort, res in per_effort.items():
                if (effort and res and "verdict" in res and not _retryable(res)
                        and load(root, effort, long_side, run["key"]) is None):
                    save(root, effort, long_side, run["key"], res)
                    added += 1
    return added
