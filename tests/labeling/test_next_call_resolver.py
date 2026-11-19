"""Table-driven tests for the next_call_at resolver (rules F1-F12, EX1-EX5)."""

from __future__ import annotations

import pytest

from call_labeling.evidence_schema import CallbackExtraction, TimeExpr
from call_labeling.label_vocabulary import APPOINTMENT, FOLLOW_UP, INVALID, NOT_INTERESTED, UNABLE
from call_labeling.next_call_resolver import resolve_next_call

MON_1400 = "2026-11-09T14:00:00+05:30"  # rulebook EX1-EX4 reference call


def specific(*options: dict, ack: bool = True, vague: bool = False) -> CallbackExtraction:
    return CallbackExtraction(
        specific_callback_agreed=True,
        acknowledged_by_other=ack,
        options=[TimeExpr(**o) for o in options],
        vague_postponement=vague,
    )


NONE = CallbackExtraction()
VAGUE = CallbackExtraction(vague_postponement=True)


CASES = [
    # --- rulebook boundary examples
    ("EX1 tomorrow at 4", specific({"day_ref": "tomorrow", "hour": 4}), FOLLOW_UP, MON_1400, "2026-11-10T16:00:00+05:30"),
    ("EX2 vague +3", VAGUE, FOLLOW_UP, MON_1400, "2026-11-12T11:00:00+05:30"),
    ("EX3 appointment no callback", NONE, APPOINTMENT, MON_1400, None),
    ("EX4 routine agent promise +1", NONE, FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    ("EX5 do-not-contact suppresses", specific({"day_ref": "tomorrow"}), NOT_INTERESTED, MON_1400, None),
    # --- F2 suppression
    ("F2 invalid", specific({"day_ref": "tomorrow"}), INVALID, MON_1400, None),
    ("F2 unable", VAGUE, UNABLE, MON_1400, None),
    # --- F3 acknowledgement / appointment coexistence
    ("F3 unacknowledged -> fallback", specific({"day_ref": "tomorrow"}, ack=False), FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    ("F3 unacknowledged + vague", specific({"day_ref": "tomorrow"}, ack=False, vague=True), FOLLOW_UP, MON_1400, "2026-11-12T11:00:00+05:30"),
    ("F3 distinct callback with appointment", specific({"day_ref": "tomorrow", "daypart": "morning"}), APPOINTMENT, MON_1400, "2026-11-10T10:00:00+05:30"),
    # --- F4 relative days and weekdays (2026-11-09 is a Monday)
    ("F4 day after tomorrow", specific({"day_ref": "day_after_tomorrow"}), FOLLOW_UP, MON_1400, "2026-11-11T11:00:00+05:30"),
    ("F4 in 5 days", specific({"day_ref": "in_days", "n": 5}), FOLLOW_UP, MON_1400, "2026-11-14T11:00:00+05:30"),
    ("F4 bare weekday same day -> +7", specific({"day_ref": "weekday", "weekday": "monday"}), FOLLOW_UP, MON_1400, "2026-11-16T11:00:00+05:30"),
    ("F4 bare weekday later this week", specific({"day_ref": "weekday", "weekday": "thursday"}), FOLLOW_UP, MON_1400, "2026-11-12T11:00:00+05:30"),
    ("F4 this weekday today, future time", specific({"day_ref": "this_weekday", "weekday": "monday", "hour": 5}), FOLLOW_UP, MON_1400, "2026-11-09T17:00:00+05:30"),
    ("F4 this weekday today, past time -> +7", specific({"day_ref": "this_weekday", "weekday": "monday", "hour": 10, "meridiem": "am"}), FOLLOW_UP, MON_1400, "2026-11-16T10:00:00+05:30"),
    ("F4 next weekday -> following week", specific({"day_ref": "next_weekday", "weekday": "thursday"}), FOLLOW_UP, MON_1400, "2026-11-19T11:00:00+05:30"),
    ("F4 next weekday from Sunday", specific({"day_ref": "next_weekday", "weekday": "monday"}), FOLLOW_UP, "2026-11-15T10:00:00+05:30", "2026-11-16T11:00:00+05:30"),
    ("F4 next week -> Monday", specific({"day_ref": "next_week"}), FOLLOW_UP, MON_1400, "2026-11-16T11:00:00+05:30"),
    ("F4 this week alone is vague", specific({"day_ref": "this_week"}), FOLLOW_UP, MON_1400, "2026-11-12T11:00:00+05:30"),
    # --- F5 clock defaults
    ("F5 hour 8 -> AM", specific({"day_ref": "tomorrow", "hour": 8}), FOLLOW_UP, MON_1400, "2026-11-10T08:00:00+05:30"),
    ("F5 hour 12 -> noon", specific({"day_ref": "tomorrow", "hour": 12}), FOLLOW_UP, MON_1400, "2026-11-10T12:00:00+05:30"),
    ("F5 hour 7 -> PM", specific({"day_ref": "tomorrow", "hour": 7}), FOLLOW_UP, MON_1400, "2026-11-10T19:00:00+05:30"),
    ("F5 explicit 7 am wins", specific({"day_ref": "tomorrow", "hour": 7, "meridiem": "am"}), FOLLOW_UP, MON_1400, "2026-11-10T07:00:00+05:30"),
    ("F5 8 in the evening", specific({"day_ref": "tomorrow", "hour": 8, "daypart": "evening"}), FOLLOW_UP, MON_1400, "2026-11-10T20:00:00+05:30"),
    ("F5 4:30", specific({"day_ref": "tomorrow", "hour": 4, "minute": 30}), FOLLOW_UP, MON_1400, "2026-11-10T16:30:00+05:30"),
    ("F5 lunch", specific({"day_ref": "tomorrow", "daypart": "lunch"}), FOLLOW_UP, MON_1400, "2026-11-10T13:00:00+05:30"),
    ("F5 time only, future today", specific({"hour": 6}), FOLLOW_UP, MON_1400, "2026-11-09T18:00:00+05:30"),
    ("F5 time only, past -> tomorrow", specific({"hour": 11}), FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    ("F5 this evening", specific({"day_ref": "today", "daypart": "evening"}), FOLLOW_UP, MON_1400, "2026-11-09T18:00:00+05:30"),
    # --- F6 absolute dates and past times
    ("F6 day number later this month", specific({"day_ref": "date", "day": 26}), FOLLOW_UP, MON_1400, "2026-11-26T11:00:00+05:30"),
    ("F6 day number already passed -> next month", specific({"day_ref": "date", "day": 2}), FOLLOW_UP, MON_1400, "2026-12-02T11:00:00+05:30"),
    ("F6 month/day without year rolls to next year", specific({"day_ref": "date", "day": 5, "month": 1}), FOLLOW_UP, MON_1400, "2027-01-05T11:00:00+05:30"),
    ("F6 explicit past full date rejected", specific({"day_ref": "date", "day": 5, "month": 11, "year": 2026}), FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    ("F6 past same-day time rejected", specific({"day_ref": "today", "hour": 10, "meridiem": "am"}), FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    ("F6 impossible date rejected", specific({"day_ref": "date", "day": 31, "month": 11}), FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    # --- F10 intervals and windows
    ("F10 in 15 minutes keeps seconds", specific({"day_ref": "in_minutes", "n": 15}), FOLLOW_UP, "2026-10-15T14:11:01+05:30", "2026-10-15T14:26:01+05:30"),
    ("F10 in 2 hours", specific({"day_ref": "in_hours", "n": 2}), FOLLOW_UP, MON_1400, "2026-11-09T16:00:00+05:30"),
    ("F10 alternatives -> earliest", specific({"day_ref": "date", "day": 5}, {"day_ref": "date", "day": 4}), FOLLOW_UP, "2026-10-17T18:05:01+05:30", "2026-11-04T11:00:00+05:30"),
    ("F10 earliest ignores past option", specific({"day_ref": "today", "hour": 10, "meridiem": "am"}, {"day_ref": "tomorrow"}), FOLLOW_UP, MON_1400, "2026-11-10T11:00:00+05:30"),
    ("F10 after event is vague", specific({"day_ref": "after_event"}), FOLLOW_UP, MON_1400, "2026-11-12T11:00:00+05:30"),
    # --- F11 months
    ("F11 in one month clamps", specific({"day_ref": "in_months", "n": 1}), FOLLOW_UP, "2026-01-31T12:00:00+05:30", "2026-02-28T11:00:00+05:30"),
    ("F11 in one month across year", specific({"day_ref": "in_months", "n": 1}), FOLLOW_UP, "2026-12-15T12:00:00+05:30", "2027-01-15T11:00:00+05:30"),
    ("F11 bare next month", specific({"day_ref": "next_month"}), FOLLOW_UP, MON_1400, "2026-12-01T11:00:00+05:30"),
    # --- F1 reference timezone
    ("F1 UTC input normalised to IST", specific({"day_ref": "tomorrow"}), FOLLOW_UP, "2026-11-09T20:00:00+00:00", "2026-11-11T11:00:00+05:30"),
]


@pytest.mark.parametrize("name,cb,disposition,start,expected", CASES, ids=[c[0] for c in CASES])
def test_resolver(name, cb, disposition, start, expected):
    assert resolve_next_call(cb, disposition, start).next_call_at == expected
