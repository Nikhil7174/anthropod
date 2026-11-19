PY ?= .venv/bin/python
ids = $(shell paste -sd, data/splits/$(1)_ids.txt)

.PHONY: setup test dev holdout predict synthetic

setup:
	python3.11 -m venv .venv && $(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest

dev:  ## task 1, iterate here
	$(PY) -m call_labeling.run_labeling --input data/calls_input.jsonl --output outputs/runs/dev.jsonl --ids "$(call ids,dev)"
	$(PY) -m evaluation.eval_labeling --pred outputs/runs/dev.jsonl --split dev

holdout:  ## task 1, once, after the prompts are frozen
	$(PY) -m call_labeling.run_labeling --input data/calls_input.jsonl --output outputs/runs/holdout.jsonl --ids "$(call ids,holdout)"
	$(PY) -m evaluation.eval_labeling --pred outputs/runs/holdout.jsonl --split holdout

predict:  ## task 1 submission file
	$(PY) -m call_labeling.run_labeling --input data/calls_input.jsonl --output outputs/labeling_predictions.jsonl
	$(PY) -m evaluation.eval_labeling --pred outputs/labeling_predictions.jsonl

synthetic:  ## task 1 rare labels absent from the supplied sample
	$(PY) -m call_labeling.run_labeling --input tests/labeling/synthetic_calls/calls_input.jsonl --output outputs/runs/synthetic.jsonl
	$(PY) -m evaluation.eval_labeling --pred outputs/runs/synthetic.jsonl --gold tests/labeling/synthetic_calls/gold_labels.jsonl
