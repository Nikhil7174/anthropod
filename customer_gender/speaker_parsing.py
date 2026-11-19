"""Split a transcript into Agent and Customer turns.

Speaker labels in the export can be wrong, so role has to be checked against
what the turn says, not only against the label. Task 1 normalises text in
call_labeling.transcript_text; this module will own the gender task's view of
who is speaking. Not implemented yet.
"""

from __future__ import annotations


def speaker_turns(transcript: str) -> list[tuple[str, str]]:
    """Return (speaker, text) pairs. Raises until task 2 is built."""
    raise NotImplementedError("speaker_turns is part of task 2, which is not built yet")
