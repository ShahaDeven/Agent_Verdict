"""Muse Ember as the judge: same prompt the published judges received, same answer format."""

from __future__ import annotations

import base64
import io
import json

from PIL import Image

from ember_core.ember import EmberClient

from .arb_data import parse_verdict


def _shrink_images(messages: list[dict], long_side: int) -> list[dict]:
    """Optionally downscale screenshots (fewer image tokens). 0 keeps the originals, which is what
    the published judges saw."""
    if not long_side:
        return messages
    out = json.loads(json.dumps(messages))
    for m in out:
        if isinstance(m.get("content"), list):
            for part in m["content"]:
                if part.get("type") == "image_url" and part["image_url"]["url"].startswith("data:"):
                    raw = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
                    img = Image.open(io.BytesIO(raw)).convert("RGB")
                    if max(img.size) > long_side:
                        s = long_side / max(img.size)
                        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    part["image_url"]["url"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return out


def judge_many(client: EmberClient, runs: list, inputs: dict, *, effort: str, long_side: int = 0,
               workers: int = 6, cache_root=None, judge_fn=None, variant: str | None = None
               ) -> tuple[dict, list[str], int]:
    """Judge runs in parallel, reusing cached verdicts (never for dry runs). If the budget cap
    trips, finished results are kept and the rest skipped.

    judge_fn(run) -> result overrides the default v1 judge (the benchmark prompt); variant names the
    cache folder for it (e.g. "v2-minimal-f4"), so different judges never share cached verdicts.
    Returns ({run_key: result}, [stop reason], number taken from cache)."""
    from concurrent.futures import ThreadPoolExecutor

    from ember_core.budget import BudgetExceeded

    from . import ember_cache

    use_cache = cache_root is not None and not client.dry_run
    slot = variant or effort
    if judge_fn is None:
        def judge_fn(r):
            return judge_run(client, inputs[r.key]["messages"], effort=effort, run_key=r.key,
                             long_side=long_side)
    out: dict = {}
    todo = []
    for r in runs:
        hit = ember_cache.load(cache_root, slot, long_side, r.key) if use_cache else None
        if hit is not None:
            out[r.key] = hit
        else:
            todo.append(r)
    from_cache = len(out)
    stopped: list[str] = []

    def do(r):
        if stopped:
            return r.key, None
        try:
            res = judge_fn(r)
        except BudgetExceeded as e:
            stopped.append(str(e))
            return r.key, None
        except Exception as e:  # one bad run must never sink the whole batch
            res = error_result(e)
            if not res["blocked"]:
                return r.key, res  # transient: not cached, so a rerun retries it
        if res.get("error") and not res.get("blocked"):
            return r.key, res  # e.g. unparseable answer: don't cache, retry next time
        if use_cache:
            ember_cache.save(cache_root, slot, long_side, r.key, res)
        return r.key, res

    with ThreadPoolExecutor(workers) as pool:
        out.update({k: v for k, v in pool.map(do, todo) if v is not None})
    return out, stopped, from_cache


def error_result(e: Exception) -> dict:
    """A run Ember did not judge. Content-policy blocks are permanent (cached, reported, and excluded
    from every judge's row); anything else is transient (not cached, retried on the next run)."""
    msg = str(e)
    blocked = "content_policy" in msg or "content management policy" in msg
    return {"verdict": {"success": None, "side_effect": None, "looping": None, "optimal": None},
            "raw": "", "truncated": False, "blocked": blocked, "error": msg[:300],
            "finish_reason": "content_filter" if blocked else "error", "cost_usd": 0.0, "latency_s": 0.0,
            "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}


def judged_ok(res: dict | None) -> bool:
    """True when Ember produced a usable verdict (not missing, truncated, blocked or errored)."""
    return bool(res) and not res.get("truncated") and not res.get("error")


def judge_run(client: EmberClient, messages: list[dict], *, effort: str, run_key: str,
              long_side: int = 0, max_completion_tokens: int = 3072) -> dict:
    msgs = _shrink_images(messages, long_side)
    res = client.chat(msgs, tag="arb_judge", reasoning_effort=effort,
                      max_completion_tokens=max_completion_tokens, prompt_cache_key="arb-judge",
                      meta={"run": run_key, "effort": effort, "long_side": long_side})
    text = res.message.content or ""
    return {"verdict": parse_verdict(text), "raw": text, "truncated": res.finish_reason == "length",
            "finish_reason": res.finish_reason, "cost_usd": res.cost, "latency_s": res.latency_s,
            "prompt_tokens": res.usage.prompt_tokens, "completion_tokens": res.usage.completion_tokens,
            "reasoning_tokens": res.usage.reasoning_tokens}
