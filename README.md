# Agent Verdict

**AI agents say "done" when they aren't. Agent Verdict checks every run, using Muse Ember, and hands the unsure ones to a person, with the proof.**

## The story

AI agents now book tables, place orders and close support tickets on their own. They also get things wrong, and they often report success anyway:

- *"Your order has been placed."* The final screen still shows the **Place order** button.
- *"Added the red umbrella to your cart."* The umbrella in the cart is yellow.
- *"The nearest Starbucks is 15 km away, a 3:25 walk."* The map shows a 15 km route across town.

Teams can't check every run by hand. Having GPT-4o or Claude check them costs about $13–21 per 1,000 runs. So most runs go unchecked, and the failures surface when a customer complains.

**Agent Verdict is a quality-control layer for agents.** For every run, Muse Ember reads the goal, every step the agent took and the key screenshots. It then returns a verdict:

- **succeeded or failed, and how:** for example "claimed done, but not done", wrong answer, looping, blocked or wrong item
- **the proof:** the step and screenshot that show it, with a short quote
- **a confidence level:** anything below high confidence goes to a **review queue**, where a person sees the agent's claim next to the screen and makes the call in one click

Three numbers, measured on 1,096 expert-labelled runs the judge was never tuned on:

| Result | What it means |
| --- | --- |
| **80% precision, best of six judges** | Same runs, same prompt, against GPT-4o, Claude 3.7 Sonnet, GPT-4o-mini, Qwen2.5-VL and Llama 3.3. The gap to every one of them is statistically significant. |
| **93% accuracy with people in the loop** | The judge decides 87% of runs on its own, at 92% accuracy, and sends the 13% it isn't sure about to a person. |
| **$0.61–0.91 per 1,000 runs** | 22× cheaper than GPT-4o and 35× cheaper than Claude 3.7 Sonnet on the same runs. |

**The same verdicts make agents better.** Run the agent a few times and keep the attempt the judge trusts most. On 300 tasks, that solves 38.8% of tasks, against 33.3% for the best single agent (Claude 3.7 Sonnet). That's 17% more tasks solved, and the gain is statistically significant.

**And it works live.** Our own Ember browser agent does tasks on three small websites we host: a shop, a restaurant and a help desk. Each site keeps its own records, so the true outcome of every run is known. The judge agreed with those records on every scored live run. When a text-only agent claimed it had bought "the cheaper blue bottle" (it was green), the judge caught it, because it could see the screenshot the agent never saw.

Built solo for the Meta Muse Ember Hackathon (Nov 23 to Dec 2, 2026). Every model call in the product goes to Muse Ember (`muse-ember-1.0`).

## Setup

You need Python 3.10+ and Node 18+. A Meta Model API key is optional: without one, the demo plays back recorded runs. Commands are shown for Windows PowerShell; on macOS and Linux, use `source .venv/bin/activate` and forward slashes.

```powershell
git clone https://github.com/ShahaDeven/Agent_Verdict.git
cd Agent_Verdict
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .            # installs the agent-verdict command
python -m playwright install chromium  # the browser the demo agent drives
copy .env.example .env                 # optional: put your key in MODEL_API_KEY

cd frontend
npm install
npm run build                          # the backend serves this UI at http://127.0.0.1:8000
cd ..
```

### See it work: one command, no API key needed

```powershell
agent-verdict demo
```

This starts the app and opens the home page in your browser.

- **Without an API key,** you get a **replay**: 59 real runs of our Ember agent on the demo sites, with all 496 screenshots and Muse Ember's real verdicts, shipped in `demo_replay/`. Most are there from the start. Eight more arrive one by one on the **Live** page, each shown as judging and then given its verdict, including two false "done" claims the judge catches. Browse the review queue, open any run and make the call yourself. No key, no cost.
- **With a key in `.env`,** the Ember agent does three new tasks live on the demo websites, for about $0.01.

Everything keeps running until you press Ctrl+C.

