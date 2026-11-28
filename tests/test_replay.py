"""The replay bundle that ships in the repo plays back cleanly with no API key ($0)."""

from agent_verdict.replay import load_bundle, play
from agent_verdict.store import Store


def test_bundle_plays_back_into_a_fresh_store(tmp_path):
    runs = load_bundle()
    assert len(runs) >= 50 and sum(r["stream_order"] is not None for r in runs) == 8
    store = Store(tmp_path / "replay.db")
    n = play(store, judging_s=0, gap_s=0, log=lambda m: None)
    assert n == len(runs)
    s = store.summary()
    assert s["judged"] == len(runs) and s["to_review"] >= 1
    live = store.recent(limit=200)
    assert len(live) == len(runs) and all(x["flag"] for x in live)
    # every screenshot the bundle names is on disk, and the review screen can serve it
    for x in live[:10]:
        run = store.run(x["id"])
        assert run["screens"] and all(store.screen_path(run["id"], i).exists() for i in run["screens"])
    # the caught false claims are in it: the agent claimed success, the site's records say it failed, the judge said failed
    caught = [r for r in runs if r["reference"]["success"] is False and r["result"]["verdict"]["claimed_success"]
              and not r["result"]["verdict"]["success"]]
    assert len(caught) >= 3
    assert store.featured() is not None
