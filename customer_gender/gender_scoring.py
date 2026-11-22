"""Weighted vote of labeling functions. No transformer and no learned weights.

Each cue family votes male, female, or abstains. Family A contributes the
log count-ratio, so 26-0 is strong and 1-1 is about zero. B, C, D and E add
a fixed weight once per side. A mixed honorific call that stays under the
margin can still be decided from the later half of the call.

The constants below were chosen from the cue strengths before any transcript
was scored. Do not refit them to the error list.

A call is unknown when the two sides are close or the total evidence is thin.
A mixed honorific call can still be decided from the later half, and only then.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

from .cue_lexicons import (
    FEMALE_HINDI,
    FEMALE_NAMES,
    MALE_HINDI,
    MALE_NAMES,
)
from .speaker_parsing import speaker_turns

# Fixed before scoring. A is a log ratio, not one of these weights.
WEIGHT_B = 1.5
WEIGHT_C = 2.0
WEIGHT_D = 0.5
WEIGHT_E = 0.5
MIN_MARGIN = 0.6
MIN_TOTAL = 0.75

_FAMILY_WEIGHT = {"B": WEIGHT_B, "C": WEIGHT_C, "D": WEIGHT_D, "E": WEIGHT_E}

_ADDRESS = re.compile(
    r"\b(ma'am|madam|sir|mr|mrs|ms|miss|mister)\b\.?",
    re.IGNORECASE,
)
_THIRD_BEFORE = re.compile(r"\b(the|that|this)\s*$", re.IGNORECASE)
_THIRD_AFTER = re.compile(r"\s+(has|had|is|was|will|can|would|sits)\b", re.IGNORECASE)
_HINDI = re.compile(
    r"\b(bhaiya|bhai|beta|didi|behen)\b",
    re.IGNORECASE,
)
_HINDI_POSSESSIVE = re.compile(r"\b(my|your|his|her|the|that|this)\s+$", re.IGNORECASE)
_MY_HUSBAND = re.compile(r"\bmy husband(?:'s)?\b", re.IGNORECASE)
_MY_WIFE = re.compile(r"\bmy wife(?:'s)?\b", re.IGNORECASE)
_YOUR_HUSBAND = re.compile(r"\byour husband(?:'s)?\b", re.IGNORECASE)
_YOUR_WIFE = re.compile(r"\byour wife(?:'s)?\b", re.IGNORECASE)
_SELF_MALE = re.compile(
    r"\bi am\b.{0,40}\bhusband\b|\b(?:her|his)\s+son\b|\bi am\s+(?:a|the)\s+son\b",
    re.IGNORECASE,
)
_SELF_FEMALE = re.compile(
    r"\bi am\b.{0,40}\bwife\b|\b(?:her|his)\s+daughter\b|\bi am\s+(?:a|the)\s+daughter\b",
    re.IGNORECASE,
)
_MY_NAME = re.compile(r"\bmy name is\s+([A-Za-z]+)", re.IGNORECASE)

_MALE_ADDRESS = {"sir", "mr", "mister"}
_FEMALE_ADDRESS = {"ma'am", "madam", "mrs", "ms", "miss"}


@dataclass(frozen=True)
class Cue:
    family: str
    side: str
    speaker: str
    quote: str
    position: float

    def as_dict(self) -> dict:
        row = asdict(self)
        row["position"] = round(self.position, 3)
        return row


def _plain(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


def _position(index: int, total: int) -> float:
    if total <= 1:
        return 1.0
    return index / (total - 1)


def _snip(text: str, start: int, end: int) -> str:
    left = max(0, start - 40)
    right = min(len(text), end + 40)
    return " ".join(text[left:right].split())


def _third_person(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 16):start]
    after = text[end:end + 20]
    if _THIRD_BEFORE.search(before):
        return True
    if _THIRD_AFTER.match(after):
        return True
    return False


def _address_side(token: str) -> str:
    token = token.lower().rstrip(".")
    if token in _MALE_ADDRESS:
        return "male"
    if token in _FEMALE_ADDRESS:
        return "female"
    raise ValueError(token)


def extract_cues(transcript: str, *, third_person_filter: bool = True) -> list[Cue]:
    """Cues that vote. Third-person honorifics are omitted when the filter is on."""
    turns = speaker_turns(transcript)
    total = len(turns)
    cues: list[Cue] = []
    for index, (speaker, raw) in enumerate(turns):
        text = _plain(raw)
        position = _position(index, total)
        if speaker == "agent":
            cues.extend(_agent_cues(text, position, third_person_filter))
        elif speaker == "customer":
            cues.extend(_customer_cues(text, position))
    return cues


def _agent_cues(text: str, position: float, third_person_filter: bool) -> list[Cue]:
    found: list[Cue] = []
    for match in _ADDRESS.finditer(text):
        if third_person_filter and _third_person(text, match.start(), match.end()):
            continue
        found.append(Cue("A", _address_side(match.group(1)), "agent", _snip(text, match.start(), match.end()), position))
    for pattern, side in ((_YOUR_HUSBAND, "female"), (_YOUR_WIFE, "male")):
        match = pattern.search(text)
        if match:
            found.append(Cue("B", side, "agent", _snip(text, match.start(), match.end()), position))
    for match in _HINDI.finditer(text):
        if _HINDI_POSSESSIVE.search(text[max(0, match.start() - 12):match.start()]):
            continue
        token = match.group(1).lower()
        side = "male" if token in MALE_HINDI else "female" if token in FEMALE_HINDI else ""
        if side:
            found.append(Cue("E", side, "agent", _snip(text, match.start(), match.end()), position))
    return found


def _customer_cues(text: str, position: float) -> list[Cue]:
    found: list[Cue] = []
    for pattern, side in ((_MY_HUSBAND, "female"), (_MY_WIFE, "male")):
        match = pattern.search(text)
        if match:
            found.append(Cue("B", side, "customer", _snip(text, match.start(), match.end()), position))
    for pattern, side in ((_SELF_MALE, "male"), (_SELF_FEMALE, "female")):
        match = pattern.search(text)
        if match:
            found.append(Cue("C", side, "customer", _snip(text, match.start(), match.end()), position))
    name = _MY_NAME.search(text)
    if name:
        token = name.group(1).lower()
        if token in MALE_NAMES and token not in FEMALE_NAMES:
            found.append(Cue("D", "male", "customer", _snip(text, name.start(), name.end()), position))
        elif token in FEMALE_NAMES and token not in MALE_NAMES:
            found.append(Cue("D", "female", "customer", _snip(text, name.start(), name.end()), position))
    return found


def _add_family_a(cues: list[Cue]) -> tuple[float, float]:
    """Log ratio of honorific counts. Repeats matter; 1-1 cancels."""
    female = sum(1 for c in cues if c.family == "A" and c.side == "female")
    male = sum(1 for c in cues if c.family == "A" and c.side == "male")
    if female == 0 and male == 0:
        return 0.0, 0.0
    ratio = math.log((female + 0.5) / (male + 0.5))
    if ratio > 0:
        return ratio, 0.0
    return 0.0, -ratio


def _add_once(cues: list[Cue], family: str) -> tuple[float, float]:
    """One vote per side. Saying "my husband" four times is still one fact."""
    weight = _FAMILY_WEIGHT[family]
    sides = {c.side for c in cues if c.family == family}
    return weight * ("female" in sides), weight * ("male" in sides)


def _later_half_side(cues: list[Cue]) -> str | None:
    """Used only when the full-call margin is too small and both honorifics occur."""
    late = [c for c in cues if c.family == "A" and c.position >= 0.5]
    female = sum(1 for c in late if c.side == "female")
    male = sum(1 for c in late if c.side == "male")
    if female == 0 or male == 0 or female == male:
        if female == male:
            return None
        ratio = math.log(((female or 0) + 0.5) / ((male or 0) + 0.5))
        if abs(ratio) < MIN_MARGIN:
            return None
        return "female" if female > male else "male"
    ratio = math.log((female + 0.5) / (male + 0.5))
    if abs(ratio) < MIN_MARGIN:
        return None
    return "female" if ratio > 0 else "male"


def score_cues(cues: list[Cue]) -> dict:
    female, male = _add_family_a(cues)
    for family in ("B", "C", "D", "E"):
        add_f, add_m = _add_once(cues, family)
        female += add_f
        male += add_m
    margin = abs(female - male)
    total = female + male
    both_honorifics = any(c.family == "A" and c.side == "female" for c in cues) and any(
        c.family == "A" and c.side == "male" for c in cues
    )
    tie_break = None
    if total < MIN_TOTAL or margin < MIN_MARGIN:
        label = "unknown"
        if both_honorifics:
            tie_break = _later_half_side(cues)
            if tie_break:
                label = tie_break
    else:
        label = "female" if female > male else "male"
    confidence = 0.0 if total == 0 else margin / (margin + 1)
    return {
        "customer_gender": label,
        "confidence": round(confidence, 3),
        "female_evidence": round(female, 3),
        "male_evidence": round(male, 3),
        "tie_break": tie_break,
    }


def predict_gender(
    transcript: str,
    *,
    third_person_filter: bool = True,
    families: str = "ABCDE",
) -> dict:
    """Return customer_gender, confidence, and the cues that voted."""
    allowed = set(families)
    cues = [c for c in extract_cues(transcript, third_person_filter=third_person_filter) if c.family in allowed]
    scored = score_cues(cues)
    return {
        "customer_gender": scored["customer_gender"],
        "confidence": scored["confidence"],
        "cues": [c.as_dict() for c in cues],
    }
