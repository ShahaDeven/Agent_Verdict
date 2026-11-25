import json
from types import SimpleNamespace as NS

from agent_verdict import ember_cache
from agent_verdict import ember_judge

RES = {"verdict": {"success": True, "side_effect": False, "looping": False, "optimal": 4},
       "raw": "x", "truncated": False, "cost_usd": 0.001}


def _report(dirpath, args, runs):
    dirpath.mkdir(parents=True)
    (dirpath / "report.json").write_text(json.dumps({"args": args, "runs": runs}))


def test_ingest_reads_both_report_formats_and_skips_dry_runs(tmp_path):
    results, root = tmp_path / "results", tmp_path / "cache"
    _report(results / "judge_probe_1", {"effort": "low", "long_side": 0, "dry_run": False},
            [{"key": "wa/A/t1", "ember": RES}, {"key": "wa/A/t2", "ember": None}])
    _report(results / "effort_sweep_1", {"dry_run": False},
            [{"key": "wa/A/t1", "ember": {"minimal": RES, "medium": None}}])
    _report(results / "dry_run_judge_1", {"effort": "low", "dry_run": True}, [{"key": "wa/A/t9", "ember": RES}])
    assert ember_cache.ingest_reports(results, root) == 2
    assert ember_cache.load(root, "low", 0, "wa/A/t1") == RES
    assert ember_cache.load(root, "minimal", 0, "wa/A/t1") == RES
    assert ember_cache.load(root, "low", 0, "wa/A/t9") is None
    assert ember_cache.ingest_reports(results, root) == 0  # idempotent


class _CountingClient:
    dry_run = False

    def __init__(self):
        self.calls = 0


def test_judge_many_uses_cache_and_only_pays_for_missing(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    ember_cache.save(root, "low", 0, "k1", RES)
    client = _CountingClient()

    def fake_judge_run(c, messages, **kw):
        c.calls += 1
        return {**RES, "raw": "new"}
    monkeypatch.setattr(ember_judge, "judge_run", fake_judge_run)
    runs = [NS(key="k1"), NS(key="k2")]
    inputs = {"k1": {"messages": []}, "k2": {"messages": []}}
    out, stopped, hits = ember_judge.judge_many(client, runs, inputs, effort="low", cache_root=root)
    assert hits == 1 and client.calls == 1 and out["k1"]["raw"] == "x" and out["k2"]["raw"] == "new"
    assert ember_cache.load(root, "low", 0, "k2")["raw"] == "new" and not stopped


def test_dry_run_never_reads_or_writes_cache(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    ember_cache.save(root, "low", 0, "k1", RES)
    client = _CountingClient()
    client.dry_run = True
    monkeypatch.setattr(ember_judge, "judge_run", lambda c, m, **kw: {**RES, "raw": "mock"})
    out, _, hits = ember_judge.judge_many(client, [NS(key="k1"), NS(key="k3")],
                                          {"k1": {"messages": []}, "k3": {"messages": []}},
                                          effort="low", cache_root=root)
    assert hits == 0 and out["k1"]["raw"] == "mock"
    assert ember_cache.load(root, "low", 0, "k3") is None
