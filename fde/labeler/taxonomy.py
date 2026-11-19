"""Label vocabulary and allowed disposition/sub_disposition pairs (policy assignment-v2)."""

from __future__ import annotations

APPOINTMENT = "Appointment Scheduled"
FOLLOW_UP = "Follow-up Required"
NOT_INTERESTED = "Not Interested"
INVALID = "Invalid Lead"
UNABLE = "Unable to Assess"

# Rule D6 precedence, highest first.
DISPOSITIONS = (INVALID, NOT_INTERESTED, APPOINTMENT, FOLLOW_UP, UNABLE)

# Children listed in each parent's tie-break order (SUB "All: Tie-breaking").
ALLOWED_PAIRS: dict[str, tuple[str, ...]] = {
    APPOINTMENT: ("Rescheduled", "Online Consultation", "Clinic Visit"),
    FOLLOW_UP: (
        "Family Discussion",
        "Cost Concern",
        "Travel Constraint",
        "Current Treatment",
        "Treatment Concern",
        "Specific Callback",
        "Information Requested",
        "Vague Deferral",
        "Further Discussion",
    ),
    NOT_INTERESTED: ("Do Not Contact", "Explicit Refusal"),
    INVALID: ("Test Enquiry", "Wrong Contact", "No Pain Need", "Policy Exclusion", "Outside Service Area"),
    UNABLE: ("Incomplete Conversation",),
}

LEAD_QUALITIES = ("Not Qualified", "Not Assessable", "Low", "High", "Medium")

# Rule F2: these dispositions never carry a callback.
CALLBACK_SUPPRESSED = frozenset({INVALID, NOT_INTERESTED, UNABLE})


def is_valid_pair(disposition: str, sub_disposition: str) -> bool:
    return sub_disposition in ALLOWED_PAIRS.get(disposition, ())
