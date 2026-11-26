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

## Spending safeguards

- Every Ember call is logged to `usage_log.jsonl`, with its tokens, cost and stop reason. That file is the proof of usage for the submission.
- Before each request is sent, its worst-case cost is reserved. A request that would take total spend past **$7.00** is refused and never sent. Each script run also has its own smaller cap.
- `reasoning_effort` is always set explicitly, because Ember defaults to `max` and reasoning tokens are billed as output.

## Data

[AgentRewardBench](https://huggingface.co/datasets/McGill-NLP/agent-reward-bench) (Lù et al., 2025, [arXiv 2504.08942](https://arxiv.org/abs/2504.08942)). No license is stated for the dataset, so it is downloaded locally, used only to evaluate judges (its intended purpose), and never committed to this repo.
