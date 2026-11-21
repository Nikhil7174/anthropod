"""Intermediate extraction schema (filled by the LLM) and the output contract.

The LLM only reports evidence-backed facts; every label is derived in Python.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class _Extraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @field_validator("*", mode="before")
    @classmethod
    def _normalise(cls, v, info: ValidationInfo):
        # Models occasionally emit "null"/"" for absent values or null for a boolean.
        if isinstance(v, str):
            s = v.strip()
            v = None if s.lower() in {"", "null", "none", "n/a"} else s
        if v is None and cls.model_fields[info.field_name].annotation is bool:
            return False
        return v


# --------------------------------------------------------------------------- callback (Call B)

DayRef = Literal[
    "unspecified",         # only a clock time / daypart was agreed ("call at 4", "this evening" -> use today)
    "today",
    "tomorrow",
    "day_after_tomorrow",  # also "parso"
    "in_days",             # "in N days"            -> n
    "weekday",             # bare weekday           -> weekday
    "this_weekday",        # "this Friday"          -> weekday
    "next_weekday",        # "next Friday"          -> weekday
    "next_week",           # "next week" with no finer condition
    "this_week",           # "this week" alone (vague)
    "date",                # explicit day number    -> day [, month, year]
    "in_minutes",          # "in N minutes"         -> n
    "in_hours",            # "in N hours"           -> n
    "in_months",           # "in/after N months"    -> n
    "next_month",          # bare "next month"
    "after_event",         # unbounded "after Diwali", "after the family event" (vague)
]
Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
Daypart = Literal["morning", "lunch", "afternoon", "evening", "night"]


class TimeExpr(_Extraction):
    """One agreed callback time, as spoken. Python resolves it to a timestamp."""

    day_ref: Optional[DayRef] = "unspecified"
    n: Optional[int] = Field(None, description="count for in_days / in_minutes / in_hours / in_months")
    weekday: Optional[Weekday] = None
    day: Optional[int] = Field(None, ge=1, le=31)
    month: Optional[int] = Field(None, ge=1, le=12)
    year: Optional[int] = None
    hour: Optional[int] = Field(None, ge=0, le=23, description="clock hour as spoken")
    minute: Optional[int] = Field(None, ge=0, le=59)
    meridiem: Optional[Literal["am", "pm"]] = None
    daypart: Optional[Daypart] = None

    @field_validator("day_ref", "weekday", "meridiem", "daypart", mode="before")
    @classmethod
    def _lower(cls, v):
        if isinstance(v, str):
            v = v.strip().lower().replace(".", "")
            return None if v in {"", "null", "none"} else v
        return v

    @field_validator("day_ref", mode="after")
    @classmethod
    def _default_day_ref(cls, v):
        return v or "unspecified"


class CallbackExtraction(_Extraction):
    specific_callback_agreed: bool = False
    proposed_by: Optional[Literal["agent", "customer"]] = None
    acknowledged_by_other: bool = False
    options: list[TimeExpr] = Field(default_factory=list)
    vague_postponement: bool = False
    evidence: Optional[str] = None


# --------------------------------------------------------------------------- call facts (Call A)

Blocker = Literal["family", "cost", "travel", "current_treatment", "treatment_concern", "info_review"]


class Validity(_Extraction):
    test_enquiry: bool = False
    wrong_contact: bool = False
    no_pain_need: bool = False
    patient_under_15: bool = False
    outside_service_area: bool = False
    evidence: Optional[str] = None


class Refusal(_Extraction):
    final_refusal: bool = False
    do_not_contact: bool = False
    evidence: Optional[str] = None


class Booking(_Extraction):
    slot_confirmed_by_both: bool = False
    slot: Optional[TimeExpr] = None
    modality: Optional[Literal["clinic", "online"]] = None
    replaces_existing_or_missed: bool = False
    evidence: Optional[str] = None


class Blockers(_Extraction):
    final_unresolved: list[Blocker] = Field(default_factory=list)
    primary: Optional[Blocker] = None
    evidence: Optional[str] = None

    @field_validator("final_unresolved", mode="before")
    @classmethod
    def _drop_unknown(cls, v):
        allowed = set(Blocker.__args__)
        return [b for b in (v or []) if isinstance(b, str) and b in allowed]

    @field_validator("primary", mode="before")
    @classmethod
    def _primary_known(cls, v):
        return v if v in Blocker.__args__ else None


class Readiness(_Extraction):
    pain_need_established: bool = False
    need_or_willingness_unclear: bool = False
    exploratory_only: bool = False
    defers_over_30_days: bool = False
    explicit_visit_commitment: bool = False
    visit_when: Optional[TimeExpr] = None
    evidence: Optional[str] = None


class Discussion(_Extraction):
    meaningful_relevant_discussion: bool = False
    call_cut_off: bool = False


class CallFacts(_Extraction):
    validity: Validity = Field(default_factory=Validity)
    refusal: Refusal = Field(default_factory=Refusal)
    booking: Booking = Field(default_factory=Booking)
    blockers: Blockers = Field(default_factory=Blockers)
    readiness: Readiness = Field(default_factory=Readiness)
    discussion: Discussion = Field(default_factory=Discussion)


class BothExtraction(_Extraction):
    """Call outcome and callback in one response. Used only by --calls 1."""

    facts: CallFacts
    callback: CallbackExtraction


# --------------------------------------------------------------------------- output contract

class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript_id: str
    disposition: str
    sub_disposition: str
    lead_quality: str
    next_call_at: Optional[str]
