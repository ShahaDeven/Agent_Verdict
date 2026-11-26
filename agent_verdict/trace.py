"""The run log Agent Verdict judges: a goal, the agent's steps, and screenshots.

One format for every source. Adapters turn a source into a Trace:
- from_arb_messages(): AgentRewardBench / BrowserGym judge prompts (goal, step list, final screenshot)
- from_generic(): our generic JSON format, for any agent:
    {"goal": "...",
     "steps": [{"action": "...", "reasoning": "...", "url": "...", "screenshot": "<path or data URL>"}],
     "final_screenshot": "<path or data URL>"}   # page state after the last action (optional)

Screenshots are indexed like BrowserGym: state k is what the agent saw before Step k+1, and the
last state is the page after the final action ("FINAL").
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Step:
    n: int            # 1-based step number, as shown to the judge
    url: str
    action: str
    reasoning: str


@dataclass
class Trace:
    goal: str
    steps: list[Step]
    final_screenshot: str | None = None                        # data URL of the final page state
    screenshots: dict[int, str] = field(default_factory=dict)  # state index -> data URL (lazy for ARB)

    @property
    def n_states(self) -> int:
        """Number of page states, including the final one (= number of steps listed)."""
        return len(self.steps)

    @property
    def final_message(self) -> str | None:
        """What the agent told the user, if it sent a message (BrowserGym send_msg_to_user)."""
        for s in reversed(self.steps):
            m = re.match(r"\s*send_msg_to_user\((.*)\)\s*$", s.action or "", re.S)
            if m:
                return m.group(1).strip().strip("'\"")
        return None


_STEP = re.compile(r"Step:\s*(\d+)\s*\nURL:\s*(.*?)\s*\nAction:\s*(.*?)\nReasoning:\s*(.*)", re.S)


def from_arb_messages(messages: list[dict]) -> Trace:
    """Parse an AgentRewardBench judge prompt (the 'regular' chat messages)."""
    goal, steps, final = "", [], None
    for m in messages:
        if not isinstance(m.get("content"), list):
            continue
        for part in m["content"]:
            if part.get("type") == "image_url":
                final = part["image_url"]["url"]
                continue
            text = part.get("text", "")
            if text.startswith("The user goal is:"):
                goal = text[len("The user goal is:"):].strip()
            elif "performed the following actions" in text:
                for seg in text.split("-----"):
                    mm = _STEP.search(seg.strip())
                    if mm:
                        steps.append(Step(int(mm.group(1)), mm.group(2).strip(), mm.group(3).strip(),
                                          mm.group(4).strip()))
    return Trace(goal=goal, steps=steps, final_screenshot=final)


def _to_data_url(ref: str | None, base_dir: Path) -> str | None:
    if not ref:
        return None
    if ref.startswith("data:"):
        return ref
    p = Path(ref)
    p = p if p.is_absolute() else base_dir / p
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def from_generic(data: dict, base_dir: Path | str = ".") -> Trace:
    """Parse the generic JSON format. Screenshot paths are resolved relative to base_dir."""
    base_dir = Path(base_dir)
    raw = data.get("steps") or []
    steps = [Step(i + 1, str(s.get("url", "")), str(s.get("action", "")), str(s.get("reasoning", "")))
             for i, s in enumerate(raw)]
    shots = {i: u for i, s in enumerate(raw) if (u := _to_data_url(s.get("screenshot"), base_dir))}
    final = _to_data_url(data.get("final_screenshot"), base_dir)
    if final:  # the final state becomes one more state with no action, like BrowserGym logs
        steps.append(Step(len(steps) + 1, steps[-1].url if steps else "", "None", "None"))
        shots[len(steps) - 1] = final
    elif shots:
        final = shots[max(shots)]
    return Trace(goal=str(data.get("goal", "")), steps=steps, final_screenshot=final, screenshots=shots)
