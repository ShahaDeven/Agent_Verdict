import base64
import io
import json

import pytest
from PIL import Image

from agent_verdict.metrics import paired_bootstrap
from agent_verdict.trace import from_arb_messages, from_generic
from agent_verdict.verdict_v2 import SCHEMA, build_messages, label, normalize, select_states

ARB_ACTIONS = ("The agent performed the following actions:\n-----\nStep: 1\nURL: http://a/\n"
               "Action: fill('145', 'Carnegie Mellon')\nReasoning: search first-----\nStep: 2\nURL: http://a/s\n"
               "Action: send_msg_to_user('It is 7 hours.')\nReasoning: I saw 7h-----\nStep: 3\nURL: http://a/s\n"
               "Action: None\nReasoning: None\n-----")
ARB = [{"role": "system", "content": "judge"},
       {"role": "user", "content": [
           {"type": "text", "text": "The user goal is: How long is the drive?\n\n"},
           {"type": "text", "text": ARB_ACTIONS},
           {"type": "text", "text": "Here is the screenshot of the last step."},
           {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
           {"type": "text", "text": "Provide your reasoning..."}]}]


def test_parse_arb_prompt():
    t = from_arb_messages(ARB)
    assert t.goal == "How long is the drive?"
    assert [s.n for s in t.steps] == [1, 2, 3] and t.steps[1].url == "http://a/s"
    assert t.steps[0].action == "fill('145', 'Carnegie Mellon')" and t.steps[0].reasoning == "search first"
    assert t.final_screenshot == "data:image/png;base64,AAAA" and t.n_states == 3
    assert t.final_message == "It is 7 hours."


def test_from_generic_with_files(tmp_path):
    for name in ("a.png", "b.png", "end.png"):
        Image.new("RGB", (20, 10), "white").save(tmp_path / name)
    t = from_generic({"goal": "Buy milk", "steps": [
        {"action": "click('cart')", "reasoning": "add", "url": "http://shop/", "screenshot": "a.png"},
        {"action": "send_msg_to_user('done')", "reasoning": "ok", "url": "http://shop/cart", "screenshot": "b.png"}],
        "final_screenshot": "end.png"}, tmp_path)
    assert t.n_states == 3 and set(t.screenshots) == {0, 1, 2}
    assert t.final_screenshot == t.screenshots[2] and t.final_screenshot.startswith("data:image/png;base64,")
    assert t.steps[-1].action == "None" and t.final_message == "done"


@pytest.mark.parametrize("n,frames,expected", [
    (1, 4, [0]), (2, 4, [0, 1]), (13, 4, [6, 10, 11, 12]), (13, 1, [12]), (5, 4, [0, 2, 3, 4]), (0, 4, [])])
def test_select_states_always_includes_final(n, frames, expected):
    assert select_states(n, frames) == expected


def test_labels():
    assert label(12, 13) == "FINAL" and label(10, 13) == "S11"


def _png_url():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_build_messages_labels_each_screenshot():
    t = from_arb_messages(ARB)
    url = _png_url()
    msgs = build_messages(t, {1: url, 2: url})
    parts = msgs[1]["content"]
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert sum(p["type"] == "image_url" for p in parts) == 2
    texts = " ".join(p.get("text", "") for p in parts)
    assert "Screenshot S2" in texts and "Screenshot FINAL" in texts and "Step 2 | URL: http://a/s" in texts


def _verdict(**over):
    v = {"reasoning": "r", "claimed_success": True, "success": False, "failure_type": "false_completion",
         "side_effect": False, "side_effect_detail": "", "looping": False, "evidence_step": 2,
         "evidence_screenshot": "FINAL", "evidence_quote": "no order", "confidence": "medium", "needs_review": False}
    v.update(over)
    return json.dumps(v)


def test_normalize_keeps_verdict_consistent():
    v = normalize(_verdict(success=True, failure_type="false_completion"), {"FINAL"})
    assert v["failure_type"] == "none"
    v = normalize(_verdict(success=False, failure_type="none"), {"FINAL"})
    assert v["failure_type"] == "other"
    v = normalize(_verdict(confidence="low", needs_review=False, evidence_screenshot="S99"), {"FINAL"})
    assert v["needs_review"] is True and v["evidence_screenshot"] == ""
    assert normalize(_verdict(confidence="medium", needs_review=False), {"FINAL"})["needs_review"] is True
    assert normalize(_verdict(confidence="high", needs_review=False), {"FINAL"})["needs_review"] is False


def test_normalize_rejects_bad_output():
    with pytest.raises(ValueError):
        normalize(_verdict(confidence="very"), {"FINAL"})
    with pytest.raises(ValueError):
        normalize(json.dumps({"success": True}), {"FINAL"})


def test_schema_requires_every_field():
    s = SCHEMA["json_schema"]["schema"]
    assert set(s["required"]) == set(s["properties"]) and s["additionalProperties"] is False


def test_paired_bootstrap_detects_a_real_difference():
    gold = [True] * 50 + [False] * 150
    good = gold[:]                       # perfect judge
    bad = [not g for g in gold[:40]] + gold[40:]  # 40 errors
    d = paired_bootstrap(gold, good, bad, "accuracy", n_boot=300)
    assert d["diff"] == pytest.approx(0.2) and d["significant"]
    same = paired_bootstrap(gold, good, good, "accuracy", n_boot=100)
    assert same["diff"] == 0 and not same["significant"]
