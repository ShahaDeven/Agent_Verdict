"""Muse Ember client: every call goes through the budget ledger.

Facts from dev.meta.ai docs (2026-11-24):
- OpenAI-compatible at https://api.meta.ai/v1, model "muse-ember-1.0", key in MODEL_API_KEY.
- reasoning_effort defaults to "max" on Ember, and reasoning tokens bill as output, so we always
  set it explicitly. "none" is rejected.
- Images are only read from user-role messages. Prompt caching is automatic on stable prefixes.
- tool_choice only accepts "auto".
"""

from __future__ import annotations

import base64
import io
import json
import os
import random
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

from PIL import Image

from .budget import Ledger
from .pricing import Usage, cost_usd, usage_from_response, worst_case_cost

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-ember-1.0"
REPO_ROOT = Path(__file__).resolve().parents[1]


def load_api_key() -> str | None:
    key = os.environ.get("MODEL_API_KEY")
    if key:
        return key
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "MODEL_API_KEY" and value.strip():
                return value.strip().strip('"').strip("'")
    return None


# ---------------------------------------------------------------- token estimates (for reservation)

def estimate_image_tokens(width: int, height: int) -> int:
    """Deliberately high upper bound. Meta's docs (measured on Muse Spark) put a ~1280px image at
    ~1,300-1,500 tokens and say cost scales with resolution. We double that. The probe's
    calibration step replaces this guess with measured numbers."""
    return int(200 + 2 * 1500 * (width * height) / (1280 * 1280))


def _image_size(url: str) -> tuple[int, int]:
    if url.startswith("data:"):
        raw = base64.b64decode(url.split(",", 1)[1])
        return Image.open(io.BytesIO(raw)).size
    return (2048, 2048)  # remote URL: assume large


def estimate_input_tokens(messages: list[dict], tools=None, response_format=None) -> int:
    chars, img_tokens = 0, 0
    for m in messages:
        chars += 40
        content = m.get("content")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    chars += len(part.get("text", ""))
                elif part.get("type") == "image_url":
                    img_tokens += estimate_image_tokens(*_image_size(part["image_url"]["url"]))
        for tc in m.get("tool_calls") or []:
            chars += len(json.dumps(tc))
    if tools:
        chars += len(json.dumps(tools))
    if response_format:
        chars += len(json.dumps(response_format))
    return int(chars / 3) + img_tokens  # ~3 chars/token is pessimistic for English


# ---------------------------------------------------------------- client

class ChatResult(NamedTuple):
    message: Any
    usage: Usage
    cost: float
    # "stop", "tool_calls", or "length" (hit max_completion_tokens: the answer or tool call
    # may be cut off; with reasoning on, the model can spend the whole budget thinking).
    finish_reason: str | None
    latency_s: float


class EmberClient:
    def __init__(self, ledger: Ledger, dry_run: bool = False, api_key: str | None = None,
                 timeout_s: float = 120.0):
        self.ledger = ledger
        self.dry_run = dry_run
        if dry_run:
            self._client = MockOpenAI()
        else:
            from openai import OpenAI
            key = api_key or load_api_key()
            if not key:
                raise RuntimeError("MODEL_API_KEY is not set (env var or .env). Use --dry-run to test without it.")
            # max_retries=0: we retry ourselves so every attempt is reserved and logged.
            self._client = OpenAI(base_url=BASE_URL, api_key=key, max_retries=0, timeout=timeout_s)

    def chat(self, messages: list[dict], *, tag: str, tools: list | None = None,
             response_format: dict | None = None, max_completion_tokens: int = 1024,
             reasoning_effort: str = "low", prompt_cache_key: str | None = None,
             meta: dict | None = None):
        """Returns a ChatResult. Raises BudgetExceeded before sending if over cap."""
        import openai

        est_in = estimate_input_tokens(messages, tools, response_format)
        worst = worst_case_cost(est_in, max_completion_tokens)
        kwargs = dict(model=MODEL, messages=messages, max_completion_tokens=max_completion_tokens,
                      reasoning_effort=reasoning_effort)
        if tools:
            kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
        if response_format:
            kwargs["response_format"] = response_format
        if prompt_cache_key:
            kwargs["prompt_cache_key"] = prompt_cache_key

        base = dict(tag=tag, model=MODEL, dry_run=self.dry_run, reasoning_effort=reasoning_effort,
                    est_input_tokens=est_in, reserved_usd=round(worst, 6), meta=meta or {})
        for attempt in range(5):
            wait = None
            with self.ledger.reserve(worst):
                t0 = time.perf_counter()
                try:
                    resp = self._client.chat.completions.create(**kwargs)
                except (openai.RateLimitError, openai.InternalServerError) as e:
                    self.ledger.record({**base, "status": f"retry:{type(e).__name__}", "cost_usd": 0.0})
                    retry_after = _retry_after(e)
                    wait = retry_after if retry_after else 0.5 * 2 ** attempt + random.random() * 0.5
                except (openai.APITimeoutError, openai.APIConnectionError) as e:
                    # The request may have been processed and billed; assume the worst.
                    self.ledger.record({**base, "status": f"assumed_billed:{type(e).__name__}",
                                        "cost_usd": worst})
                    raise
                except openai.APIStatusError as e:
                    self.ledger.record({**base, "status": f"error:{e.status_code}", "cost_usd": 0.0,
                                        "error": str(e)[:300]})
                    raise
                else:
                    latency = round(time.perf_counter() - t0, 3)
                    usage = usage_from_response(resp)
                    cost = cost_usd(usage)
                    choice = resp.choices[0]
                    finish = getattr(choice, "finish_reason", None)
                    self.ledger.record({
                        **base, "status": "ok", "finish_reason": finish, "latency_s": latency,
                        "prompt_tokens": usage.prompt_tokens, "cached_tokens": usage.cached_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "reasoning_tokens": usage.reasoning_tokens, "cost_usd": cost,
                    })
                    return ChatResult(choice.message, usage, cost, finish, latency)
            time.sleep(wait)
        raise RuntimeError(f"{tag}: gave up after 5 attempts (rate limit / server errors)")


def _retry_after(e) -> float | None:
    try:
        return float(e.response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


def assistant_to_dict(msg) -> dict:
    """Turn an SDK assistant message into the dict we send back on the next turn."""
    out = {"role": "assistant", "content": msg.content}
    if getattr(msg, "tool_calls", None):
        out["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
            for tc in msg.tool_calls
        ]
    return out


# ---------------------------------------------------------------- dry-run stand-in

class MockOpenAI:
    """Offline stand-in for plumbing tests: no network, no spend. With a JSON schema it returns
    a schema-shaped object of default values; otherwise "OK". Usage numbers are estimates."""

    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        est_in = estimate_input_tokens(kw["messages"], kw.get("tools"), kw.get("response_format"))
        rf = kw.get("response_format")
        content = json.dumps(_default_for(rf["json_schema"]["schema"])) if rf else "OK"
        reasoning = {"minimal": 0, "low": 20, "medium": 80, "high": 200, "xhigh": 400,
                     "max": 800}.get(kw.get("reasoning_effort"), 20)
        usage = {"prompt_tokens": int(est_in * 0.6), "completion_tokens": 40 + reasoning,
                 "prompt_tokens_details": {"cached_tokens": 0},
                 "completion_tokens_details": {"reasoning_tokens": reasoning}}
        msg = SimpleNamespace(content=content, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=usage)


def _default_for(schema: dict):
    t = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if t == "object":
        return {k: _default_for(v) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return []
    return {"boolean": False, "integer": 0, "number": 0.0, "string": ""}.get(t)
