# Agent Verdict

Muse Ember as a cheap, always-on judge of AI web agents: did the agent actually do what it claimed, did it cause unintended side effects, and did it loop? Ember is scored against expert human labels and against published judges (GPT-4o, Claude 3.7 Sonnet, GPT-4o-mini, Qwen2.5-VL, Llama 3.3 70B) on the same runs and the same prompt. Built during the Muse Ember Hackathon (Nov 23 to Dec 2, 2026).

Work in progress.

## Setup

```powershell
python -m pip install -r requirements.txt
copy .env.example .env   # put your Meta Model API key in MODEL_API_KEY
```

## Judge probe

```powershell
python scripts\judge_probe.py --fetch-only   # download data only: no Ember calls, $0
python scripts\judge_probe.py --dry-run      # mock Ember: checks the plumbing, $0
python scripts\judge_probe.py                # real run: ~60 runs (dev split), stops itself at $0.20
```

The probe:

1. Picks expert-labelled runs from the dev split, balanced across websites and agents. The test split is kept for final results.
2. Downloads each run's judge prompt (goal, actions, agent reasoning, final screenshot) and the published judges' verdicts. It downloads only the first few KB of each comparison file.
3. Sends Ember the identical prompt.
4. Reports precision, recall, F1 and accuracy against the experts for every judge on the same runs, plus cost per 1,000 runs.

Results are written to `results/judge_probe_<timestamp>/report.md`.

## Reproduce the headline (no API calls)

```powershell
python scripts\compare_judges.py   # Ember vs the five published judges on the test split, with paired-bootstrap intervals
```

## Verdict v2

Verdict v2 is Agent Verdict's own judge. It returns a strict JSON verdict with:

- success, and whether the agent *claimed* success
- the failure type
- the step and screenshot that prove it, with a short quote
- side effects (tightly defined) and looping
- a confidence level and a needs-a-person flag

It sees four screenshots per run: the final page, the two states just before it, and one from the middle.

```powershell
python scripts\verdict_v2_eval.py --fetch-only   # download screenshots ($0)
python scripts\verdict_v2_eval.py --dry-run      # mock Ember ($0)
python scripts\verdict_v2_eval.py                # 60 dev runs vs the v1 judge, stops itself at $0.25
```

## Use it: command, Python API, backend

```powershell
python -m pip install -e .                   # installs the agent-verdict command

agent-verdict judge run.json --dry-run       # mock Ember, $0
agent-verdict judge run.json                 # Verdict v2 on Muse Ember (~$0.001 per run), capped at $0.05
agent-verdict judge runs\*.json --json --save   # JSON output, and add the runs to the review queue

agent-verdict seed-arb                       # load the cached test-split verdicts into the review queue ($0)
agent-verdict serve                          # backend on http://127.0.0.1:8000 (API docs at /docs)
```

A run file is either an AgentRewardBench judge file or the generic format, which any agent can write:

```json
{"goal": "Order one blue mug",
 "steps": [{"action": "click('blue mug')", "reasoning": "open the product", "url": "http://shop/", "screenshot": "s0.png"}],
 "final_screenshot": "end.png"}
```

Screenshot paths are relative to the file. From Python:

```python
from agent_verdict import api
result = api.judge(api.load_trace("run.json"), max_usd=0.05)
result["verdict"]["success"], result["verdict"]["needs_review"], api.flag(result["verdict"])
```

The backend (FastAPI + SQLite, `data/app/agent_verdict.db`):

| Endpoint | What it does |
| --- | --- |
| `GET /api/summary` | counts per flag, runs to review, the judge's accuracy on what it decided alone (benchmark runs), cost |
| `GET /api/queue?status=to_review` | the review queue, least confident first (`to_review`, `reviewed`, `auto`, `all`; filter by `flag`, `benchmark`, `q`) |
| `GET /api/runs/{id}` | one run: goal, every step, screenshots available, the verdict with its evidence, reviews |
| `GET /api/runs/{id}/screens/{state}` | a screenshot |
| `POST /api/runs/{id}/review` | a person's decision: `agree` or `override`, with their call and a note |
| `POST /api/runs` | import a run in the generic format (screenshots as data URLs) |
| `POST /api/runs/{id}/judge` | judge it with Ember: **off unless** the server runs with `--allow-spend --max-usd 0.10` (or `--dry-run`) |

### The review UI

Vite + React + TypeScript + Tailwind, in `frontend/`. It has two screens: a front page with the headline numbers, and the review screen. The review screen shows one flagged run at a time: what the agent said next to what the screen shows, the proof the judge points to, a replay of every step, and two buttons ("No, it failed" / "Yes, it succeeded"; keys F and S).

```powershell
cd frontend
npm install
npm run build        # then agent-verdict serve shows the UI at http://127.0.0.1:8000
npm run dev          # or develop with hot reload at http://localhost:5173 (needs agent-verdict serve running)
```

Every verdict gets one flag. Yellow means needs review: anything the judge is not highly confident about goes to a person. Green means succeeded, red means failed, and blue means looping. Set `AGENT_VERDICT_WEBHOOK` to have each new verdict that needs review POSTed to a URL.

## Spending safeguards

- Every Ember call is logged to `usage_log.jsonl`, with its tokens, cost and stop reason. That file is the proof of usage for the submission.
- Before each request is sent, its worst-case cost is reserved. A request that would take total spend past **$7.00** is refused and never sent. Each script run also has its own smaller cap.
- `reasoning_effort` is always set explicitly, because Ember defaults to `max` and reasoning tokens are billed as output.

## Data

[AgentRewardBench](https://huggingface.co/datasets/McGill-NLP/agent-reward-bench) (Lù et al., 2025, [arXiv 2504.08942](https://arxiv.org/abs/2504.08942)). No license is stated for the dataset, so it is downloaded locally, used only to evaluate judges (its intended purpose), and never committed to this repo.
