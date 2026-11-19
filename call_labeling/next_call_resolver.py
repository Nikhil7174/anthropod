"""Resolve an extracted callback description into next_call_at (rules F1-F12).

Pure, deterministic and clock-free: every date is computed from
call_started_at in the record's timezone, never from the machine clock.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from .evidence_schema import CallbackExtraction, TimeExpr
from .label_vocabulary import APPOINTMENT, CALLBACK_SUPPRESSED

DEFAULT_TIME = time(11, 0)
DAYPART_TIME = {  # F5
    "morning": time(10, 0),
    "lunch": time(13, 0),
    "afternoon": time(15, 0),
    "evening": time(18, 0),
    "night": time(20, 0),  # not defined by policy; nearest sensible reading
}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
VAGUE_DAY_REFS = frozenset({"this_week", "after_event"})


class _Vague:
    """Sentinel: the expression is a vague postponement, not a resolvable time."""


VAGUE = _Vague()


@dataclass(frozen=True)
class Resolution:
    next_call_at: Optional[str]
    rule: str


def parse_call_start(call_started_at: str, tz: str = "Asia/Kolkata") -> datetime:
    dt = datetime.fromisoformat(call_started_at)
    zone = ZoneInfo(tz)
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)


def format_ts(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# --------------------------------------------------------------------------- clock (F5)

def _clock(expr: TimeExpr) -> Optional[time]:
    if expr.hour is None:
        return DAYPART_TIME.get(expr.daypart, DEFAULT_TIME)
    h, m = expr.hour, expr.minute or 0
    if h == 0 or h >= 13:
        pass
    elif expr.meridiem == "am":
        h = 0 if h == 12 else h
    elif expr.meridiem == "pm" or expr.daypart in {"afternoon", "evening", "night"}:
        h = h if h == 12 else h + 12
    elif expr.daypart == "morning":
        pass
    elif 1 <= h <= 7:
        h += 12
    return time(h, m)


def _has_clock(expr: TimeExpr) -> bool:
    return expr.hour is not None or expr.daypart is not None


# --------------------------------------------------------------------------- day (F4, F6, F11)

def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _explicit_date(expr: TimeExpr, start: datetime, clock: time) -> Optional[datetime]:
    """Explicit day number, optionally with month/year. F6: next future occurrence if year missing."""
    today = start.date()
    if expr.year is not None:
        d = _safe_date(expr.year, expr.month or today.month, expr.day)
        return datetime.combine(d, clock, start.tzinfo) if d else None  # past full dates rejected later

    if expr.month is not None:
        candidates = [_safe_date(today.year, expr.month, expr.day), _safe_date(today.year + 1, expr.month, expr.day)]
    else:
        nxt = _add_months(today.replace(day=1), 1)
        candidates = [_safe_date(today.year, today.month, expr.day), _safe_date(nxt.year, nxt.month, expr.day)]
    for d in candidates:
        if d is None or d < today:
            continue
        # Same-day past time is rejected (F6) rather than rolled forward a month/year.
        return datetime.combine(d, clock, start.tzinfo)
    return None


def resolve_expr(expr: TimeExpr, start: datetime):
    """Return an aware datetime, VAGUE, or None (unresolvable / invalid)."""
    ref = expr.day_ref
    if ref in VAGUE_DAY_REFS:
        return VAGUE

    if ref in {"in_minutes", "in_hours"}:  # F10: from call start, seconds preserved
        if not expr.n or expr.n <= 0:
            return None
        return start + (timedelta(minutes=expr.n) if ref == "in_minutes" else timedelta(hours=expr.n))

    try:
        clock = _clock(expr)
    except ValueError:
        return None
    today = start.date()
    tz = start.tzinfo
    at = lambda d: datetime.combine(d, clock, tz)  # noqa: E731

    if ref == "unspecified":
        if not _has_clock(expr):
            return None
        same_day = at(today)
        return same_day if same_day > start else at(today + timedelta(days=1))
    if ref == "today":
        return at(today)
    if ref == "tomorrow":
        return at(today + timedelta(days=1))
    if ref == "day_after_tomorrow":
        return at(today + timedelta(days=2))
    if ref == "in_days":
        return at(today + timedelta(days=expr.n)) if expr.n and expr.n > 0 else None
    if ref in {"weekday", "this_weekday", "next_weekday"}:
        if expr.weekday is None:
            return None
        target = WEEKDAYS.index(expr.weekday)
        delta = (target - today.weekday()) % 7
        if ref == "weekday":
            return at(today + timedelta(days=delta or 7))
        if ref == "this_weekday":
            dt = at(today + timedelta(days=delta))
            return dt if dt > start else at(today + timedelta(days=delta + 7))
        next_monday = today + timedelta(days=7 - today.weekday())
        return at(next_monday + timedelta(days=target))
    if ref == "next_week":
        return at(today + timedelta(days=7 - today.weekday()))
    if ref == "date":
        return _explicit_date(expr, start, clock) if expr.day else None
    if ref == "in_months":
        return at(_add_months(today, expr.n)) if expr.n and expr.n > 0 else None
    if ref == "next_month":
        return at(_add_months(today.replace(day=1), 1))
    return None


# --------------------------------------------------------------------------- top level (F2-F9)

def resolve_next_call(
    cb: CallbackExtraction,
    disposition: str,
    call_started_at: str,
    tz: str = "Asia/Kolkata",
) -> Resolution:
    if disposition in CALLBACK_SUPPRESSED:
        return Resolution(None, "F2 suppressed by disposition")

    start = parse_call_start(call_started_at, tz)
    resolved = [resolve_expr(o, start) for o in cb.options] if cb.specific_callback_agreed else []
    future = [r for r in resolved if isinstance(r, datetime) and r > start]

    if future and cb.acknowledged_by_other:
        return Resolution(format_ts(min(future)), "F3 specific acknowledged callback (earliest option)")
    if disposition == APPOINTMENT:
        return Resolution(None, "F8 appointment without distinct callback")

    only_vague = bool(resolved) and all(r is VAGUE for r in resolved)
    if cb.vague_postponement or only_vague:
        return Resolution(format_ts(datetime.combine(start.date() + timedelta(days=3), DEFAULT_TIME, start.tzinfo)),
                          "F7 vague postponement +3d")
    return Resolution(format_ts(datetime.combine(start.date() + timedelta(days=1), DEFAULT_TIME, start.tzinfo)),
                      "F8 follow-up fallback +1d")
