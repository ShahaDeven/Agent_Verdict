# Effort comparison (dev split, screenshots original size)

All rows are scored on the same 35 runs (11 successful per experts). Brackets are 95% bootstrap confidence intervals: with this few runs, overlapping intervals mean the difference may be noise.

| Judge | Precision | Recall | F1 | Accuracy | Side effects acc. | Looping acc. | Truncated | Avg reasoning tokens | Avg cost / run | Cost per 1,000 runs | Avg latency | Source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Ember minimal** | 100% | 64% | 78% (50%–95%) | 89% (77%–97%) | 77% | 83% | 0 | 124 | $0.00056 | $0.56 | 2.0s | new |
| **Ember low** | 100% | 64% | 78% (50%–95%) | 89% (77%–97%) | 71% | 83% | 0 | 383 | $0.00072 | $0.72 | 2.3s | reused from judge_probe_20261125_002445 |
| **Ember medium** | 100% | 64% | 78% (50%–95%) | 89% (77%–97%) | 63% | 86% | 0 | 750 | $0.00091 | $0.91 | 3.2s | new |
| gpt-4o-noaxtree (published) | 83% | 45% | 59% (27%–83%) | 80% (66%–91%) | | | | | | $12.50 | | dataset |
| llama-3.3-70b-noscreen (published) | 100% | 64% | 78% (50%–95%) | 89% (77%–97%) | | | | | | $0.00 | | dataset |

## How verdicts change compared with `low`

- `minimal`: 0 of 35 verdicts differ from `low`; 0 of those became correct, 0 became wrong.
- `medium`: 0 of 35 verdicts differ from `low`; 0 of those became correct, 0 became wrong.

**Cheapest effort with accuracy and F1 at least as good as `low` on this sample: `minimal`** ($0.56 per 1,000 runs). Treat this as provisional: the intervals above show how much is noise. The final choice is confirmed on the test split.

Ledger: this run spent $0.0875; total recorded $0.2374 of the $7.00 cap.