# Aster Vale FDE Assignment

Task 1 labels pain-clinic enrollment calls with `disposition`, `sub_disposition`, `lead_quality` and `next_call_at` under policy **assignment-v2**.

**Design principle: the LLM reads, code decides.** The model answers small, evidence-backed questions. Deterministic Python then applies outcome precedence, the allowed label pairs, lead-quality ordering and all calendar arithmetic, so every rule in the policy is visible in code and covered by unit tests.

## Run

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
export GROQ_API_KEY=...            # or put GROQ_API_KEY=... in .env (gitignored)
.venv/bin/python run.py --input data/calls.jsonl --output outputs/predictions.jsonl
```

- Input: JSONL with `transcript_id`, `call_started_at`, `timezone` and `transcript`. Any other key is dropped when the file is loaded.
- Output: one JSON object per input, in input order, with exactly `transcript_id, disposition, sub_disposition, lead_quality, next_call_at`.
- Side files: `outputs/debug.jsonl` holds the per-record extracted facts, evidence quotes, a decision trace and token usage. `outputs/predictions.meta.json` holds the run time, token totals, estimated cost and the exact settings used.

The `make` targets cover the development loop: `make test`, `make dev` (dev split plus score), `make holdout`, `make predict` (all 50 plus score) and `make synthetic` (rare-label set).

## Model and generation settings

These are pinned in [`fde/labeler/config.py`](fde/labeler/config.py) and copied into every run's meta file.

| Setting | Value |
|---|---|
| Provider / model | Groq, `openai/gpt-oss-120b` (open weights) |
| temperature / top_p / seed | 0.0 / 1.0 / 7 |
| reasoning_effort | `medium` (reasoning text not returned) |
| max_completion_tokens | 8192 (includes reasoning) |
| Output format | `json_schema` with `strict: true`, generated from the Pydantic models |
| Calls per record | 2: call facts and callback |
| Request timeout | 90 s |
| Retries | Up to 6 attempts on 429, 5xx, timeouts and connection errors. Backoff is exponential (2 s base, 60 s cap) with jitter and honours `retry-after`. |
| JSON parsing | Code fences or surrounding prose are stripped, then Pydantic validation runs. One repair re-ask is made on invalid JSON or a Groq `json_validate_failed` error. |
| Concurrency | 4 records in parallel (`--concurrency`) |

Dependencies (pinned in `requirements.txt`): Python 3.11, `groq==1.7.0`, `pydantic==2.14.4`, `openpyxl==3.1.5` (data export only) and `pytest==9.2.0`.

## How it works

```
record -> normalise whitespace (wording untouched) -> user message with call time and weekday
       -> LLM call A: call facts       (validity, refusal, booking, blockers, readiness, discussion + quotes)
       -> LLM call B: callback facts   (agreed?, acknowledged?, time expression(s) as spoken, vague postponement + quote)
       -> combine.py   D6 precedence -> disposition -> sub_disposition (tie-break order) -> lead_quality (LQ order)
       -> callback.py  F1-F12: time expression + call_started_at -> next_call_at (never the machine clock)
       -> validate.py  five keys, allowed pair, +05:30 with seconds, real null
```

- **The model never computes dates.** It encodes what was said, for example `{day_ref: tomorrow, daypart: evening}` or `{day_ref: date, day: 26}`. Python resolves that against `call_started_at`.
- **Callback timing is a separate prompt.** It is the most error-prone question and is worth 20 points.
- **Failures are isolated per record.** If extraction still fails after retries, that record gets a documented fallback (`Follow-up Required / Further Discussion / Medium / next day 11:00`, which keeps the lead open), the error is logged in `debug.jsonl`, and the run continues. A transcript with no customer speech is labeled Unable to Assess without calling the model.
- **No per-record logic.** There are no ID or hash lookups and no few-shot examples from the labeled set. The prompts paraphrase the policy only. `tests/test_guardrails.py` fails if inference code references gold labels, the evaluator, the machine clock or a transcript ID.

## Repository layout

```
run.py                       one-command runner
fde/io.py, fde/transcript.py shared input contract, JSONL I/O, turn parsing (reused by task 2)
fde/labeler/
  config.py                  pinned model and runtime settings
  prompts/                   facts.md, callback.md, time_expr.md (complete prompt text)
  schema.py                  extraction schema and output model
  llm.py                     Groq client: strict schema, retries, repair, usage
  extract.py                 prompt assembly and the two calls
  combine.py                 disposition / sub_disposition / lead_quality rules
  callback.py                next_call_at resolver (F1-F12)
  validate.py                output contract and fallback record
  pipeline.py                per-record orchestration and isolation
  evaluate.py                scoring (evaluation only, never imported by run.py)
scripts/                     workbook export, dev/holdout split
data/                        calls.jsonl (inputs), gold.jsonl (labels), splits.json
tests/                       resolver, combiner, pipeline, guardrails, synthetic rare-label set
docs/error_analysis.md       results, failure classes, iteration log
```

## Data

`scripts/export_workbook.py` converts the candidate workbook into `data/calls.jsonl` (inputs only) and `data/gold.jsonl` (labels only; the literal `null` becomes JSON `null`). `scripts/make_split.py` makes a seeded, stratified split of 35 dev and 15 holdout calls. Prompt iteration uses dev only, and holdout is scored once after the prompt is frozen.

## Tests

```bash
.venv/bin/python -m pytest      # 138 tests, offline, under 1 s
```

The suite includes a **reverse test**. Hand-written callback descriptors for all 50 labeled calls must reproduce every gold `next_call_at` (50/50). Because the resolver is verified on its own, any `next_call_at` miss in a live run is an extraction error rather than a misread rule.
