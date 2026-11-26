import base64
import io
import json

import pytest
from PIL import Image

from agent_verdict.arb_data import _RESP, load_runs, parse_verdict, sample_runs
from agent_verdict.ember_judge import _shrink_images
from agent_verdict.metrics import binary_scores

GOOD = ("<reasoning>The agent found it.</reasoning>\n<success>Successful</success>\n"
        "<side>No</side>\n<optimal>4. Completely Optimal</optimal>\n<loop>No</loop>")


def test_parse_full_verdict():
    assert parse_verdict(GOOD) == {"success": True, "side_effect": False, "looping": False, "optimal": 4}


def test_parse_uses_last_tag_when_choices_are_restated():
    text = "Choices: <success>Successful</success>, <success>Unsuccessful</success>\n<success>Unsuccessful</success>"
    assert parse_verdict(text)["success"] is False


def test_parse_missing_or_garbage_is_none():
    v = parse_verdict("I think it worked")
    assert v == {"success": None, "side_effect": None, "looping": None, "optimal": None}
    assert parse_verdict("<success>maybe</success>")["success"] is None


def test_response_regex_reads_partial_file_and_ignores_prompt_tags():
    content = GOOD.replace("\n", "\\n").replace('"', '\\"')
    partial = ('{"benchmark": "webarena", "cost": {"total_price": 0.016}, "response": {"id": "x", '
               '"choices": [{"message": {"content": "' + content + '"}}]}, "chat_messages": {"regular": '
               '[{"role": "system", "content": "Choices: <success>Successful</success>, <success>Unsucc')
    m = _RESP.search(partial)
    assert m and parse_verdict(json.loads(f'"{m.group(1)}"'))["success"] is True


def test_bootstrap_ci_brackets_the_point_estimate():
    from agent_verdict.metrics import bootstrap_ci
    gold = [True] * 10 + [False] * 30
    pred = [True] * 8 + [False] * 2 + [False] * 27 + [True] * 3
    acc = binary_scores(gold, pred)["accuracy"]
    lo, hi = bootstrap_ci(gold, pred, "accuracy", n_boot=500)
    assert lo <= acc <= hi and hi - lo < 0.4
    assert bootstrap_ci([], [], "accuracy") is None


def test_binary_scores():
    s = binary_scores([True, True, False, False, True], [True, False, True, False, None])
    assert (s["tp"], s["fp"], s["fn"], s["tn"], s["unparsed"]) == (1, 1, 1, 1, 1)
    assert s["precision"] == pytest.approx(0.5) and s["accuracy"] == pytest.approx(0.5)


def _write_csvs(tmp_path, rows):
    (tmp_path / "splits.csv").write_text("task_id,benchmark,split\nwa.1,webarena,dev\nwa.2,webarena,dev\n"
                                         "wa.3,webarena,test\n", encoding="utf-8")
    head = ("annotator_name,benchmark,task_id,model_name,exp_name,trajectory_success,"
            "trajectory_side_effect,trajectory_optimality,trajectory_looping\n")
    (tmp_path / "annotations.csv").write_text(head + "".join(rows), encoding="utf-8")


def test_load_runs_majority_and_ties(tmp_path):
    _write_csvs(tmp_path, [
        "A,webarena,wa.1,agentX,e,Successful,No,4. x,No\n",
        "B,webarena,wa.1,agentX,e,Successful,Yes,4. x,No\n",
        "C,webarena,wa.1,agentX,e,Unsuccessful,No,4. x,No\n",   # 2-1 -> Successful
        "A,webarena,wa.2,agentX,e,Successful,No,4. x,No\n",
        "B,webarena,wa.2,agentX,e,Unsuccessful,No,4. x,No\n",   # tie -> dropped
        "A,webarena,wa.3,agentY,e,Unsuccessful,No,1. x,Yes\n",
        "A,webarena,wa.9,agentY,e,Unsuccessful,No,1. x,Yes\n",  # no split -> dropped
    ])
    runs, dropped = load_runs(tmp_path)
    by = {r.task_id: r for r in runs}
    assert by["wa.1"].success is True and by["wa.1"].n_annotators == 3 and by["wa.1"].side_effect is False
    assert "wa.2" not in by and dropped == {"tie_or_unsure": 1, "no_split": 1}
    assert by["wa.3"].split == "test" and by["wa.3"].looping is True
    assert [r.task_id for r in sample_runs(runs, "dev", 5)] == ["wa.1"]


def test_rate_limit_wait_reads_huggingface_headers():
    from types import SimpleNamespace as NS
    from agent_verdict.arb_data import _reset_wait
    assert _reset_wait(NS(headers={"RateLimit": '"resolvers";r=0;t=283'}), 0) == 285
    assert _reset_wait(NS(headers={"Retry-After": "10"}), 0) == 11
    assert _reset_wait(NS(headers={}), 2) == 20


def test_split_key_maps_renamed_benchmark_ids():
    from agent_verdict.arb_data import _split_key
    assert _split_key("visualwebarena.resized.102") == "visualwebarena.102"
    assert _split_key("assistantbench.improved.validation.4") == "assistantbench.validation.4"
    assert _split_key("webarena.100") == "webarena.100"


def test_shrink_images_downscales_and_keeps_text():
    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), "white").save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    msgs = [{"role": "user", "content": [{"type": "text", "text": "goal"},
                                         {"type": "image_url", "image_url": {"url": url}}]}]
    out = _shrink_images(msgs, 640)
    raw = base64.b64decode(out[0]["content"][1]["image_url"]["url"].split(",", 1)[1])
    assert Image.open(io.BytesIO(raw)).size == (640, 360) and out[0]["content"][0]["text"] == "goal"
    assert _shrink_images(msgs, 0) is msgs
