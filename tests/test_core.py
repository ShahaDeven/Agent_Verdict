import json

import pytest
from PIL import Image

from ember_core.budget import BudgetExceeded, Ledger
from ember_core.ember import EmberClient, estimate_image_tokens, estimate_input_tokens
from ember_core.pricing import Usage, cost_usd, usage_from_response, worst_case_cost


def test_cost_uses_cached_rate_for_cached_tokens():
    # stays under the 200K long-context threshold, so standard rates apply
    u = Usage(prompt_tokens=100_000, cached_tokens=60_000, completion_tokens=10_000)
    assert cost_usd(u) == pytest.approx((40_000 * 0.10 + 60_000 * 0.004 + 10_000 * 0.50) / 1e6)


def test_long_context_rates_apply_to_whole_request():
    assert cost_usd(Usage(prompt_tokens=300_000)) == pytest.approx(0.3 * 0.30)


def test_worst_case_assumes_nothing_cached():
    assert worst_case_cost(10_000, 2_000) == pytest.approx((10_000 * 0.10 + 2_000 * 0.50) / 1e6)


def test_usage_from_dict_and_missing_details():
    assert usage_from_response({"usage": {"prompt_tokens": 50, "completion_tokens": 7}}) == Usage(50, 0, 7, 0)


def test_ledger_refuses_call_that_would_pass_cap(tmp_path):
    led = Ledger(tmp_path / "log.jsonl", cap_usd=1.0)
    led.record({"cost_usd": 0.95})
    with pytest.raises(BudgetExceeded):
        with led.reserve(0.10):
            pass


def test_ledger_counts_in_flight_reservations(tmp_path):
    led = Ledger(tmp_path / "log.jsonl", cap_usd=1.0)
    with led.reserve(0.6):
        with pytest.raises(BudgetExceeded):
            with led.reserve(0.6):
                pass
    with led.reserve(0.6):
        pass


def test_ledger_reads_prior_spend_and_session_cap(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_text(json.dumps({"cost_usd": 2.5}) + "\n" + json.dumps({"cost_usd": 0.5}) + "\n")
    led = Ledger(p, cap_usd=7.0, session_cap_usd=0.2)
    assert led.prior_spent == pytest.approx(3.0)
    with pytest.raises(BudgetExceeded):
        with led.reserve(0.25):
            pass


def test_ledger_rejects_corrupt_file(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_text("not json\n")
    with pytest.raises(ValueError):
        Ledger(p)


def test_image_estimate_is_conservative_and_grows():
    assert estimate_image_tokens(1280, 1280) >= 3000
    assert estimate_image_tokens(384, 384) < estimate_image_tokens(1024, 1024)


def test_input_estimate_counts_data_url_images():
    import base64, io
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    msgs = [{"role": "user", "content": [{"type": "text", "text": "hi"},
                                         {"type": "image_url", "image_url": {"url": url}}]}]
    assert estimate_input_tokens(msgs) >= estimate_image_tokens(800, 600)


def test_dry_run_client_logs_and_fills_schema(tmp_path):
    led = Ledger(tmp_path / "log.jsonl", cap_usd=1.0)
    client = EmberClient(led, dry_run=True)
    res = client.chat([{"role": "user", "content": "hello"}], tag="t")
    assert res.message.content == "OK" and res.finish_reason == "stop" and res.cost > 0
    schema = {"type": "json_schema", "json_schema": {"name": "x", "schema": {
        "type": "object", "properties": {"flag": {"type": "boolean"}, "kind": {"type": "string", "enum": ["a", "b"]}}}}}
    res = client.chat([{"role": "user", "content": "hi"}], tag="t", response_format=schema)
    assert json.loads(res.message.content) == {"flag": False, "kind": "a"}
    line = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])
    assert line["dry_run"] is True and line["reasoning_effort"] == "low" and line["finish_reason"] == "stop"
