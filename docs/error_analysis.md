# Error analysis and iteration log

Status: the pipeline, the deterministic rules and the offline validation are complete. **Live model results are pending a run with a Groq key.** Fill in the tables below from `make dev`, `make holdout` and `make predict`. `outputs/predictions.meta.json` provides runtime, tokens and cost.

## 1. What is verified without the model

| Check | Result |
|---|---|
| Resolver reverse test: hand-written callback descriptors reproduce the gold `next_call_at` | **50 / 50** |
| Rulebook boundary examples EX1-EX5, plus edge cases for F1-F12 | 45 / 45 |
| Combiner: every allowed disposition/sub_disposition pair is reachable | 21 / 21 pairs |
| Output contract, fallback record, failure isolation, guardrails | pass |
| Baseline: fallback record for every call (scored with `evaluate.py`) | 23.1 / 70 label points; disposition 72%, lead quality 66%, next_call_at 10%, sub_disposition 2% |

Because the resolver reproduces all 50 gold timestamps from correct descriptors, any `next_call_at` error in a live run comes from extraction (a misread callback, acknowledgement or postponement), not from date arithmetic. Debugging can go straight to the `callback` block in `debug.jsonl`.

## 2. Gold-label structure that shaped the design

- Dispositions: 36 Follow-up Required, 12 Appointment Scheduled, 2 Not Interested. No Invalid Lead, Unable to Assess, Do Not Contact, Online Consultation or Rescheduled appear, so those branches are rule-driven and covered by unit tests plus `tests/synthetic/` (10 hand-labeled calls).
- `next_call_at` for follow-ups: 19 use the vague +3 days fallback, 5 fall on the next day at 11:00 (AVT-048 through an explicit "call you tomorrow"), and 12 have another specific acknowledged callback. Appointments and refusals are always null. Vague-postponement detection is therefore the most valuable single extraction for this field.
- All 12 appointments are Clinic Visit / High. Travel Constraint is the most common follow-up blocker (14 of 36) and is used broadly.

## 3. Policy interpretations chosen

| Situation | Interpretation | Basis |
|---|---|---|
| Customer: "I'll call you myself / I'll let you know / once he's back" | Vague postponement, so +3 days | F7. Matches AVT-001, 007 and 022 |
| Work, business or office hours clash; "busy until the 22nd"; patient temporarily away | Travel Constraint | SUB definition ("work or clinic timing"). Matches gold usage |
| "Forget it" said out of frustration while the need is still open | Not a final refusal | D2. AVT-042 gold is Follow-up |
| Customer gives a vague postponement, then the agent says "I'll call you tomorrow" and gets an "alright" | Specific callback (tomorrow, 11:00) | F3. AVT-048 |
| Agent proposes "the 26th" after the customer says "after the 25th", and the customer accepts | Specific callback on the 26th | F3/F10. AVT-017 |
| Date given as a day number only ("on the 22nd") | Next future occurrence: this month if not past, else next month | F6 extended to day-only dates |
| "night" daypart | 20:00 | Not defined by the policy; nearest sensible reading |
| Appointment whose slot day can't be resolved | High | Every sample booking is High. A resolvable slot at offset 7 or more gives Medium (EX6) |
| Follow-up with an explicit, unblocked visit commitment within offsets 0-6 | High | LQ "High" does not require a booking. Never observed in the sample |

## 4. Live results (to fill)

| Split | n | disposition | sub_disposition | lead_quality | next_call_at | exact match | label points / 70 |
|---|---|---|---|---|---|---|---|
| dev (iteration) | 35 | | | | | | |
| holdout (frozen prompt, single run) | 15 | | | | | | |
| all 50 (submission) | 50 | | | | | | |
| synthetic rare labels | 10 | | | | | | |

Runtime, tokens and cost (from `predictions.meta.json`): wall time __, mean per record __, tokens in/out __/__, about $__. At list price ($0.15 / $0.60 per 1M tokens) and roughly 2 × 4k input tokens per record, 50 records cost on the order of $0.10.

## 5. Failure classes to check first

For each mismatch printed by `evaluate.py`, open the record in `debug.jsonl` and read the `facts`, `callback` and `trace` blocks.

1. Travel Constraint confused with Specific Callback, when the customer is away but gives a date. The combiner lets any named blocker win over Specific Callback, so this error appears only if `blockers` comes back empty.
2. An agent proposal treated as a mutual booking (`slot_confirmed_by_both` true on an offer).
3. A missed vague postponement, which turns +3 days into +1 day. This is the highest-frequency risk for `next_call_at`.
4. A missed callback acknowledgement, or a consultation slot misread as a callback.
5. Weekday or day-number encoding mistakes (for example "next Friday" versus "Friday").

## 6. Iteration log

One line per change, with the measured effect on dev. With 35 dev calls, one record is about 2.9 points of field accuracy, so a single-record change is within noise.

| # | Change | dev effect |
|---|---|---|
| 0 | Initial prompts (no few-shot examples), rules as committed | pending |

## 7. Disclosures

- During initial data inspection, before the split existed, I printed the closing turns of AVT-022 and AVT-042 (now in holdout) and the timing lines of a few other calls. No prompt text was tuned to them. The holdout number should still be read with that caveat.
- No few-shot examples from the labeled set are used. The prompts paraphrase the supplied policy only.

## 8. With more time

- Self-consistency on the callback call (several samples, majority vote on the descriptor), applied only when the descriptor and the vague flag disagree.
- A per-field confidence signal, sending low-confidence records to human review.
- A larger labeled set for Invalid Lead and Unable to Assess, which are absent from the sample.
