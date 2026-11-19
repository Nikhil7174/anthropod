"""Branch coverage for the deterministic combiner and output contract."""

from __future__ import annotations

import pytest

from call_labeling.evidence_schema import CallbackExtraction, CallFacts
from call_labeling.label_rules import combine
from call_labeling.label_vocabulary import ALLOWED_PAIRS
from call_labeling.output_validator import contract_errors, fallback_prediction

START = "2026-11-09T14:00:00+05:30"  # Monday
OPEN = {"discussion": {"meaningful_relevant_discussion": True}, "readiness": {"pain_need_established": True}}


def facts(**overrides) -> CallFacts:
    data = {k: dict(v) for k, v in OPEN.items()}
    for key, value in overrides.items():
        data.setdefault(key, {}).update(value)
    return CallFacts.model_validate(data)


def booked(day_ref="tomorrow", **booking) -> dict:
    return {"booking": {"slot_confirmed_by_both": True, "slot": {"day_ref": day_ref, "hour": 3}, **booking}}


NO_CB = CallbackExtraction()
VAGUE = CallbackExtraction(vague_postponement=True)
TOMORROW_CB = CallbackExtraction(
    specific_callback_agreed=True, acknowledged_by_other=True, options=[{"day_ref": "tomorrow"}]
)

CASES = [
    # name, facts, callback, (disposition, sub, lead_quality, next_call_at)
    # --- Invalid Lead (all five) and tie-break
    ("test enquiry", facts(validity={"test_enquiry": True}), NO_CB, ("Invalid Lead", "Test Enquiry", "Not Qualified", None)),
    ("wrong contact", facts(validity={"wrong_contact": True}), NO_CB, ("Invalid Lead", "Wrong Contact", "Not Qualified", None)),
    ("no pain need", facts(validity={"no_pain_need": True}), NO_CB, ("Invalid Lead", "No Pain Need", "Not Qualified", None)),
    ("under 15", facts(validity={"patient_under_15": True}), NO_CB, ("Invalid Lead", "Policy Exclusion", "Not Qualified", None)),
    ("outside area", facts(validity={"outside_service_area": True}), NO_CB, ("Invalid Lead", "Outside Service Area", "Not Qualified", None)),
    ("invalid tie-break", facts(validity={"no_pain_need": True, "wrong_contact": True}), NO_CB, ("Invalid Lead", "Wrong Contact", "Not Qualified", None)),
    ("invalid beats refusal", facts(validity={"wrong_contact": True}, refusal={"final_refusal": True}), NO_CB, ("Invalid Lead", "Wrong Contact", "Not Qualified", None)),
    # --- Not Interested
    ("explicit refusal", facts(refusal={"final_refusal": True}), TOMORROW_CB, ("Not Interested", "Explicit Refusal", "Low", None)),
    ("do not contact beats refusal", facts(refusal={"final_refusal": True, "do_not_contact": True}), TOMORROW_CB, ("Not Interested", "Do Not Contact", "Low", None)),
    ("late refusal beats booking", facts(refusal={"final_refusal": True}, **booked()), NO_CB, ("Not Interested", "Explicit Refusal", "Low", None)),
    # --- Appointment Scheduled
    ("clinic visit", facts(**booked()), NO_CB, ("Appointment Scheduled", "Clinic Visit", "High", None)),
    ("online", facts(**booked(modality="online")), NO_CB, ("Appointment Scheduled", "Online Consultation", "High", None)),
    ("rescheduled beats online", facts(**booked(modality="online", replaces_existing_or_missed=True)), NO_CB, ("Appointment Scheduled", "Rescheduled", "High", None)),
    ("booking + distinct callback", facts(**booked()), TOMORROW_CB, ("Appointment Scheduled", "Clinic Visit", "High", "2026-11-10T11:00:00+05:30")),
    ("booking offset 6 is High", facts(booking={"slot_confirmed_by_both": True, "slot": {"day_ref": "in_days", "n": 6}}), NO_CB, ("Appointment Scheduled", "Clinic Visit", "High", None)),
    ("booking offset 7 is Medium", facts(booking={"slot_confirmed_by_both": True, "slot": {"day_ref": "in_days", "n": 7}}), NO_CB, ("Appointment Scheduled", "Clinic Visit", "Medium", None)),
    # --- Follow-up Required sub-dispositions
    ("primary blocker wins", facts(blockers={"final_unresolved": ["family", "travel"], "primary": "travel"}), VAGUE, ("Follow-up Required", "Travel Constraint", "Medium", "2026-11-12T11:00:00+05:30")),
    ("family first in tie-break", facts(blockers={"final_unresolved": ["cost", "family"]}), VAGUE, ("Follow-up Required", "Family Discussion", "Medium", "2026-11-12T11:00:00+05:30")),
    ("blocker tie-break", facts(blockers={"final_unresolved": ["treatment_concern", "cost"]}), VAGUE, ("Follow-up Required", "Cost Concern", "Medium", "2026-11-12T11:00:00+05:30")),
    ("blocker beats specific callback", facts(blockers={"final_unresolved": ["current_treatment"]}), TOMORROW_CB, ("Follow-up Required", "Current Treatment", "Medium", "2026-11-10T11:00:00+05:30")),
    ("specific callback", facts(), TOMORROW_CB, ("Follow-up Required", "Specific Callback", "Medium", "2026-11-10T11:00:00+05:30")),
    ("info review", facts(blockers={"final_unresolved": ["info_review"]}), VAGUE, ("Follow-up Required", "Information Requested", "Medium", "2026-11-12T11:00:00+05:30")),
    ("vague deferral", facts(), VAGUE, ("Follow-up Required", "Vague Deferral", "Medium", "2026-11-12T11:00:00+05:30")),
    ("further discussion", facts(), NO_CB, ("Follow-up Required", "Further Discussion", "Medium", "2026-11-10T11:00:00+05:30")),
    # --- Unable to Assess
    ("unable", CallFacts(), VAGUE, ("Unable to Assess", "Incomplete Conversation", "Not Assessable", None)),
    ("cut-off call with known need is follow-up", facts(discussion={"meaningful_relevant_discussion": False, "call_cut_off": True}), NO_CB, ("Follow-up Required", "Further Discussion", "Medium", "2026-11-10T11:00:00+05:30")),
    # --- Lead quality
    ("need unclear -> Not Assessable", facts(readiness={"need_or_willingness_unclear": True}, blockers={"primary": "treatment_concern"}), NO_CB, ("Follow-up Required", "Treatment Concern", "Not Assessable", "2026-11-10T11:00:00+05:30")),
    ("exploratory -> Low", facts(readiness={"exploratory_only": True}), VAGUE, ("Follow-up Required", "Vague Deferral", "Low", "2026-11-12T11:00:00+05:30")),
    ("defers > 30 days -> Low", facts(readiness={"defers_over_30_days": True}, blockers={"primary": "current_treatment"}), VAGUE, ("Follow-up Required", "Current Treatment", "Low", "2026-11-12T11:00:00+05:30")),
    ("unblocked visit commitment -> High", facts(readiness={"explicit_visit_commitment": True, "visit_when": {"day_ref": "tomorrow"}}), TOMORROW_CB, ("Follow-up Required", "Specific Callback", "High", "2026-11-10T11:00:00+05:30")),
    ("blocked visit commitment -> Medium", facts(readiness={"explicit_visit_commitment": True, "visit_when": {"day_ref": "tomorrow"}}, blockers={"primary": "cost"}), NO_CB, ("Follow-up Required", "Cost Concern", "Medium", "2026-11-10T11:00:00+05:30")),
]


