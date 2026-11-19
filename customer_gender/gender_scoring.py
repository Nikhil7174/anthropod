"""Combine parsed cues into a gender label, a confidence and an unknown bucket.

The cascade is weighted and deterministic. It does not call a transformer
or any other model. Not implemented yet.
"""

from __future__ import annotations


def predict_gender(transcript: str) -> dict:
    """Return transcript-level gender fields. Raises until task 2 is built."""
    raise NotImplementedError("predict_gender is part of task 2, which is not built yet")
