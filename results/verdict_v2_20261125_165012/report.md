# Verdict v2 evaluation (dev split, effort minimal, 4 screenshots)

v2 judged 60 runs; 60 also have a v1 (`minimal`) verdict for the side-by-side.

## Did the agent succeed? (same runs, expert labels)

| Judge | Precision | Recall | F1 | Accuracy | Cost per 1,000 runs |
| --- | ---: | ---: | ---: | ---: | ---: |
| v1 fair-comparison prompt (`minimal`) | 87% | 72% | 79% (61%–92%) | 88% (80%–95%) | $0.55 |
| **Verdict v2** | 92% | 67% | 77% (57%–91%) | 88% (80%–95%) | $0.84 |

- v2 minus v1, accuracy: +0.0 points (95% CI -5.0 to +5.0)
- v2 minus v1, f1: -1.4 points (95% CI -11.7 to +7.1)
- v2 minus v1, precision: +5.6 points (95% CI -2.1 to +20.0)
- v2 minus v1, recall: -5.6 points (95% CI -17.6 to +0.0)

## Side effects and looping (v1 vs v2, same runs)

| Question | Judge | Accuracy | Precision | Recall | Judge said yes | Experts said yes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Side effects | v1 | 77% | 24% | 80% | 17 | 5 |
| Side effects | v2 | 93% | 67% | 40% | 3 | 5 |
| Looping | v1 | 85% | 72% | 100% | 32 | 23 |
| Looping | v2 | 93% | 88% | 96% | 25 | 23 |

## "Claimed done, but failed"

- The agent claimed success in 18 of 60 runs (per v2).
- v2 flagged 9 of those as **claimed done but failed**; experts agree the run failed in 7 of 9 (78%).

## Failure types (v2, failed runs)

looping: 18, blocked: 9, gave_up: 8, false_completion: 5, wrong_answer: 4, wrong_target: 2, other: 1


## Confidence and escalation

| Confidence | Runs | Accuracy vs experts |
| --- | ---: | ---: |
| high | 57 | 93% |
| medium | 3 | 0% |
| low | 0 | n/a |

- v2 sends **2 of 60 runs (3%)** to a person. Accuracy on the runs it decides alone: 91%.
- If a person settles the flagged runs, overall accuracy becomes 92% (from 88%).

## Cost

- v2: $0.84 per 1,000 runs; 7,746 input tokens, 252 output (105 reasoning), 2.7s per run, 3.9 screenshots per run.

## Where v2 disagrees with the experts (7)

- **assistantbench/GenericAgent-gpt-4o-2024-11-20/assistantbench.improved.validation.4**: experts Successful, v2 Unsuccessful (wrong_answer, confidence medium, flagged for review). Goal: "Which restaurants (not takeaway only) within 1 blocks of Washington Square Park have vegan mains for under $15". Evidence: step 4, S4: "One block from Washington Square Park lies a restaurant offering... dan dan noodles ($11) and cumin-spiced tofu ($17)"
- **visualwebarena/GenericAgent-gpt-4o-2024-11-20/visualwebarena.739**: experts Successful, v2 Unsuccessful (gave_up, confidence medium). Goal: "Find me a rug that has the simliar pattern as the animal in the picture.
Input image 1/1 below (local path: Po". Evidence: step 7, FINAL: "ULTRUG Cowhide Rug Faux Cow Print Area Rug ... White and Brown, 2.3ft x 3.6ft"
- **assistantbench/GenericAgent-meta-llama_Llama-3.3-70B-Instruct/assistantbench.improved.validation.4**: experts Successful, v2 Unsuccessful (wrong_answer, confidence high). Goal: "Which restaurants (not takeaway only) within 1 blocks of Washington Square Park have vegan mains for under $15". Evidence: step 12, S12: "V Spot Express, Spicy Moon, and Peacefood Café have vegan options under $15 near Washington Square Park."
- **visualwebarena/GenericAgent-gpt-4o-2024-11-20/visualwebarena.248**: experts Successful, v2 Unsuccessful (gave_up, confidence high). Goal: "Can you help me find and navigate to the comments section of an image post that has something like this image?". Evidence: step 2, FINAL: "/f/Newark submissions list with 'Doesn't Newark look amazing right now?' etc., no post comments opened"
- **workarena/GenericAgent-anthropic_claude-3.7-sonnet/workarena.servicenow.filter-requested-items-and-order-apple-mac-book-pro15-l2**: experts Successful, v2 Unsuccessful (wrong_target, confidence medium, flagged for review). Goal: "Order same item as Wesley-Natalie Perry-Bush
 
 Concretely, you need to complete the following steps:
1. Navig". Evidence: step 24, FINAL: "No records to display after filter for Wesley-Natalie Perry-Bush; final order is MacBook Pro quantity 3 submitted as REQ0010283 with no evid"
- **workarena/GenericAgent-gpt-4o-2024-11-20/workarena.servicenow.navigate-and-order-apple-mac-book-pro15-l2**: experts Successful, v2 Unsuccessful (other, confidence high). Goal: "Order an Apple MacBook Pro 15" from the service catalog
 
 Concretely, you need to complete the following step". Evidence: step 11, FINAL: "Final Order Status: Apple MacBook Pro Quantity 1 Total $1,099.99 REQ0010107; S10 shows Quantity 1 before second Order Now click"
- **visualwebarena/GenericAgent-anthropic_claude-3.7-sonnet/visualwebarena.resized.352**: experts Unsuccessful, v2 Successful (none, confidence high). Goal: "What is the birth year of the guy in red jacket? Answer using the Wikipedia site in the second tab.". Evidence: step 20, S20: "Red Jacket (born 15 April 1879, date of death unknown) was a Canadian lacrosse player"

Ledger: this run spent $0.0506; total recorded $0.9747 of the $7.00 cap.