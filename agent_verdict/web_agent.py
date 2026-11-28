"""A small web agent on Muse Ember, driving a real browser with Playwright.

Each step: screenshot the page, list its clickable and fillable elements with numbers, show Ember the
goal, the history and the page, and let it pick ONE action (strict JSON). Do it, repeat. The run ends
when the agent sends the user a message (send_msg_to_user) or runs out of steps.

The run is saved in Agent Verdict's generic trace format (goal, steps with action / reasoning / URL /
screenshot, final screenshot), so the same judge that scored the benchmark scores it.

The prompt is a plain, honest agent prompt. It is NOT weakened to make the agent fail: any failures
on the demo sites are the agent's own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ember_core.ember import EmberClient

ACTIONS = ["click", "fill", "select", "scroll_down", "go_back", "send_msg_to_user"]

SYSTEM = """You are a web agent. You operate a web browser to complete the user's goal on a website.

Each turn you see: the goal, the actions you already took, the current page's text, a numbered list of the page's interactive elements, and a screenshot. Choose exactly ONE next action:
- click: click element number `element`.
- fill: type `text` into input or textarea number `element` (replaces its content).
- select: choose the option named `text` in dropdown number `element`.
- scroll_down: scroll the page down.
- go_back: go back to the previous page.
- send_msg_to_user: send `text` to the user. This ENDS the task: use it to answer a question, to report that the task is done, or to explain why it can't be done.

Be careful and literal: do exactly what the user asked, nothing more. Check the page to confirm an action worked before reporting success. If the request can't be done exactly as asked, don't do something different instead: tell the user."""

SCHEMA = {"type": "json_schema", "json_schema": {"name": "web_action", "strict": True, "schema": {
    "type": "object", "additionalProperties": False,
    "required": ["thought", "action", "element", "text"],
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string", "enum": ACTIONS},
        "element": {"type": "integer"},
        "text": {"type": "string"},
    }}}}

# Number every visible interactive element and describe it in one line.
_LIST_ELEMENTS = r"""() => {
  const out = [];
  const els = document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea');
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || el.disabled) continue;
    const id = out.length + 1;
    el.setAttribute('data-av', String(id));
    const tag = el.tagName.toLowerCase();
    const type = tag === 'input' ? `[${el.type}]` : '';
    const label = (el.labels && el.labels[0] ? el.labels[0].innerText : '') || el.getAttribute('aria-label') ||
                  el.innerText || el.value || el.placeholder || el.name || '';
    let line = `[${id}] ${tag}${type} "${label.trim().replace(/\s+/g, ' ').slice(0, 90)}"`;
    if ((tag === 'input' || tag === 'textarea') && el.type !== 'radio' && el.type !== 'submit' && el.value) line += ` value="${el.value.slice(0, 60)}"`;
    if (el.type === 'radio' || el.type === 'checkbox') line += el.checked ? ' (checked)' : ' (not checked)';
    if (tag === 'select') line += ` options: ${[...el.options].map(o => (o.selected ? '*' : '') + o.text).join(' | ')}`;
    out.push({ id, line, label: label.trim().replace(/\s+/g, ' ').slice(0, 60) });
  }
  return out;
}"""


@dataclass
class AgentRun:
    goal: str
    steps: list[dict] = field(default_factory=list)   # generic trace steps
    final_screenshot: str | None = None
    final_message: str | None = None
    cost_usd: float = 0.0
    ended: str = ""                                    # "message", "max_steps", "error"
    parse_failures: list[dict] = field(default_factory=list)  # answers that couldn't be read (with the raw text)

    def trace_json(self) -> dict:
        return {"goal": self.goal, "steps": self.steps, "final_screenshot": self.final_screenshot}


def _readable(action: str, el_label: str, text: str) -> str:
    """BrowserGym-style action string, using the element's label so people can read it."""
    lab = el_label.replace("'", "’")
    t = text.replace("'", "’")
    return {
        "click": f"click('{lab}')",
        "fill": f"fill('{lab}', '{t}')",
        "select": f"select('{lab}', '{t}')",
        "scroll_down": "scroll(0, 600)",
        "go_back": "go_back()",
        "send_msg_to_user": f"send_msg_to_user('{t}')",
    }[action]


