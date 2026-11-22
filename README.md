# Aster Vale FDE Assignment

Two tasks, two packages. Each has its own command and can be read without the other.

| Task | What it predicts | Command |
|---|---|---|
| 1. Call labeling | `disposition`, `sub_disposition`, `lead_quality`, `next_call_at` | `python -m call_labeling.run_labeling` |
| 2. Customer gender | gender of the caller, without a transformer model | `python -m customer_gender.run_gender` |

Task 1 is implemented under policy **assignment-v2**. The model reports evidence; Python applies the policy. Task 2 is a weighted vote of speech cues and does not call a model.

## Setup

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
export CEREBRAS_API_KEY=...        # or put it in .env (gitignored; see .env.example)
# optional, only for --provider groq:
export GROQ_API_KEY=...
```

## Task 1

```bash
.venv/bin/python -m call_labeling.run_labeling \
    --input data/calls_input.jsonl --output outputs/labeling_predictions.jsonl
```

- Input: JSONL with `transcript_id`, `call_started_at`, `timezone` and `transcript`. Any other key is dropped when the file is loaded.
- Output: one JSON object per input, in input order, with exactly those five keys: `transcript_id`, `disposition`, `sub_disposition`, `lead_quality`, `next_call_at`.
- `outputs/debug/` holds the extracted evidence, quotes, decision trace and token usage. `outputs/labeling_predictions.meta.json` holds runtime, tokens, estimated cost and the exact settings used.
- Reference answers live only in `data/gold_labels.jsonl`. Nothing in `call_labeling/` reads that file.

```bash
make test        # offline tests
make dev         # 35 dev calls, then the score
make holdout     # 15 holdout calls, run once after the prompts are frozen
make predict     # all 50, the submission file
make synthetic   # rare labels that do not appear in the supplied sample
```

### Model and generation settings

Pinned in [`call_labeling/settings.py`](call_labeling/settings.py) and copied into every run's meta file.

| Setting | Value |
|---|---|
| Provider / model | Cerebras, `qwen-3.8-27b` (open weights). `--provider groq` runs the same open model on Groq as `qwen/qwen3.8-27b`. `LABELING_MODEL` in `.env` overrides the default; `--model` overrides that |
| temperature / top_p / seed | 0.0 / 1.0 / 7 |
| reasoning_effort | `high`. Cerebras returns reasoning separately (`reasoning_format=parsed`); Qwen rejects `hidden`. Groq sets `include_reasoning=false` |
| max_completion_tokens | 8192 (includes reasoning) |
| Output format | `json_schema` with `strict: true`, generated from the Pydantic models |
| Calls per record | 1 by default: outcome and callback in one JSON object. `--calls 2` asks for them separately. `--votes 3` repeats the extraction and keeps a blocker only when a majority agrees |
| Request timeout | 90 s |
| Retries | Up to 10 attempts on 429, 5xx, timeouts and connection errors. Backoff is exponential (2 s base, 60 s cap) with jitter and honours `retry-after`. A daily quota stops the run and keeps finished records. |
| JSON parsing | Code fences or surrounding prose are stripped, then Pydantic validation runs. One repair re-ask is made on invalid JSON or a `json_validate_failed` error. |
| Concurrency | 2 records in parallel (`--concurrency`). Qwen 3.8 on the Cerebras free trial allows 300 requests per minute |

The `openai` package is only the HTTP client. Cerebras and Groq both expose an OpenAI-compatible chat API. No closed OpenAI model is called.

Dependencies, pinned in `requirements.txt`: Python 3.11, `openai==3.57.0` (HTTP client only), `pydantic==2.14.4`, `openpyxl==3.1.5` (workbook export only), `pytest==9.2.0`.

### How a call becomes four labels

```
record -> normalise whitespace (wording untouched) -> user message with call time and weekday
       -> extract_call_outcome.md   validity, refusal, booking, blockers, readiness, discussion, plus quotes
       -> extract_callback.md       was a callback agreed and acknowledged, and the time as spoken, plus a quote
       -> label_rules.py            precedence, allowed pair, tie-break, lead quality
       -> next_call_resolver.py     spoken time + call_started_at -> next_call_at (never the machine clock)
       -> output_validator.py       five keys, allowed pair, +05:30 with seconds, real null
