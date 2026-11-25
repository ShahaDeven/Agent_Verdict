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
               workers: int = 6, cache_root=None) -> tuple[dict, list[str], int]:
    """Judge runs in parallel, reusing cached verdicts (never for dry runs). If the budget cap
    trips, finished results are kept and the rest skipped.
    Returns ({run_key: result}, [stop reason], number taken from cache)."""
    from concurrent.futures import ThreadPoolExecutor

    from ember_core.budget import BudgetExceeded

    from . import ember_cache

    use_cache = cache_root is not None and not client.dry_run
    out: dict = {}
    todo = []
    for r in runs:
        hit = ember_cache.load(cache_root, effort, long_side, r.key) if use_cache else None
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
            res = judge_run(client, inputs[r.key]["messages"], effort=effort, run_key=r.key,
                            long_side=long_side)
        except BudgetExceeded as e:
            stopped.append(str(e))
            return r.key, None
        if use_cache:
            ember_cache.save(cache_root, effort, long_side, r.key, res)
        return r.key, res

    with ThreadPoolExecutor(workers) as pool:
        out.update({k: v for k, v in pool.map(do, todo) if v is not None})
    return out, stopped, from_cache


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
