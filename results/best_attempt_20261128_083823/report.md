# Best of several attempts, picked by the judge (v2-minimal-f4, AgentRewardBench test split)

300 tasks with at least 2 judged attempts (197 with 4, 102 with 3, 1 with 2); 0 tasks had only one attempt and are left out; 1 runs had no usable verdict.

| How the attempt is chosen | Tasks solved |
| --- | ---: |
| **Judge's pick (Verdict v2 on Muse Ember)** | **38.8%** |
| Always Claude 3.7 Sonnet (best single agent) | 33.3% |
| Always GPT-4o | 30.9% |
| Always Qwen2.5-VL 72B | 22.8% |
| Always Llama 3.3 70B | 20.7% |
| Random attempt | 26.9% |
| Ceiling (pick right whenever any attempt succeeded) | 46.7% |

- Judge's pick vs the best single agent (Claude 3.7 Sonnet): +5.5 points (95% CI +2.1 to +9.1) **significant**.
- Judge's pick vs a random attempt: +11.9 points (95% CI +9.1 to +14.7) **significant**.
- Of the possible gain from choosing well (random 26.9% to ceiling 46.7%), the judge's pick captures 60%.
- On 191 tasks the judge said every attempt failed; it was right on 147 (77.0%). Those are the tasks to send to a person or retry.
- The best single agent is chosen with hindsight on these same tasks, which flatters that baseline. Judging every attempt costs about $0.0009 each, so $0.99 for all 1096 attempts here.

## By benchmark

| Benchmark | Tasks | Judge's pick | Best single agent | Random | Ceiling |
| --- | ---: | ---: | ---: | ---: | ---: |
| assistantbench | 27 | 13.9% | 11.1% | 7.4% | 22.2% |
| visualwebarena | 92 | 43.1% | 29.3% | 29.0% | 56.5% |
| webarena | 78 | 60.3% | 55.1% | 38.2% | 65.4% |
| workarena | 103 | 25.2% | 26.2% | 21.6% | 30.1% |
