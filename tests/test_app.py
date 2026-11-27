"""Library, store, backend and command. Everything runs on mock Ember with temporary files: $0."""

import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agent_verdict import api, cli
from agent_verdict.server import create_app
from agent_verdict.store import Store


def _png(path=None, color="white"):
    img = Image.new("RGB", (16, 12), color)
    if path:
        img.save(path)
        return path
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _generic(tmp_path):
    for n in ("a.png", "b.png", "end.png"):
        _png(tmp_path / n)
    run = {"goal": "Order one blue mug", "steps": [
        {"action": "click('blue mug')", "reasoning": "open it", "url": "http://shop/", "screenshot": "a.png"},
        {"action": "send_msg_to_user('Ordered.')", "reasoning": "done", "url": "http://shop/cart",
         "screenshot": "b.png"}], "final_screenshot": "end.png"}
    p = tmp_path / "run.json"
    p.write_text(json.dumps(run))
    return p


def _verdict(**over):
    v = {"success": False, "claimed_success": True, "failure_type": "false_completion", "side_effect": False,
         "side_effect_detail": "", "looping": False, "evidence_step": 2, "evidence_screenshot": "FINAL",
         "evidence_quote": "cart is empty", "confidence": "medium", "needs_review": True, "reasoning": "r"}
    v.update(over)
    return {"verdict": v, "cost_usd": 0.0009, "latency_s": 1.2, "frames": ["S2", "FINAL"]}


@pytest.mark.parametrize("over,expected", [
    ({"needs_review": True, "success": True}, "yellow"), ({"needs_review": False, "success": True}, "green"),
    ({"needs_review": False, "looping": True}, "red"), ({"needs_review": False}, "red")])
def test_flags(over, expected):
    assert api.flag(_verdict(**over)["verdict"]) == expected


def test_load_trace_and_pick_screenshots(tmp_path):
    t = api.load_trace(_generic(tmp_path))
    assert t.goal == "Order one blue mug" and t.n_states == 3
    assert sorted(api.pick_screenshots(t, 4)) == [0, 1, 2]
    assert sorted(api.pick_screenshots(t, 1)) == [2]
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": 1}')
    with pytest.raises(ValueError):
        api.load_trace(bad)


def test_judge_dry_run_writes_only_the_dry_ledger(tmp_path):
    t = api.load_trace(_generic(tmp_path))
    client = api.make_client(dry_run=True, ledger_path=tmp_path / "dry.jsonl")
    res = api.judge(t, client=client)
    assert "verdict" in res and not res.get("error")
    assert (tmp_path / "dry.jsonl").exists()


def test_store_queue_review_and_summary(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    t = api.load_trace(_generic(tmp_path))
    shot = _png(tmp_path / "s.png")
    a = s.add_run("k/a", t, source="generic", screens={2: shot}, reference={"success": False})
    b = s.add_run("k/b", t, source="generic", screens={})
    s.add_verdict(a, "v2", _verdict(confidence="low"))
    s.add_verdict(b, "v2", _verdict(needs_review=False, confidence="high", success=True, failure_type="none"))
    rows, total = s.queue()
    assert total == 1 and rows[0]["id"] == a and rows[0]["flag"] == "yellow"
    assert s.queue(status="auto")[1] == 1 and s.queue(status="all")[1] == 2
    s.add_review(a, "agree", False, note="cart was empty")
    assert s.queue()[1] == 0 and s.queue(status="reviewed")[0][0]["review_decision"] == "agree"
    # a newer verdict replaces the old one everywhere (no duplicate rows)
    s.add_verdict(b, "v2-dryrun", _verdict(needs_review=False, confidence="high"))
    assert s.queue(status="all")[1] == 2 and s.run(b)["verdict"]["judge"] == "v2-dryrun"
    summ = s.summary()
    assert summ["judged"] == 2 and summ["reviewed"] == 1 and summ["to_review"] == 0
    assert s.screen_path(a, 2) == shot.resolve() and s.screen_path(a, 0) is None
    with pytest.raises(ValueError):
        s.add_review(a, "maybe", True)
    # front-page preview: a flagged "claimed done, but failed" run; live list: non-benchmark runs, newest first
    assert s.featured() == a
    assert [r["id"] for r in s.recent()] == [b, a]
    # Ember details are stored with each verdict
    s.add_verdict(a, "v2-minimal-f4", {**_verdict(), "prompt_tokens": 7000, "completion_tokens": 300})
    v = s.run(a)["verdict"]
    assert v["tokens_in"] == 7000 and v["effort"] == "minimal" and v["model"] == "muse-ember-1.0"


def test_old_blue_flags_migrate_to_red(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    t = api.load_trace(_generic(tmp_path))
    rid = s.add_run("k/a", t, source="generic", screens={})
    s.add_verdict(rid, "v2", _verdict(needs_review=False, looping=True))
    with s.conn() as c:
        c.execute("UPDATE verdicts SET flag = 'blue'")
    assert Store(tmp_path / "db.sqlite").run(rid)["verdict"]["flag"] == "red"


def test_api_end_to_end_on_mock(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    t = api.load_trace(_generic(tmp_path))
    rid = store.add_run("k/a", t, source="generic", screens={2: _png(tmp_path / "s.png")})
    store.add_verdict(rid, "v2", _verdict())
    off = TestClient(create_app(store))
    assert off.get("/api/summary").json()["judging_enabled"] is False
    assert off.post(f"/api/runs/{rid}/judge").status_code == 403  # no spending unless allowed
    q = off.get("/api/queue").json()
    assert q["total"] == 1 and q["items"][0]["goal"] == "Order one blue mug"
    run = off.get(f"/api/runs/{rid}").json()
    assert run["screens"] == [2] and run["verdict"]["evidence_screenshot"] == "FINAL" and len(run["steps"]) == 3
    assert off.get(f"/api/runs/{rid}/screens/2").status_code == 200
    assert off.get(f"/api/runs/{rid}/screens/0").status_code == 404
    assert off.get("/api/runs/999").status_code == 404
    r = off.post(f"/api/runs/{rid}/review", json={"decision": "override", "success": True, "note": "it did order"})
    assert r.status_code == 200 and off.get("/api/queue").json()["total"] == 0
    assert off.post(f"/api/runs/{rid}/review", json={"decision": "agree", "success": True,
                                                    "failure_type": "nope"}).status_code == 422

    mock = TestClient(create_app(store, dry_run=True, ledger_path=tmp_path / "dry.jsonl"))
    new = mock.post("/api/runs", json={"key": "live/1", "goal": "Book a table", "steps": [
        {"action": "click('book')", "reasoning": "x", "url": "http://b/", "screenshot": _png()}],
        "final_screenshot": _png(color="black")})
    assert new.status_code == 200
    nid = new.json()["id"]
    judged = mock.post(f"/api/runs/{nid}/judge").json()
    assert judged["verdict"]["judge"].endswith("-dryrun") and judged["screens"] == [0, 1]
    assert mock.post("/api/runs", json={"key": "x", "goal": "g", "steps": []}).status_code == 422


def test_cli_judge_dry_run(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(api, "make_client", lambda **kw: api.EmberClient(
        api.Ledger(tmp_path / "dry.jsonl", session_cap_usd=kw.get("max_usd")), dry_run=True))
    rc = cli.main(["judge", str(_generic(tmp_path)), "--dry-run", "--json"])
    out = capsys.readouterr().out
    assert rc == 0 and json.loads(out[out.index("["):])[0]["flag"] in api.FLAGS
