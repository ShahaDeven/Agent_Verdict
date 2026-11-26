# Effort comparison (test split, screenshots original size)

**Excluded from every row:** 1 runs blocked by Ember's content filter, 2 with temporary API errors (rerun to retry), 0 not judged. Blocked runs: visualwebarena/GenericAgent-anthropic_claude-3.7-sonnet/visualwebarena.resized.385

All rows are scored on the same 1094 runs (291 successful per experts). Brackets are 95% bootstrap confidence intervals: with this few runs, overlapping intervals mean the difference may be noise.

| Judge | Precision | Recall | F1 | Accuracy | Side effects acc. | Looping acc. | Truncated | Avg reasoning tokens | Avg cost / run | Cost per 1,000 runs | Avg latency | Source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Ember minimal** | 80% | 68% | 74% (69%–78%) | 87% (85%–89%) | 66% | 85% | 0 | 139 | $0.00061 | $0.61 | 1.8s | 787 cached, 310 new |
| gpt-4o-noaxtree (published) | 68% | 80% | 74% (70%–78%) | 85% (83%–87%) | | | | | | $13.37 | | dataset |
| claude-3.7-sonnet-noaxtree (published) | 70% | 77% | 73% (69%–77%) | 85% (83%–87%) | | | | | | $21.36 | | dataset |
| gpt-4o-mini-noaxtree (published) | 65% | 78% | 71% (67%–75%) | 83% (81%–85%) | | | | | | $6.10 | | dataset |
| qwen-2.5-vl-noaxtree (published) | 65% | 86% | 74% (70%–77%) | 84% (82%–86%) | | | | | | $0.00 | | dataset |
| llama-3.3-70b-noscreen (published) | 68% | 79% | 73% (69%–77%) | 84% (82%–86%) | | | | | | $0.00 | | dataset |

Published judges' costs are what the benchmark authors paid; Qwen2.5-VL and Llama 3.3 were self-hosted, so their $0 excludes GPU cost.

**Cheapest effort with accuracy and F1 at least as good as `low` on this sample: `minimal`** ($0.61 per 1,000 runs). Treat this as provisional: the intervals above show how much is noise. The final choice is confirmed on the test split.

Ledger: this run spent $0.1968; total recorded $0.9241 of the $7.00 cap.