"""Transcript normalisation and speaker-turn parsing shared by all tasks.

Normalisation only touches whitespace; wording, speaker labels and turn
order are preserved exactly as exported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SPEAKER = re.compile(r"^\s*(agent|customer)\s*:\s?(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class Turn:
    speaker: str  # "agent" | "customer" | "unknown" (as labelled; labels may be wrong)
    text: str


def normalize(text: str) -> str:
    lines = (line.rstrip() for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return "\n".join(line for line in lines if line.strip())


def parse_turns(text: str) -> list[Turn]:
    turns: list[Turn] = []
    for line in normalize(text).split("\n"):
        if not line:
            continue
        m = _SPEAKER.match(line)
        if m:
            turns.append(Turn(m.group(1).lower(), m.group(2).strip()))
        elif turns:  # continuation of the previous turn
            turns[-1] = Turn(turns[-1].speaker, f"{turns[-1].text} {line.strip()}")
        else:
            turns.append(Turn("unknown", line.strip()))
    return turns


def customer_word_count(turns: list[Turn]) -> int:
    return sum(len(t.text.split()) for t in turns if t.speaker != "agent")