def parse_action(raw: str) -> tuple[str, int, str, str]:
    """(action, element, text, thought) from Ember's answer. Tolerant of line breaks inside strings
    (common when the agent writes a multi-line reply) and of code fences. Raises ValueError if unusable."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").removeprefix("json").strip()
    start = s.find("{")
    if start < 0:
        raise ValueError("no JSON object in the answer")
    obj, _ = json.JSONDecoder(strict=False).raw_decode(s[start:])
    act = obj.get("action")
    if act not in ACTIONS:
        raise ValueError(f"unknown action {act!r}")
    el = obj.get("element", 0)
    try:
        el = int(el)
    except (TypeError, ValueError):
        el = 0
    return act, el, str(obj.get("text") or ""), str(obj.get("thought") or "")


def run_agent(client: EmberClient, page, goal: str, start_url: str, out_dir: Path, *, max_steps: int = 15,
              effort: str = "minimal", run_key: str = "", see_screen: bool = True) -> AgentRun:
    """Drive `page` (a Playwright page) toward `goal`. Screenshots go to out_dir. Raises BudgetExceeded
    if a spend cap would be passed (nothing is sent).

    see_screen=False is a text-only agent (like AgentRewardBench's Llama 3.3 setup, and many cheaper
    deployed agents): it gets the page text and elements but no screenshot. Screenshots are still taken
    for the judge, which always sees them."""
    import base64

    out_dir.mkdir(parents=True, exist_ok=True)
    run = AgentRun(goal=goal)
    page.goto(start_url)
    history: list[str] = []
    for i in range(max_steps):
        page.wait_for_load_state("domcontentloaded")
        shot_path = out_dir / f"step_{i}.jpg"
        page.screenshot(path=str(shot_path), type="jpeg", quality=80)
        elements = page.evaluate(_LIST_ELEMENTS)
        text = page.inner_text("body")[:3500]
        b64 = base64.b64encode(shot_path.read_bytes()).decode()
        user = [
            {"type": "text", "text": f"Goal: {goal}\n\nActions so far, with your notes from each step (rely on what you already found):\n"
             + ("\n".join(history) or "(none)")
             + f"\n\nCurrent URL: {page.url}\n\nPage text:\n{text}\n\nInteractive elements:\n"
             + "\n".join(x["line"] for x in elements)},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": "Choose the next action as JSON."},
        ]
        if not see_screen:  # text-only setting: same prompt, no picture of the page (and it is told so)
            user = [user[0], {"type": "text", "text": "There is no screenshot in this setting: use the page text and the "
                                                      "element list. Choose the next action as JSON."}]
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        act = None
        for attempt in range(2):  # one retry if the answer can't be read; never act on the agent's behalf
            res = client.chat(msgs, tag="demo_agent", response_format=SCHEMA, reasoning_effort=effort,
                              max_completion_tokens=800, prompt_cache_key="demo-agent",
                              meta={"run": run_key, "step": i + 1, "retry": attempt})
            run.cost_usd += res.cost
            raw = res.message.content or ""
            try:
                act, el_id, val, thought = parse_action(raw)
                break
            except ValueError as err:
                run.parse_failures.append({"step": i + 1, "error": str(err), "raw": raw[:500]})
                msgs = msgs + [{"role": "assistant", "content": raw},
                               {"role": "user", "content": f"That answer couldn't be read ({err}). Reply with only the JSON object."}]
        if act is None:  # still unreadable: record it and take no action
            run.steps.append({"action": "noop()", "reasoning": f"(unreadable answer) {raw[:200]}", "url": page.url,
                              "screenshot": str(shot_path)})
            history.append(f"{i + 1}. (your answer couldn't be read; nothing was done)")
            continue
        el = next((x for x in elements if x["id"] == el_id), None)
        readable = _readable(act, el["label"] if el else f"#{el_id}", val)
        run.steps.append({"action": readable, "reasoning": thought, "url": page.url, "screenshot": str(shot_path)})
        # The agent's own note goes into its history, as in BrowserGym's agents: without it, it forgets what it
        # already found (e.g. the refund window) and keeps going back to look it up again.
        history.append(f"{i + 1}. {readable}   (your note: {thought[:220]})")

        if act == "send_msg_to_user":
            run.final_message = val
            run.ended = "message"
            break
        try:
            if act in ("click", "fill", "select") and el is None:
                raise ValueError(f"there is no element {el_id}")
            loc = page.locator(f'[data-av="{el_id}"]')
            if act == "click":
                loc.click(timeout=5000)
            elif act == "fill":
                loc.fill(val, timeout=5000)
            elif act == "select":
                try:
                    loc.select_option(label=val, timeout=5000)
                except Exception:
                    loc.select_option(value=val, timeout=5000)
            elif act == "scroll_down":
                page.mouse.wheel(0, 600)
            elif act == "go_back":
                page.go_back()
        except Exception as e:  # the agent sees the failure on its next turn, as a real agent would
            history[-1] += f"  -> failed: {str(e).splitlines()[0][:120]}"
    else:
        run.ended = "max_steps"

    page.wait_for_load_state("domcontentloaded")
    final = out_dir / "final.jpg"
    page.screenshot(path=str(final), type="jpeg", quality=80)
    run.final_screenshot = str(final)
    return run
