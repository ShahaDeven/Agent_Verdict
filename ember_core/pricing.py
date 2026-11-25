"""Muse Ember prices and cost math.

Rates are USD per 1M tokens, from dev.meta.ai/docs/pricing-rate-limits (checked 2026-11-24).
A request whose input is over 200K tokens is billed entirely at the long-context rates.
Reasoning tokens are part of completion tokens and billed at the output rate.
"""

from __future__ import annotations

from dataclasses import dataclass

LONG_CONTEXT_THRESHOLD = 200_000

# (uncached input, cached input, output) per 1M tokens
STANDARD_RATES = (0.10, 0.004, 0.50)
LONG_RATES = (0.30, 0.012, 1.50)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def uncached_tokens(self) -> int:
        return max(self.prompt_tokens - self.cached_tokens, 0)


def _rates(prompt_tokens: int) -> tuple[float, float, float]:
    return LONG_RATES if prompt_tokens > LONG_CONTEXT_THRESHOLD else STANDARD_RATES


def cost_usd(usage: Usage) -> float:
    rin, rcached, rout = _rates(usage.prompt_tokens)
    return (
        usage.uncached_tokens * rin
        + usage.cached_tokens * rcached
        + usage.completion_tokens * rout
    ) / 1_000_000


def worst_case_cost(est_input_tokens: int, max_completion_tokens: int) -> float:
    """Upper bound for one request: nothing cached, every allowed output token used."""
    rin, _, rout = _rates(est_input_tokens)
    return (est_input_tokens * rin + max_completion_tokens * rout) / 1_000_000


def _get(obj, name, default=0):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default) or default
    return getattr(obj, name, default) or default


def usage_from_response(resp) -> Usage:
    """Read the Chat Completions usage block (works for SDK objects and plain dicts)."""
    u = _get(resp, "usage", None)
    return Usage(
        prompt_tokens=int(_get(u, "prompt_tokens")),
        cached_tokens=int(_get(_get(u, "prompt_tokens_details", None), "cached_tokens")),
        completion_tokens=int(_get(u, "completion_tokens")),
        reasoning_tokens=int(_get(_get(u, "completion_tokens_details", None), "reasoning_tokens")),
    )
