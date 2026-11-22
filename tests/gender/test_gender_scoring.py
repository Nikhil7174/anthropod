"""Cue extraction and the frozen weighted vote. Fixtures are made-up lines."""

from __future__ import annotations

from customer_gender.gender_scoring import predict_gender
from customer_gender.speaker_parsing import speaker_turns


def _genders(transcript: str, **kwargs) -> str:
    return predict_gender(transcript, **kwargs)["customer_gender"]


def test_speaker_turns_keep_agent_and_customer_apart():
    turns = speaker_turns("Agent: Yes, ma'am.\nCustomer: Thank you, ma'am.\nstill me")
    assert turns == [
        ("agent", "Yes, ma'am."),
        ("customer", "Thank you, ma'am. still me"),
    ]


def test_vocative_maam_counts_and_third_person_does_not():
    kept = predict_gender(
        "Agent: Yes, ma'am.\n"
        "Agent: What is the problem, ma'am?\n"
        "Agent: Dr. Leena Rao, overall ma'am has more than 30 years of experience.\n"
        "Agent: Yes, exactly the madam will tell you.\n"
    )
    assert kept["customer_gender"] == "female"
    quotes = " ".join(c["quote"] for c in kept["cues"])
    assert "Yes, ma'am" in quotes
    assert "ma'am has" not in quotes
    assert "the madam will" not in quotes


def test_customer_maam_is_the_agent_not_the_customer():
    prediction = predict_gender(
        "Agent: Hello, how can I help?\n"
        "Customer: Yes ma'am.\n"
        "Customer: Okay ma'am, thank you ma'am.\n"
    )
    assert prediction["customer_gender"] == "unknown"
    assert prediction["cues"] == []
    assert prediction["confidence"] == 0.0


def test_spouse_words_vote_and_a_customer_mr_does_not():
    assert _genders("Agent: Hello.\nCustomer: My husband is away, so I can't come alone.") == "female"
    assert _genders("Agent: Hello.\nCustomer: I will consult my wife and let you know.") == "male"
    assert _genders("Agent: Hello.\nCustomer: My father's name is Mr. Hamid Qureshi.") == "unknown"


def test_agent_mr_addresses_the_customer():
    assert _genders("Agent: Hi, am I speaking to Mr. Kartik?\nCustomer: Yes, speaking.") == "male"


def test_self_identification_is_family_c():
    prediction = predict_gender("Agent: Hello.\nCustomer: I am her son. She cannot come to the phone.")
    assert prediction["customer_gender"] == "male"
    assert any(c["family"] == "C" and c["side"] == "male" for c in prediction["cues"])


def test_stated_name_is_a_weak_cue_and_does_not_commit_alone():
    assert _genders("Customer: My name is Mala.\nAgent: What is the problem?") == "unknown"


def test_no_cue_is_unknown():
    prediction = predict_gender("Agent: Hello.\nCustomer: I want to know the fee.\nAgent: It is 750.")
    assert prediction["customer_gender"] == "unknown"
    assert prediction["cues"] == []


def test_later_half_breaks_a_mixed_honorific_tie():
    early = "\n".join(f"Agent: Yes, sir. line {i}" for i in range(3))
    late = "\n".join(f"Agent: Okay, ma'am. line {i}" for i in range(3))
    prediction = predict_gender(early + "\nCustomer: One moment.\n" + late)
    assert prediction["customer_gender"] == "female"
    assert {c["side"] for c in prediction["cues"] if c["family"] == "A"} == {"male", "female"}


def test_turning_the_third_person_filter_off_lets_the_doctor_vote():
    transcript = "Agent: The doctor, ma'am has more than 30 years of experience."
    assert _genders(transcript) == "unknown"
    assert _genders(transcript, third_person_filter=False) == "female"