| Option | What it does |
| --- | --- |
| `--replay` | Replays the recorded runs even if you have a key |
| `--dry-run` | Uses a mock instead of Ember, so it costs nothing, with its own database |
| `--tasks visual --text-only` | The agent setting without screenshots, where false "done" claims show up |
| `--headed` | Shows the agent's browser |
| `--tasks none` | Only starts the sites and the app |
| `--max-usd 0.05` | The spend cap (that's the default) |

The parts also run separately (`agent-verdict demo-sites`, `agent-verdict serve`, `python scripts\live_demo.py`), which is handy for longer runs.

### Judge your own agent's runs

Write each run as JSON: the goal, then the steps with their action, reasoning, URL and screenshot.

```json
{"goal": "Order one blue mug",
 "steps": [{"action": "click('Blue mug')", "reasoning": "open the product", "url": "http://shop/", "screenshot": "s0.png"},
           {"action": "send_msg_to_user('Ordered.')", "reasoning": "done", "url": "http://shop/cart", "screenshot": "s1.png"}],
 "final_screenshot": "end.png"}
```

```powershell
agent-verdict judge run.json            # the verdict in the terminal; about $0.001, capped at $0.05
agent-verdict judge runs\*.json --save  # also adds them to the review queue
agent-verdict judge run.json --dry-run  # mock judge, $0
```

From Python:

```python
from agent_verdict import api
result = api.judge(api.load_trace("run.json"), max_usd=0.05)
print(result["verdict"]["success"], result["verdict"]["confidence"], api.flag(result["verdict"]))
```

### Reproduce the benchmark numbers

The benchmark data isn't in this repo (see [Data](#data)). These steps download it from Hugging Face and judge the test split with Ember, for about $1 in total. Each script stops itself at its cap.

```powershell
python scripts\verdict_v2_eval.py --split test --n 5000 --fetch-only     # download (~500 MB), $0
python scripts\effort_sweep.py --split test --n 5000 --efforts minimal --session-cap 1.00   # Ember on the benchmark's own prompt, ~$0.70
python scripts\verdict_v2_eval.py --split test --n 5000 --session-cap 1.30   # Verdict v2, ~$1.00
python scripts\compare_judges.py       # the six-judge comparison with paired intervals, $0
python scripts\best_attempt.py         # best of several attempts, $0
agent-verdict seed-arb                 # load the judged runs into the review queue, $0
python scripts\build_results.py        # the numbers behind the Results page, $0
```

Run the tests with `python -m pytest tests -q`. They use a mock Ember and cost nothing.

## What's in the app

| Screen | What it's for |
| --- | --- |
| **Front page** (`/`) | The pitch, the headline numbers and a real flagged run |
| **Review queue** (`#/review`) | One run at a time, least confident first: what the agent said, what the screen shows, the proof, a replay of every step, and "No, it failed" / "Yes, it succeeded" (keys F and S) |
| **Live** (`#/live`) | Your own agent's runs as they finish, judged in real time |
| **Results** (`#/results`) | Every number, with confidence intervals and the limits |

Every verdict gets one flag: **yellow** (a person decides), **red** (failed) or **green** (succeeded). **Looped** and **side effect?** are tags on top of it, because a run can loop and still succeed.

## Results

All benchmark numbers come from the AgentRewardBench **test split** (1,096 runs). The dev split was used to choose settings and is left out of every number. Intervals are 95% paired bootstrap.

**The six judges, same runs and same prompt:**

| Judge | Precision | Recall | Accuracy | Cost per 1,000 runs |
| --- | ---: | ---: | ---: | ---: |
| **Muse Ember (minimal)** | **80%** | 68% | **87%** | **$0.61** |
| GPT-4o | 68% | 80% | 85% | $13.38 |
| Claude 3.7 Sonnet | 70% | 77% | 85% | $21.37 |
| GPT-4o-mini | 65% | 78% | 83% | $6.10 |
| Qwen2.5-VL 72B (self-hosted) | 65% | 86% | 84% | GPU time not counted |
| Llama 3.3 70B (self-hosted, text only) | 68% | 79% | 84% | GPU time not counted |

Ember's precision is 10 to 16 points higher than every other judge's, and all five gaps are significant. Its accuracy is the highest too. Ember is the strict judge: when it says an agent succeeded, it's right 80% of the time, and the runs it isn't sure about go to a person.

**With a person in the loop (Verdict v2):**

| Confidence | Share of runs | Accuracy |
| --- | ---: | ---: |
| high | 88% | 92% |
| medium | 9% | 57% |
| low | 3% | 23% |

Sending everything below high confidence to a person means reviewing 13% of runs, and overall accuracy rises from 87% to 93%.

**Best of several attempts** (300 tasks, each tried by 2–4 agents):

| How the attempt is chosen | Tasks solved |
| --- | ---: |
| **The attempt the judge trusts most** | **38.8%** |
| Always Claude 3.7 Sonnet (the best single agent, chosen with hindsight) | 33.3% |
| A random attempt | 26.9% |
| Ceiling: pick right whenever any attempt succeeded | 46.7% |

**Live, on our demo sites:** the judge agreed with the sites' own records on every scored run, at about $0.0006 per verdict. In the text-only agent setting it caught all 3 false "done" claims.

**What we don't claim:**
- **Side effects:** the judge rarely raises false alarms, but it catches only some real side effects. In the UI the side-effect tag is a hint for the reviewer, not a measured detector.
- **Enterprise forms (WorkArena):** the judge is strict and misses some real successes when the final screen doesn't show every field. Picking the best attempt doesn't help there (−1 point).
- **Few live failures:** our main agent rarely fails on our sites, so most live runs test whether the judge confirms real success.

## How it works

```
agent run ─► trace (goal, steps, screenshots) ─► Verdict v2 on Muse Ember ─► verdict + proof + confidence
                                                                                    │
                                        high confidence ◄───────────────────────────┤
                                        decided automatically          below high ──► review queue ─► a person
```

- **Verdict v2** (`agent_verdict/verdict_v2.py`) sends Ember the goal, every step with the agent's reasoning, and four screenshots: the final page, the two before it, and one from the middle. Ember returns strict JSON: success, whether the agent *claimed* success, failure type, side effect, looping, the evidence (step, screenshot, quote), confidence and reasoning.
- **Demo sites** (`demo_sites/`) are plain local websites with realistic traps:
  - a review step before an order is placed
  - an expired coupon and an item with only one left
  - a waitlist that says "Request received"
  - a P1 ticket that needs a resolution note to close
  - replies to a closed ticket that are saved as drafts
  - product pictures that only someone looking at the page can tell apart

  There are 44 tasks, each with a checker that reads the sites' records.
- **The demo agent** (`agent_verdict/web_agent.py`) is a Playwright browser driven by Ember. Each step, it sees the page text, a numbered list of elements and (unless `--text-only`) a screenshot, and picks one action.
- **The app:** a FastAPI + SQLite backend (`agent_verdict/server.py`, `store.py`) and a React + TypeScript + Tailwind frontend (`frontend/`).

## Spending safeguards

- Every Ember call is logged to `usage_log.jsonl` with its tokens, cost and stop reason. That file is the proof of usage. The whole project, including all evaluation and live runs, has cost about $2.25.
- Before a request is sent, its worst-case cost is reserved. A request that would take total spend past **$7.00** is refused and never sent. Every script and server session also has its own smaller cap.
- The judging endpoint in the app is off unless the server is started with `--allow-spend`.
- `reasoning_effort` is always set explicitly, because Ember defaults to `max` and reasoning tokens are billed as output.

## Repository map

| Path | What's there |
| --- | --- |
| `ember_core/` | The Ember client, pricing and the spend ledger with its hard cap |
| `agent_verdict/` | The judge (`verdict_v2.py`), trace formats, the Python API and command, the store and server, best-attempt selection, the web agent |
| `demo_sites/` | The three demo websites and the 44 tasks with their checkers |
| `frontend/` | The review app |
| `demo_replay/` | 59 recorded live runs with screenshots and Ember's verdicts, for the demo without a key (our own data) |
| `scripts/` | The evaluation, live-demo and results scripts |
| `results/` | Reports from every run: summaries only, never per-run benchmark labels |
| `tests/` | 132 tests, with a mock Ember |

## Data

[AgentRewardBench](https://huggingface.co/datasets/McGill-NLP/agent-reward-bench) (Lù et al., 2025, [arXiv 2504.08942](https://arxiv.org/abs/2504.08942)) has 1,302 web-agent runs with expert labels. 1,290 of them have a majority label, split into 193 dev runs and 1,097 test runs. No license is stated for the dataset. So it is downloaded locally, used only to evaluate judges (its intended purpose), and never committed: the review queue, the cached verdicts and the per-run reports stay on your machine.
