# Effort comparison (dev split, screenshots original size)

All rows are scored on the same 60 runs (18 successful per experts). Brackets are 95% bootstrap confidence intervals: with this few runs, overlapping intervals mean the difference may be noise.

| Judge | Precision | Recall | F1 | Accuracy | Side effects acc. | Looping acc. | Truncated | Avg reasoning tokens | Avg cost / run | Cost per 1,000 runs | Avg latency | Source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Ember minimal** | 87% | 72% | 79% (61%–92%) | 88% (80%–95%) | 77% | 85% | 0 | 130 | $0.00055 | $0.55 | 2.1s | 60 cached, 0 new |
| **Ember low** | 87% | 72% | 79% (61%–92%) | 88% (80%–95%) | 73% | 85% | 0 | 372 | $0.00069 | $0.69 | 2.6s | 35 cached, 25 new |
| **Ember medium** | 93% | 78% | 85% (69%–97%) | 92% (83%–98%) | 68% | 87% | 0 | 795 | $0.00091 | $0.91 | 3.3s | 60 cached, 0 new |
| gpt-4o-noaxtree (published) | 71% | 67% | 69% (48%–84%) | 82% (72%–92%) | | | | | | $11.91 | | dataset |
| llama-3.3-70b-noscreen (published) | 74% | 78% | 76% (56%–89%) | 85% (75%–93%) | | | | | | $0.00 | | dataset |

## How verdicts change compared with `low`

- `minimal`: 0 of 60 verdicts differ from `low`; 0 of those became correct, 0 became wrong.
- `medium`: 2 of 60 verdicts differ from `low`; 2 of those became correct, 0 became wrong.

**Cheapest effort with accuracy and F1 at least as good as `low` on this sample: `minimal`** ($0.55 per 1,000 runs). Treat this as provisional: the intervals above show how much is noise. The final choice is confirmed on the test split.

Ledger: this run spent $0.0166; total recorded $0.2540 of the $7.00 cap.