```

- The model never computes a date. It encodes what was said, for example `{day_ref: tomorrow, daypart: evening}`. Python resolves that against `call_started_at`.
- Callback timing is its own prompt. It is the most error-prone question and worth 20 points.
- One failed record does not stop the run. After retries it gets a documented fallback (`Follow-up Required / Further Discussion / Medium / next day 11:00`). A transcript with no customer speech is `Unable to Assess` and the model is not called.
- There is no per-record logic, no id lookup and no few-shot example taken from the labeled calls. `tests/labeling/test_guardrails.py` fails if `call_labeling/` mentions the reference file, imports `evaluation`, reads the machine clock, or contains a transcript id.

The design and the run history are in [`docs/task1_process.md`](docs/task1_process.md). Failure classes and the early iteration log: [`docs/error_analysis_labeling.md`](docs/error_analysis_labeling.md).

## Task 2

The label is the **caller marked Customer**, not the patient. Caregivers are common, so "my mother" does not make the customer female. The result is inferred from speech cues. It is `unknown` when those cues are thin or mixed. No transformer and no LLM API is used.

The method is a weighted vote of labeling functions. Each family votes male, female, or abstains:

| Family | Cue | Weight |
|---|---|---|
| A | Agent addresses the customer as sir, ma'am, Mr, or Mrs. Third person ("the madam will", "ma'am has") is dropped. The customer's own sir/ma'am is dropped, because that is the agent's gender | log ratio of the two counts |
| B | "my husband / my wife", or the agent saying "your husband / your wife" | 1.5, once per side |
| C | "I am her son", "I am Renu's husband" | 2.0, once per side |
| D | "my name is" plus a name in the list | 0.5, once per side |
| E | Agent says bhai, didi, beta, or behen to the customer | 0.5, once per side |

A label is emitted only when the margin is at least 0.6 and the total evidence is at least 0.75. If both honorifics appear and that margin fails, the later half of the call can break the tie. Those constants were set before scoring and were not refit on the errors.

```bash
.venv/bin/python -m customer_gender.run_gender \
    --input data/calls_input.jsonl --output outputs/gender_predictions.jsonl
.venv/bin/python -m evaluation.eval_gender \
    --pred outputs/gender_predictions.jsonl \
    --gold customer_gender/gender_labels_manual.jsonl
```

Hand labels are in `customer_gender/gender_labels_manual.jsonl`, separate from task 1's gold file. `data/splits/gender_holdout_ids.txt` is 15 calls that were not used to choose the cue rules. The design is in [`docs/task2_process.md`](docs/task2_process.md). What those 50 transcripts show, and what they do not, is in [`docs/error_analysis_gender.md`](docs/error_analysis_gender.md).

## Layout

```
data/calls_input.jsonl            the only file inference reads
data/gold_labels.jsonl            reference answers for task 1
data/splits/                      dev_ids.txt, holdout_ids.txt, gender_holdout_ids.txt
data/raw/                         original workbook, not committed
call_labeling/                    task 1
  run_labeling.py                 command line
  settings.py                     pinned model and runtime settings
  llm_client.py                   Cerebras or Groq: strict schema, retries, repair, usage
  evidence_schema.py              what the model is allowed to return
  evidence_extraction.py          the two model calls
  prompts/                        extract_call_outcome.md, extract_callback.md, time_expression.md
  label_vocabulary.py             allowed labels and pairs
  label_rules.py                  disposition, sub_disposition, lead quality
  next_call_resolver.py           callback rules F1-F12
  output_validator.py             output contract and the fallback record
  label_one_call.py               one record, including the fallback path
  input_records.py                JSONL loading; drops every non-input field
  transcript_text.py              whitespace normalisation and turn splitting
customer_gender/                  task 2
evaluation/                       scoring; imported by neither task
tests/labeling/                   resolver, rules, one-call path, guardrails, synthetic calls
tests/gender/
outputs/                          labeling_predictions.jsonl, gender_predictions.jsonl, debug/
docs/error_analysis_labeling.md
scripts/                          workbook export and the dev/holdout split
```

## Data

`scripts/export_workbook.py` writes `data/calls_input.jsonl` and `data/gold_labels.jsonl` from the candidate workbook. The sheet's literal `null` becomes JSON `null`. `scripts/make_split.py` writes the seeded 35/15 split as one id per line. Prompt work uses dev only. Holdout is scored once, after the prompts are frozen.

## Tests

```bash
.venv/bin/python -m pytest
```

The suite includes a reverse test: hand-written callback descriptions for all 50 labeled calls reproduce every reference `next_call_at`. A `next_call_at` miss in a live run is therefore the model misreading the call, not the date arithmetic.
