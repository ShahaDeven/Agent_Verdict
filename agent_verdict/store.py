"""Local SQLite store behind the review queue: runs, their verdicts, and people's review decisions.

Screenshots stay as image files on disk; the database keeps their paths (relative to the repo when
they are inside it). Default location: data/app/agent_verdict.db (gitignored).
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ember_core.ember import MODEL, REPO_ROOT

from .api import flag
from .trace import Trace

DEFAULT_DB = REPO_ROOT / "data" / "app" / "agent_verdict.db"
LATEST = "v.rowid = (SELECT MAX(rowid) FROM verdicts WHERE run_id = v.run_id)"  # one verdict per run: the newest

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    key           TEXT UNIQUE NOT NULL,     -- source-specific id, e.g. benchmark/agent/task
    source        TEXT NOT NULL,            -- 'agentrewardbench', 'generic', 'live'
    benchmark     TEXT, agent TEXT, task TEXT,
    goal          TEXT NOT NULL,
    steps_json    TEXT NOT NULL,            -- [{n, url, action, reasoning}]
    n_states      INTEGER NOT NULL,
    final_message TEXT,
    screens_json  TEXT NOT NULL,            -- {state index: image path}
    ref_success   INTEGER, ref_side_effect INTEGER, ref_looping INTEGER,  -- expert labels, benchmark runs only
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verdicts (
    run_id        INTEGER NOT NULL REFERENCES runs(id),
    judge         TEXT NOT NULL,            -- e.g. 'v2-minimal-f4'
    flag          TEXT NOT NULL,            -- yellow / green / red / blue
    success INTEGER, claimed_success INTEGER, failure_type TEXT,
    side_effect INTEGER, side_effect_detail TEXT, looping INTEGER,
    evidence_step INTEGER, evidence_screenshot TEXT, evidence_quote TEXT,
    confidence TEXT, needs_review INTEGER, reasoning TEXT,
    frames_json TEXT, cost_usd REAL, latency_s REAL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (run_id, judge)
);
CREATE TABLE IF NOT EXISTS reviews (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(id),
    decision      TEXT NOT NULL CHECK (decision IN ('agree', 'override')),
    success       INTEGER NOT NULL,          -- the person's final call
    failure_type  TEXT,
    note          TEXT,
    reviewer      TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verdicts_flag ON verdicts(flag);
CREATE INDEX IF NOT EXISTS reviews_run ON reviews(run_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _b(x):
    return None if x is None else int(bool(x))


def _rel(p: Path) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(p)


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.conn() as c:
            c.execute("PRAGMA journal_mode = WAL")  # persistent; makes each small commit cheap
            c.executescript(SCHEMA)
            self._migrate(c)

    @staticmethod
    def _migrate(c) -> None:
        """Bring an older database up to date in place (no data lost)."""
        have = {r["name"] for r in c.execute("PRAGMA table_info(verdicts)")}
        for col, typ in (("tokens_in", "INTEGER"), ("tokens_out", "INTEGER"), ("reasoning_tokens", "INTEGER"),
                         ("effort", "TEXT"), ("model", "TEXT")):
            if col not in have:
                c.execute(f"ALTER TABLE verdicts ADD COLUMN {col} {typ}")
        # Nov 27: looping became a secondary tag, not a flag; a looping run's flag is its outcome.
        c.execute("UPDATE verdicts SET flag = 'red' WHERE flag = 'blue'")

    @contextmanager
    def batch(self):
        """Run many writes in one transaction (one disk sync instead of one per write; matters on HDDs).
        Per thread, so the server's request threads never share it."""
        with self.conn() as c:
            self._local.tx = c
            try:
                yield
            finally:
                self._local.tx = None

    @contextmanager
    def conn(self):
        tx = getattr(self._local, "tx", None)
        if tx is not None:  # inside batch(): reuse its connection, commit once at the end
            yield tx
            return
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA synchronous = NORMAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ------------------------------------------------------------------ writes

    def add_run(self, key: str, trace: Trace, *, source: str, screens: dict[int, str | Path],
                benchmark: str | None = None, agent: str | None = None, task: str | None = None,
                reference: dict | None = None) -> int:
        """Insert or replace a run. screens: state index -> image file path. Returns the run id."""
        ref = reference or {}
        steps = [{"n": s.n, "url": s.url, "action": s.action, "reasoning": s.reasoning} for s in trace.steps]
        row = (key, source, benchmark, agent, task, trace.goal, json.dumps(steps), trace.n_states,
               trace.final_message, json.dumps({str(i): _rel(p) for i, p in screens.items()}),
               _b(ref.get("success")), _b(ref.get("side_effect")), _b(ref.get("looping")), _now())
        with self.conn() as c:
            c.execute("""INSERT INTO runs (key, source, benchmark, agent, task, goal, steps_json, n_states,
                         final_message, screens_json, ref_success, ref_side_effect, ref_looping, created_at)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(key) DO UPDATE SET goal=excluded.goal, steps_json=excluded.steps_json,
                         n_states=excluded.n_states, final_message=excluded.final_message,
                         screens_json=excluded.screens_json""", row)
            return c.execute("SELECT id FROM runs WHERE key = ?", (key,)).fetchone()["id"]

    def add_verdict(self, run_id: int, judge: str, result: dict) -> str:
        """Store a judge result (as returned by api.judge / judge_v2). Returns its flag."""
        v = result["verdict"]
        f = flag(v)
        m = re.match(r"v\d+-([a-z]+)-f\d+", judge)  # e.g. v2-minimal-f4 -> minimal
        with self.conn() as c:
            c.execute("""INSERT OR REPLACE INTO verdicts (run_id, judge, flag, success, claimed_success,
                         failure_type, side_effect, side_effect_detail, looping, evidence_step,
                         evidence_screenshot, evidence_quote, confidence, needs_review, reasoning,
                         frames_json, cost_usd, latency_s, created_at,
                         tokens_in, tokens_out, reasoning_tokens, effort, model)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (run_id, judge, f, _b(v.get("success")), _b(v.get("claimed_success")),
                       v.get("failure_type"), _b(v.get("side_effect")), v.get("side_effect_detail"),
                       _b(v.get("looping")), v.get("evidence_step"), v.get("evidence_screenshot"),
                       v.get("evidence_quote"), v.get("confidence"), _b(v.get("needs_review")),
                       v.get("reasoning"), json.dumps(result.get("frames", [])), result.get("cost_usd"),
                       result.get("latency_s"), _now(), result.get("prompt_tokens"),
                       result.get("completion_tokens"), result.get("reasoning_tokens"),
                       m.group(1) if m else None, MODEL))
        return f

    def add_review(self, run_id: int, decision: str, success: bool, *, failure_type: str | None = None,
                   note: str | None = None, reviewer: str | None = None) -> dict:
        if decision not in ("agree", "override"):
            raise ValueError("decision must be 'agree' or 'override'")
        with self.conn() as c:
            if not c.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone():
                raise KeyError(run_id)
            cur = c.execute("""INSERT INTO reviews (run_id, decision, success, failure_type, note, reviewer,
                               created_at) VALUES (?,?,?,?,?,?,?)""",
                            (run_id, decision, int(success), failure_type, note, reviewer, _now()))
            return dict(c.execute("SELECT * FROM reviews WHERE id = ?", (cur.lastrowid,)).fetchone())

    # ------------------------------------------------------------------ reads

    _LIST = """SELECT r.id, r.key, r.source, r.benchmark, r.agent, r.goal, r.n_states,
                      v.flag, v.success, v.failure_type, v.confidence, v.needs_review, v.side_effect,
                      v.looping, v.evidence_step, v.evidence_screenshot, v.evidence_quote, v.judge,
                      rv.decision AS review_decision, rv.success AS review_success
               FROM runs r JOIN verdicts v ON v.run_id = r.id AND v.rowid = (SELECT MAX(rowid) FROM verdicts WHERE run_id = v.run_id)
               LEFT JOIN reviews rv ON rv.id = (SELECT MAX(id) FROM reviews WHERE run_id = r.id)"""

    def queue(self, *, status: str = "to_review", flag_: str | None = None, benchmark: str | None = None,
              q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        """status: to_review (needs a person, not yet reviewed), reviewed, auto (decided by the judge), all."""
        where, args = [], []
        if status == "to_review":
            where.append("v.needs_review = 1 AND rv.id IS NULL")
        elif status == "reviewed":
            where.append("rv.id IS NOT NULL")
        elif status == "auto":
            where.append("v.needs_review = 0")
        elif status != "all":
            raise ValueError(f"unknown status {status}")
        if flag_:
            where.append("v.flag = ?")
            args.append(flag_)
        if benchmark:
            where.append("r.benchmark = ?")
            args.append(benchmark)
        if q:
            where.append("(r.goal LIKE ? OR r.key LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        sql = self._LIST + (" WHERE " + " AND ".join(where) if where else "")
        # least confident first: those are the most likely mistakes
        order = (" ORDER BY CASE v.confidence WHEN 'low' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
                 "v.success, r.id")
        with self.conn() as c:
            total = c.execute(f"SELECT COUNT(*) FROM ({sql})", args).fetchone()[0]
            rows = c.execute(sql + order + " LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total

    def run(self, run_id: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not r:
                return None
            verdicts = [dict(v) for v in c.execute("SELECT * FROM verdicts WHERE run_id = ? ORDER BY rowid",
                                                    (run_id,))]
            reviews = [dict(v) for v in c.execute("SELECT * FROM reviews WHERE run_id = ? ORDER BY id", (run_id,))]
        out = dict(r)
        out["steps"] = json.loads(out.pop("steps_json"))
        out["screens"] = sorted(int(i) for i in json.loads(out.pop("screens_json")))
        for v in verdicts:
            v["frames"] = json.loads(v.pop("frames_json") or "[]")
        out["verdict"] = verdicts[-1] if verdicts else None
        out["reviews"] = reviews
        return out

    def screen_path(self, run_id: int, state: int) -> Path | None:
        with self.conn() as c:
            r = c.execute("SELECT screens_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        p = r and json.loads(r["screens_json"]).get(str(state))
        return resolve(p) if p else None

    def summary(self) -> dict:
        """Counts for the header, and how reviews compare with the judge (and the experts, when known)."""
        with self.conn() as c:
            one = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
            flags = {r["flag"]: r["n"] for r in c.execute(f"SELECT flag, COUNT(*) n FROM verdicts v WHERE {LATEST} GROUP BY flag")}
            latest = f"""FROM runs r JOIN verdicts v ON v.run_id = r.id AND {LATEST}
                        JOIN reviews rv ON rv.id = (SELECT MAX(id) FROM reviews WHERE run_id = r.id)"""
            reviewed = one(f"SELECT COUNT(*) {latest}")
            overridden = one(f"SELECT COUNT(*) {latest} WHERE rv.decision = 'override'")
            judged = one(f"SELECT COUNT(*) FROM verdicts v WHERE {LATEST}")
            to_review = one(f"""SELECT COUNT(*) FROM verdicts v WHERE {LATEST} AND v.needs_review = 1 AND NOT EXISTS
                               (SELECT 1 FROM reviews rv WHERE rv.run_id = v.run_id)""")
            # benchmark runs only: is the judge right on what it decided alone?
            auto_ref = c.execute(f"""SELECT COUNT(*) n, SUM(v.success = r.ref_success) ok FROM runs r
                                    JOIN verdicts v ON v.run_id = r.id AND {LATEST}
                                    WHERE v.needs_review = 0 AND r.ref_success IS NOT NULL""").fetchone()
            cost = c.execute(f"SELECT AVG(cost_usd) FROM verdicts v WHERE {LATEST} AND cost_usd IS NOT NULL").fetchone()[0]
            # looping is a secondary tag; checked against the experts' loop labels where they exist
            loop = c.execute(f"""SELECT SUM(v.looping = 1) n, SUM(r.ref_looping = 1) expert_n,
                                        AVG(CASE WHEN r.ref_looping IS NOT NULL THEN v.looping = r.ref_looping END) agree
                                 FROM runs r JOIN verdicts v ON v.run_id = r.id AND {LATEST}""").fetchone()
            # people's decisions so far, and (benchmark runs) how they compare with the experts
            rev = c.execute(f"""SELECT COUNT(*) n, SUM(rv.success = r.ref_success) ok,
                                       SUM(r.ref_success IS NOT NULL) labelled
                                {latest}""").fetchone()
        auto_acc = (auto_ref["ok"] / auto_ref["n"]) if auto_ref["n"] else None
        # Accuracy with people in the loop: judge's own calls on what it decided + people's calls on the rest.
        with_people = None
        if auto_ref["n"] and rev["labelled"]:
            with_people = (auto_ref["ok"] + (rev["ok"] or 0)) / (auto_ref["n"] + rev["labelled"])
        return {
            "judged": judged, "to_review": to_review, "reviewed": reviewed, "overridden": overridden,
            "auto_decided": judged - flags.get("yellow", 0), "flags": flags,
            "auto_accuracy_vs_experts": auto_acc,
            "auto_runs_with_expert_label": auto_ref["n"],
            "accuracy_with_reviews": with_people, "reviewed_with_expert_label": rev["labelled"] or 0,
            "reviews_matching_experts": rev["ok"] or 0,
            "looped": loop["n"] or 0, "looped_by_experts": loop["expert_n"] or 0, "looping_agreement": loop["agree"],
            "cost_per_1000_runs": cost * 1000 if cost is not None else None,
        }

    def featured(self) -> int | None:
        """A run for the front page: one the judge sent to a person where the agent claimed success but failed
        (benchmark runs: the experts agree). Prefers short goals and a final-screen proof."""
        with self.conn() as c:
            r = c.execute(f"""SELECT r.id FROM runs r JOIN verdicts v ON v.run_id = r.id AND {LATEST}
                              WHERE v.success = 0 AND v.claimed_success = 1 AND r.final_message IS NOT NULL
                                AND v.failure_type IN ('false_completion', 'wrong_answer', 'wrong_target')
                                AND (r.ref_success IS NULL OR r.ref_success = 0)
                              ORDER BY v.needs_review DESC, r.ref_success IS NOT NULL DESC,
                                       v.failure_type = 'false_completion' DESC,
                                       v.evidence_screenshot = 'FINAL' DESC, LENGTH(r.goal), r.id
                              LIMIT 1""").fetchone()
        return r["id"] if r else None

    def recent(self, *, exclude_source: str = "agentrewardbench", limit: int = 30) -> list[dict]:
        """Newest runs from live sources (not the benchmark), with their newest verdict if judged yet."""
        with self.conn() as c:
            rows = c.execute(f"""SELECT r.id, r.key, r.source, r.agent, r.goal, r.final_message, r.n_states,
                                        r.created_at, v.flag, v.success, v.failure_type, v.looping, v.confidence,
                                        v.needs_review, v.cost_usd, v.latency_s, v.created_at AS judged_at
                                 FROM runs r LEFT JOIN verdicts v ON v.run_id = r.id AND {LATEST}
                                 WHERE r.source != ? ORDER BY r.id DESC LIMIT ?""",
                             (exclude_source, limit)).fetchall()
        return [dict(r) for r in rows]


def save_data_url(url: str, path_without_ext: Path) -> Path:
    """Write a data: URL image to disk (used for screenshots that arrive inline)."""
    head, b64 = url.split(",", 1)
    ext = ".jpg" if "jpeg" in head or "jpg" in head else ".png"
    p = path_without_ext.with_suffix(ext)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(b64))
    return p
