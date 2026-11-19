"""Reverse test: hand-written callback descriptors must reproduce every gold next_call_at.

This isolates the resolver from extraction. If it passes, any next_call_at
error in an end-to-end run is an extraction error, not a rule misreading.
Gold labels are read here only for testing; they never reach inference.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from call_labeling.evidence_schema import CallbackExtraction, TimeExpr
from call_labeling.next_call_resolver import resolve_next_call

DATA = Path(__file__).resolve().parents[2] / "data"


def _specific(*options: dict) -> CallbackExtraction:
    return CallbackExtraction(
        specific_callback_agreed=True, acknowledged_by_other=True, options=[TimeExpr(**o) for o in options]
    )


VAGUE = CallbackExtraction(vague_postponement=True)
NONE = CallbackExtraction()

# Callback evidence read from each transcript's closing next-step agreement.
SPECIFIC = {
    "AVT-004": _specific({"day_ref": "tomorrow", "daypart": "evening"}),     # "follow-up from you by tomorrow evening"
    "AVT-011": _specific({"day_ref": "tomorrow", "daypart": "afternoon"}),   # "I'll call you tomorrow afternoon"
    "AVT-014": _specific({"day_ref": "weekday", "weekday": "friday"}),       # "I will give you a call once on Friday"
    "AVT-017": _specific({"day_ref": "date", "day": 26}),                    # "shall I call you on the 26th" / "Okay"
    "AVT-023": _specific({"day_ref": "date", "day": 22}),                    # "I'll contact you again on the 22nd"
    "AVT-026": _specific({"day_ref": "weekday", "weekday": "wednesday"}),    # "I'll call you back on Wednesday"
    "AVT-029": _specific({"day_ref": "date", "day": 4, "month": 11},
                         {"day_ref": "date", "day": 5, "month": 11}),        # "call me on the 4th or 5th"
    "AVT-035": _specific({"day_ref": "day_after_tomorrow"}),                 # "I'll call you the day after tomorrow"
    "AVT-040": _specific({"day_ref": "next_week"}),                          # "Should I call next week?"
    "AVT-044": _specific({"day_ref": "today", "daypart": "evening"}),        # "Call me this evening"
    "AVT-047": _specific({"day_ref": "in_minutes", "n": 15}),                # "I will tell you in 15 minutes"
    "AVT-049": _specific({"day_ref": "date", "day": 21}),                    # "we'll talk on the 21st"
    "AVT-024": _specific({"day_ref": "after_event"}),                        # "after Dussehra" (unbounded -> vague)
}
NO_POSTPONEMENT = {"AVT-015", "AVT-041", "AVT-042", "AVT-048", "AVT-050"}


def _gold_rows():
    calls = {c["transcript_id"]: c for c in map(json.loads, (DATA / "calls_input.jsonl").open())}
    for g in map(json.loads, (DATA / "gold_labels.jsonl").open()):
        yield g, calls[g["transcript_id"]]


@pytest.mark.parametrize("gold,call", list(_gold_rows()), ids=lambda x: x.get("transcript_id", ""))
def test_gold_next_call_reproduces(gold, call):
    tid = gold["transcript_id"]
    cb = SPECIFIC.get(tid) or (NONE if tid in NO_POSTPONEMENT else VAGUE)
    got = resolve_next_call(cb, gold["disposition"], call["call_started_at"], call["timezone"])
    assert got.next_call_at == gold["next_call_at"], got.rule
