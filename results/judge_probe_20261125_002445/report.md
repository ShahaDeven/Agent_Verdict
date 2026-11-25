# Agent-judge probe (dev split, effort low, screenshots original)

60 runs judged by Ember (0 truncated, excluded). Expert labels: 17 successful, 43 unsuccessful. Every judge below is scored on the same runs it has a verdict for, against the same expert labels, with the same prompt (goal, actions, agent reasoning, final screenshot).

## Did the agent succeed? (positive class = Successful)

| Judge | Runs | Precision | Recall | F1 | Accuracy | Unparsed | Avg cost / run | Cost per 1,000 runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Muse Ember** (ours) | 60 | 86% | 71% | 77% | 88% | 0 | $0.00075 | $0.75 |
| gpt-4o-noaxtree | 60 | 73% | 65% | 69% | 83% | 0 | $0.01336 | $13.36 |
| claude-3.7-sonnet-noaxtree | 60 | 83% | 59% | 69% | 85% | 0 | $0.02164 | $21.64 |
| gpt-4o-mini-noaxtree | 60 | 68% | 76% | 72% | 83% | 0 | $0.00611 | $6.11 |
| qwen-2.5-vl-noaxtree | 60 | 82% | 82% | 82% | 90% | 0 | $0.00000 | $0.00 |
| llama-3.3-70b-noscreen | 60 | 87% | 76% | 81% | 90% | 0 | $0.00000 | $0.00 |

Ember costs **18x less** than GPT-4o per run on this prompt (published GPT-4o cost from the dataset vs. our measured Ember cost).

Published judges' costs are what the benchmark authors paid at the time; Llama 3.3 was self-hosted (cost 0).

## Secondary questions (Ember vs. experts)

- Unintended side effects: accuracy 70% on 60 runs (precision 11%, recall 67%)
- Looping: accuracy 88% on 60 runs (precision 81%, recall 100%)

## Ember by benchmark

| Benchmark | Runs | Precision | Recall | Accuracy |
| --- | ---: | ---: | ---: | ---: |
| assistantbench | 20 | n/a | 0% | 95% |
| visualwebarena | 5 | 100% | 50% | 60% |
| webarena | 19 | 71% | 83% | 84% |
| workarena | 16 | 100% | 83% | 94% |

## Where Ember was wrong (2 false 'success', 5 missed successes)

- **webarena/GenericAgent-gpt-4o-2024-11-20/webarena.306** (said Successful, experts said Unsuccessful). Goal: "How many commits did Anthony make between 08/2022-09/2022?". Ember's reasoning: "The agent navigated from the repository to the Commits page, scrolled through the history until the August-September 2022 period was visible, and then reported a count to the user. The final screenshot shows commits grouped by dates in that period, e.g. 22 Sep"
- **webarena/GenericAgent-meta-llama_Llama-3.3-70B-Instruct/webarena.380** (said Successful, experts said Unsuccessful). Goal: "Find the bar around Carnegie Music Hall". Ember's reasoning: "Question 1 - Success: The agent initially searched for "Carnegie Music Hall" but encountered a geocoding error. After repeated map interactions, it searched "bars near Carnegie Music Hall" in step 13-14. The final screenshot shows Search Results from OpenStree"
- **workarena/GenericAgent-gpt-4o-2024-11-20/workarena.servicenow.navigate-and-order-apple-mac-book-pro15-l2** (said Unsuccessful, experts said Successful). Goal: "Order an Apple MacBook Pro 15" from the service catalog    Concretely, you need to complete the following steps: 1. Navigate to the "Service". Ember's reasoning: "Q1: Steps 1-6 correctly navigated Service Catalog > Hardware > Apple MacBook Pro 15", set quantity to 5, and clicked Order Now, which would have fulfilled the goal. However the agent did not stop. Steps 7-10 repeated the Hardware > MacBook > Order Now flow. On"
- **assistantbench/GenericAgent-meta-llama_Llama-3.3-70B-Instruct/assistantbench.improved.validation.4** (said Unsuccessful, experts said Successful). Goal: "Which restaurants (not takeaway only) within 1 blocks of Washington Square Park have vegan mains for under $15?". Ember's reasoning: "Q1: The agent searched for vegan restaurants near Washington Square Park, opened the NYU News list, then repeatedly clicked headings on the same page without reading/verifying addresses, distances, menus, or restaurant type. Its final answer listed V Spot Expr"
- **visualwebarena/GenericAgent-gpt-4o-2024-11-20/visualwebarena.739** (said Unsuccessful, experts said Successful). Goal: "Find me a rug that has the simliar pattern as the animal in the picture. Input image 1/1 below (local path: PosixPath('/tmp/tmpyimvknd1/inpu". Ember's reasoning: "Agent correctly navigated to Home & Kitchen > Home Décor > Rugs, Pads & Protectors, but then scrolled and went to page 2 without searching for the animal's pattern. It identified the animal in the picture as a leopard with spotted pattern in its reasoning, yet"
- **visualwebarena/GenericAgent-gpt-4o-2024-11-20/visualwebarena.248** (said Unsuccessful, experts said Successful). Goal: "Can you help me find and navigate to the comments section of an image post that has something like this image? Input image 1/1 below (local ". Ember's reasoning: "The goal was to find and navigate to the comments section of an image post matching the input image. The agent's only action was clicking bid '261' for the Newark forum, reasoning it matched a cityscape at dusk. The final screenshot shows the agent arrived at "
- **webarena/GenericAgent-anthropic_claude-3.7-sonnet/webarena.171** (said Unsuccessful, experts said Successful). Goal: "Tell me the full names of the repositories where I made contributions and they got less than 5 stars?". Ember's reasoning: "Question 1: The agent stayed on the root URL, performed only one scroll(0,500), and immediately sent a list of 10 repositories. It never navigated to a contributions/membership filter, never scrolled to the bottom, and never verified completeness. The final sc"

Ember averages: 4,446 input tokens, 661 output tokens (377 of them reasoning), 2.9s per run.

Ledger: this run spent $0.0450; total recorded $0.1499 of the $7.00 cap.