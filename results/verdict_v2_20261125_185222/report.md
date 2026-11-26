# Verdict v2 evaluation (test split, effort minimal, 4 screenshots)

**Not usable from v2:** {'blocked': 1} (excluded).

v2 judged 1096 runs; 1093 also have a v1 (`minimal`) verdict for the side-by-side.

## Did the agent succeed? (same runs, expert labels)

| Judge | Precision | Recall | F1 | Accuracy | Cost per 1,000 runs |
| --- | ---: | ---: | ---: | ---: | ---: |
| v1 fair-comparison prompt (`minimal`) | 80% | 68% | 74% (69%–78%) | 87% (85%–89%) | $0.61 |
| **Verdict v2** | 85% | 61% | 71% (66%–75%) | 87% (85%–89%) | $0.91 |

- v2 minus v1, accuracy: -0.3 points (95% CI -1.8 to +1.2)
- v2 minus v1, f1: -2.6 points (95% CI -6.2 to +0.9)
- v2 minus v1, precision: +4.7 points (95% CI +0.8 to +8.7) **significant**
- v2 minus v1, recall: -6.9 points (95% CI -11.3 to -2.5) **significant**

## Side effects and looping (v1 vs v2, same runs)

| Question | Judge | Accuracy | Precision | Recall | Judge said yes | Experts said yes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Side effects | v1 | 66% | 11% | 63% | 390 | 70 |
| Side effects | v2 | 93% | 41% | 29% | 49 | 70 |
| Looping | v1 | 85% | 78% | 99% | 727 | 574 |
| Looping | v2 | 89% | 85% | 95% | 642 | 574 |

## "Claimed done, but failed"

- The agent claimed success in 281 of 1096 runs (per v2).
- v2 flagged 147 of those as **claimed done but failed**; experts agree the run failed in 81 of 147 (55%).

## Failure types (v2, failed runs)

looping: 435, gave_up: 228, wrong_answer: 101, blocked: 51, false_completion: 49, wrong_target: 20, other: 4


## Confidence and escalation

| Confidence | Runs | Accuracy vs experts |
| --- | ---: | ---: |
| high | 966 | 92% |
| medium | 100 | 57% |
| low | 30 | 23% |

**Escalation options** (a person settles every run sent to review):

| Send to a person | Runs reviewed | Accuracy on the rest | Overall accuracy |
| --- | ---: | ---: | ---: |
| nothing | 0 (0%) | 87% | 87% |
| low confidence only | 30 (3%) | 89% | 89% |
| **anything below high confidence (chosen rule)** | 146 (13%) | 92% | 93% |

## Cost

- v2: $0.91 per 1,000 runs; 8,348 input tokens, 264 output (114 reasoning), 1.6s per run, 3.9 screenshots per run.

## Where v2 disagrees with the experts (145)

- **webarena/GenericAgent-anthropic_claude-3.7-sonnet/webarena.356**: experts Successful, v2 Unsuccessful (false_completion, confidence high). Goal: "Show the route from SCS CMU in Pittsburgh to the location where the Declaration of Independence and Constituti". Evidence: step 6, FINAL: "I've displayed the route from the School of Computer Science (SCS) at Carnegie Mellon University in Pittsburgh to Independence Hall in Phila"
- **webarena/GenericAgent-meta-llama_Llama-3.3-70B-Instruct/webarena.268**: experts Successful, v2 Unsuccessful (wrong_answer, confidence high). Goal: "What's the closest national park to Vinalhaven, ME? How long does it take to bike there?". Evidence: step 18, FINAL: "The closest national park to Vinalhaven, ME is Acadia National Park. Waiting for the page to load the biking directions... | FINAL: Distance"
- **visualwebarena/GenericAgent-anthropic_claude-3.7-sonnet/visualwebarena.resized.512**: experts Successful, v2 Unsuccessful (gave_up, confidence low, flagged for review). Goal: "List out reviewers, if exist, who mention 'disgust' for the purple product". Evidence: step 3, S3: "Review by Maria A. ... 'i was extremely disgusted with it'"
- **webarena/GenericAgent-Qwen_Qwen2.5-VL-72B-Instruct/webarena.386**: experts Successful, v2 Unsuccessful (wrong_answer, confidence high). Goal: "What is the rating of Ugreen lightning to 3.5mm cable. Please round to the nearest whole number". Evidence: step 3, S3: "Search results page shows only top of products at bottom edge; no product name, rating, or 65% visible in S3/FINAL screenshot."
- **webarena/GenericAgent-gpt-4o-2024-11-20/webarena.655**: experts Successful, v2 Unsuccessful (wrong_answer, confidence high). Goal: "Fill the "contact us" form in the site for a refund on the iphone case I bought, stating that it broke after j". Evidence: step 4, S4: "SKU: IPHONE-CASE-123."
- **visualwebarena/GenericAgent-anthropic_claude-3.7-sonnet/visualwebarena.resized.756**: experts Successful, v2 Unsuccessful (other, confidence low, flagged for review). Goal: "Please show me the product page for the item in the second row, second column.". Evidence: step 2, FINAL: "FINAL page: 'Q Mixers Premium Ginger Ale: Real Ingredients & Less Sweet, 6.7 Fl Oz (24 Bottles)' $68.50"
- **visualwebarena/GenericAgent-anthropic_claude-3.7-sonnet/visualwebarena.resized.464**: experts Successful, v2 Unsuccessful (gave_up, confidence high). Goal: "What is the price of the most expensive blue product in the "Posters & Prints" category?". Evidence: step 31, FINAL: "Final page shows '1 Item' filtered $300.00 - $399.99 with blue abstract product image but no price text visible; no answer sent"
- **webarena/GenericAgent-anthropic_claude-3.7-sonnet/webarena.764**: experts Successful, v2 Unsuccessful (gave_up, confidence medium, flagged for review). Goal: "Find the walkway to the closest Target from 401 Shady Ave, Pittsburgh.". Evidence: step 17, FINAL: "Distance: 920m. Time: 0:12. 1. Start on unnamed road 2. Turn left onto Walnut Street 3. Turn right onto Shady Avenue"

Ledger: this run spent $0.9937; total recorded $1.9684 of the $7.00 cap.