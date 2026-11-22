"""Split a transcript into Agent and Customer turns.

Speaker labels in the export can be wrong. Callers still have to be separated
from the agent before any cue is counted, because "ma'am" from the customer
is about the agent.
"""

from __future__ import annotations

import re

_SPEAKER = re.compile(r"^\s*(agent|customer)\s*:\s?(.*)$", re.IGNORECASE)


def speaker_turns(transcript: str) -> list[tuple[str, str]]:
    """Return (speaker, text) pairs. speaker is "agent", "customer", or "unknown"."""
    turns: list[tuple[str, str]] = []
    for line in (transcript or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        match = _SPEAKER.match(line)
        if match:
            turns.append((match.group(1).lower(), match.group(2).strip()))
        elif turns:
            speaker, text = turns[-1]
            turns[-1] = (speaker, f"{text} {line}")
        else:
            turns.append(("unknown", line))
    return turns
