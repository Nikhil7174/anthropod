"""Output contract checks and the documented safe fallback record."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .label_vocabulary import ALLOWED_PAIRS, CALLBACK_SUPPRESSED, FOLLOW_UP, LEAD_QUALITIES, is_valid_pair
from .next_call_resolver import DEFAULT_TIME, format_ts, parse_call_start

OUTPUT_KEYS = ("transcript_id", "disposition", "sub_disposition", "lead_quality", "next_call_at")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$")


def contract_errors(pred: dict) -> list[str]:
    errors = []
    if tuple(pred) != OUTPUT_KEYS:
        errors.append(f"keys must be exactly {OUTPUT_KEYS}, got {tuple(pred)}")
        return errors
    if not isinstance(pred["transcript_id"], str) or not pred["transcript_id"]:
        errors.append("transcript_id must be a non-empty string")
    if pred["disposition"] not in ALLOWED_PAIRS:
        errors.append(f"unknown disposition {pred['disposition']!r}")
    elif not is_valid_pair(pred["disposition"], pred["sub_disposition"]):
        errors.append(f"invalid pair {pred['disposition']!r}/{pred['sub_disposition']!r}")
    if pred["lead_quality"] not in LEAD_QUALITIES:
        errors.append(f"unknown lead_quality {pred['lead_quality']!r}")
    nca = pred["next_call_at"]
    if nca is not None and not (isinstance(nca, str) and _TS.match(nca)):
        errors.append(f"next_call_at must be null or YYYY-MM-DDTHH:MM:SS+05:30, got {nca!r}")
    if nca is not None and pred["disposition"] in CALLBACK_SUPPRESSED:
        errors.append(f"next_call_at must be null for {pred['disposition']}")
    return errors


def fallback_prediction(transcript_id: str, call_started_at: str, tz: str = "Asia/Kolkata") -> dict:
    """Used only when extraction fails after retries: keep the lead open for a next-day call (F8)."""
    try:
        start = parse_call_start(call_started_at, tz)
        nca = format_ts(datetime.combine(start.date() + timedelta(days=1), DEFAULT_TIME, start.tzinfo))
    except (TypeError, ValueError):
        nca = None
    return {
        "transcript_id": transcript_id,
        "disposition": FOLLOW_UP,
        "sub_disposition": "Further Discussion",
        "lead_quality": "Medium",
        "next_call_at": nca,
    }