@pytest.mark.parametrize("name,f,cb,expected", CASES, ids=[c[0] for c in CASES])
def test_combine(name, f, cb, expected):
    labels = combine(f, cb, START)
    assert (labels.disposition, labels.sub_disposition, labels.lead_quality, labels.next_call_at) == expected, labels.trace


def test_every_allowed_pair_is_reachable():
    reached = set()
    for _, f, cb, _ in CASES:
        labels = combine(f, cb, START)
        reached.add((labels.disposition, labels.sub_disposition))
    expected = {(d, s) for d, subs in ALLOWED_PAIRS.items() for s in subs}
    assert expected <= reached, expected - reached


def test_llm_noise_is_tolerated():
    f = CallFacts.model_validate(
        {"blockers": {"final_unresolved": ["cost", "weather"], "primary": "none"},
         "readiness": {"pain_need_established": None, "exploratory_only": "null"},
         "discussion": {"meaningful_relevant_discussion": True}}
    )
    assert f.blockers.final_unresolved == ["cost"] and f.blockers.primary is None
    assert f.readiness.pain_need_established is False


def test_contract_and_fallback():
    fb = fallback_prediction("X-1", START)
    assert contract_errors(fb) == []
    assert fb["next_call_at"] == "2026-11-10T11:00:00+05:30"
    assert contract_errors({**fb, "sub_disposition": "Clinic Visit"})
    assert contract_errors({**fb, "next_call_at": "2026-11-10T11:00+05:30"})
    assert contract_errors({**fb, "extra": 1})
    assert contract_errors({**fb, "disposition": "Not Interested", "sub_disposition": "Explicit Refusal"})
