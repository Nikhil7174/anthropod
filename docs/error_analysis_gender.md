# Task 2 error analysis

The customer is the caller, not the patient. The submitted method is the weighted vote in `customer_gender/gender_scoring.py`. Weights were set from the cue strengths (A strong, B medium, C medium-to-strong, D and E weak) and were not changed after these scores.

Hand labels for all 50 calls are in `customer_gender/gender_labels_manual.jsonl`: 35 male, 14 female, 1 unclear (AVT-008, because a husband and a wife both speak). The same honorifics a person uses to label a call are the ones family A counts, so agreement with the hand labels is partly circular. The separate check is whether family A agrees with families B and C when both fire.

`data/splits/gender_holdout_ids.txt` holds 15 calls that were not among the examples used to design the cue rules. They were labeled, then scored once.

## Agreement with the hand labels

These numbers are agreement on this clinic's 50 transcripts. They are not a general accuracy. The hand labels were read from the same address terms and relationship words the rules count.

| Slice | Calls where both sides said male or female | Rules left unknown | Hand label left unclear |
|---|---|---|---|
| All 50 | 48 agree | 1/50 | 1 (AVT-008) |
| Design 35 | 33 agree | 1/35 | 1 |
| Holdout 15 | 15 agree | 0/15 | 0 |

A call is left out of the "agree" count when the prediction or the hand label is unknown. Two calls are not a simple match:

| Id | Hand label | Prediction | Why |
|---|---|---|---|
| AVT-008 | unclear | male | Both spouses speak. The later half of the call is the husband arranging the visit, so the tie-break says male. The hand label refuses to pick one person. |
| AVT-039 | male | unknown | The caller gives his name as Zayan and the agent never says sir or ma'am. Zayan is not in the frozen name list, so family D abstains. That is the intended behavior of a weak list, not a miss to patch by adding the name. |

## Ablations

| Variant | Agreement where both sides committed | Unknown predictions |
|---|---|---|
| Frozen rules | 48/48 | 1/50 |
| Third-person filter off | 47/48 | 1/50 |
| Family A only | 48/48 | 1/50 |

Turning the filter off changes AVT-015. The agent says sir to the son who is calling about his mother, and also says "the madam will tell you" about the doctor. Without the filter that doctor line votes female and the call is labeled female. With the filter it stays male, which matches the hand label.

Family A alone matches the full rules on every call where both the rules and the hand label committed. B and C never contradicted A on the 10 calls where both were present.

## Logistic regression comparison

`evaluation/gender_loo.py` is not the submitted method. It fits a bag-of-words logistic regression with L2 regularization and tests each call on a model trained on the other male and female hand labels. AVT-008 is excluded, because one unclear label cannot train a third class. The vocabulary is rebuilt inside each fold. No extra package is imported.

On the 49 male and female hand labels it agrees on 42 (85.7%). Always guessing male agrees on 35 (71.4%). All 7 misses are female callers predicted male: AVT-010, AVT-021, AVT-026, AVT-030, AVT-036, AVT-043, AVT-046. A small male-heavy set pushes a learned model toward the majority. The rules stay the submission because they abstain when the evidence is thin and because each vote is a quoted span.

The weights and thresholds scored above are the ones in commit `ff50c73589406e60c618c534786474e583faa4b6`, tagged `gender-weights-frozen`. That commit is the parent of this citation. `gender_scoring.py` is unchanged between the tag and this note.
