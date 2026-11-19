"""Task 2 is scaffolded only. These tests pin the public names so the package stays importable."""

from __future__ import annotations

import pytest

from customer_gender.cue_lexicons import FEMALE_CUES, MALE_CUES
from customer_gender.gender_scoring import predict_gender
from customer_gender.speaker_parsing import speaker_turns


def test_cue_lists_start_empty():
    assert MALE_CUES == () and FEMALE_CUES == ()


def test_gender_entry_points_are_not_built_yet():
    with pytest.raises(NotImplementedError):
        speaker_turns("Agent: Hello")
    with pytest.raises(NotImplementedError):
        predict_gender("Agent: Hello")
