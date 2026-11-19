"""Deterministic label derivation from extracted facts (rules D1-D6, SUB, LQ).

Every decision appends a short reason to `trace` so a prediction can be
explained from debug output without re-running the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .evidence_schema import CallbackExtraction, CallFacts, TimeExpr
from .label_vocabulary import APPOINTMENT, FOLLOW_UP, INVALID, NOT_INTERESTED, UNABLE
from .next_call_resolver import parse_call_start, resolve_expr, resolve_next_call

# Invalid Lead tie-break order (SUB "All: Tie-breaking").
_INVALID_REASONS = (
    ("test_enquiry", "Test Enquiry"),
    ("wrong_contact", "Wrong Contact"),
    ("no_pain_need", "No Pain Need"),
    ("patient_under_15", "Policy Exclusion"),
    ("outside_service_area", "Outside Service Area"),
)

# Named Follow-up blockers in tie-break order.
_NAMED_BLOCKERS = {
    "family": "Family Discussion",
    "cost": "Cost Concern",
    "travel": "Travel Constraint",
    "current_treatment": "Current Treatment",
    "treatment_concern": "Treatment Concern",
}
HIGH_MAX_DAY_OFFSET = 6  # call date is day 1, so offsets 0-6 are "within seven calendar dates"


@dataclass
class Labels:
    disposition: str
    sub_disposition: str
    lead_quality: str
    next_call_at: Optional[str]
    trace: list[str] = field(default_factory=list)


def _disposition(f: CallFacts, trace: list[str]) -> tuple[str, Optional[str]]:
    for attr, sub in _INVALID_REASONS:
        if getattr(f.validity, attr):
            trace.append(f"D1 invalid: {attr}")
            return INVALID, sub
    if f.refusal.do_not_contact:
        trace.append("D2 do-not-contact")
        return NOT_INTERESTED, "Do Not Contact"
    if f.refusal.final_refusal:
        trace.append("D2 final refusal")
        return NOT_INTERESTED, "Explicit Refusal"
    if f.booking.slot_confirmed_by_both:
        if f.booking.replaces_existing_or_missed:
            sub = "Rescheduled"
        elif f.booking.modality == "online":
            sub = "Online Consultation"
        else:
            sub = "Clinic Visit"
        trace.append(f"D3 confirmed slot -> {sub}")
        return APPOINTMENT, sub
    if f.discussion.meaningful_relevant_discussion or f.readiness.pain_need_established:
        trace.append("D4 open relevant discussion")
        return FOLLOW_UP, None
    trace.append("D5 no reliable relevant outcome")
    return UNABLE, "Incomplete Conversation"


def _named_blocker(f: CallFacts) -> Optional[str]:
    if f.blockers.primary in _NAMED_BLOCKERS:
        return _NAMED_BLOCKERS[f.blockers.primary]
    for key, label in _NAMED_BLOCKERS.items():
        if key in f.blockers.final_unresolved:
            return label
    return None


def _follow_up_sub(f: CallFacts, cb: CallbackExtraction, specific_callback: bool, trace: list[str]) -> str:
    named = _named_blocker(f)
    if named:
        trace.append(f"SUB named blocker -> {named}")
        return named
    if specific_callback:
        trace.append("SUB acknowledged specific callback")
        return "Specific Callback"
    if f.blockers.primary == "info_review" or "info_review" in f.blockers.final_unresolved:
        trace.append("SUB reviewing requested information")
        return "Information Requested"
    if cb.vague_postponement:
        trace.append("SUB vague postponement")
        return "Vague Deferral"
    trace.append("SUB open enquiry, no next step")
    return "Further Discussion"


def _day_offset(expr: Optional[TimeExpr], start: datetime) -> Optional[int]:
    if expr is None:
        return None
    resolved = resolve_expr(expr, start)
    return (resolved.date() - start.date()).days if isinstance(resolved, datetime) else None


def _lead_quality(f: CallFacts, disposition: str, start: datetime, trace: list[str]) -> str:
    r = f.readiness
    if disposition == INVALID:
        return "Not Qualified"
    if disposition == UNABLE:
        return "Not Assessable"
    if r.need_or_willingness_unclear:
        trace.append("LQ need/willingness unclear")
        return "Not Assessable"
    if disposition == NOT_INTERESTED:
        return "Low"
    if disposition != APPOINTMENT and (r.exploratory_only or r.defers_over_30_days):
        trace.append("LQ exploratory or >30 day deferral")
        return "Low"

    if disposition == APPOINTMENT:
        offset = _day_offset(f.booking.slot, start)
        if offset is not None and offset > HIGH_MAX_DAY_OFFSET:
            trace.append(f"LQ booked at offset {offset} -> Medium")
            return "Medium"
        trace.append(f"LQ booked at offset {offset}")
        return "High"

    if r.pain_need_established and r.explicit_visit_commitment and _named_blocker(f) is None:
        offset = _day_offset(r.visit_when, start)
        if offset is not None and 0 <= offset <= HIGH_MAX_DAY_OFFSET:
            trace.append(f"LQ unblocked visit commitment at offset {offset}")
            return "High"
    return "Medium"


def combine(facts: CallFacts, cb: CallbackExtraction, call_started_at: str, tz: str = "Asia/Kolkata") -> Labels:
    trace: list[str] = []
    start = parse_call_start(call_started_at, tz)

    disposition, sub = _disposition(facts, trace)
    resolution = resolve_next_call(cb, disposition, call_started_at, tz)
    trace.append(resolution.rule)

    if disposition == FOLLOW_UP:
        sub = _follow_up_sub(facts, cb, resolution.rule.startswith("F3"), trace)

    lead_quality = _lead_quality(facts, disposition, start, trace)
    return Labels(disposition, sub, lead_quality, resolution.next_call_at, trace)
