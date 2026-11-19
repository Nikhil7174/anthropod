PY ?= .venv/bin/python
ids = $(shell $(PY) -c 'import json; print(",".join(json.load(open("data/splits.json"))["$(1)"]))')

.PHONY: setup test dev holdout predict synthetic

setup:
	python3.11 -m venv .venv && $(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest

dev:  ## iterate here
	$(PY) run.py --input data/calls.jsonl --output outputs/runs/dev.jsonl --ids "$(call ids,dev)"
	$(PY) -m fde.labeler.evaluate --pred outputs/runs/dev.jsonl --split dev

holdout:  ## run once, after the prompt is frozen
	$(PY) run.py --input data/calls.jsonl --output outputs/runs/holdout.jsonl --ids "$(call ids,holdout)"
	$(PY) -m fde.labeler.evaluate --pred outputs/runs/holdout.jsonl --split holdout

predict:  ## submission file for all 50
	$(PY) run.py --input data/calls.jsonl --output outputs/predictions.jsonl
	$(PY) -m fde.labeler.evaluate --pred outputs/predictions.jsonl

synthetic:  ## rare labels absent from the supplied sample
	$(PY) run.py --input tests/synthetic/calls.jsonl --output outputs/runs/synthetic.jsonl
	$(PY) -m fde.labeler.evaluate --pred outputs/runs/synthetic.jsonl --gold tests/synthetic/gold.jsonl
