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
