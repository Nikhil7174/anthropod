"""Evidence extraction. Neither call returns a final label.

--calls 2 (default) asks for the call outcome, then the callback.
--calls 1 asks for both in one JSON object. The transcript is sent once.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .evidence_schema import BothExtraction, CallbackExtraction, CallFacts
from .input_records import CallRecord
from .llm_client import JSONClient, Usage
from .next_call_resolver import parse_call_start
from .transcript_text import normalize

PROMPT_DIR = Path(__file__).parent / "prompts"
CALL_OUTCOME = "extract_call_outcome"
CALLBACK = "extract_callback"


@lru_cache(maxsize=None)
def system_prompt(name: str) -> str:
    time_expr = (PROMPT_DIR / "time_expression.md").read_text(encoding="utf-8")
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").replace("{time_expr}", time_expr).strip()


@lru_cache(maxsize=None)
def system_prompt_both() -> str:
    """The two prompts in one request. The time-encoding section appears once."""
    outcome = (PROMPT_DIR / f"{CALL_OUTCOME}.md").read_text(encoding="utf-8").replace("{time_expr}", "").strip()
    callback = (PROMPT_DIR / f"{CALLBACK}.md").read_text(encoding="utf-8").replace("{time_expr}", "").strip()
    time_expr = (PROMPT_DIR / "time_expression.md").read_text(encoding="utf-8").strip()
    header = (
        "Return ONE JSON object with exactly two keys, `facts` and `callback`.\n"
        "`facts` is the call outcome. `callback` is the next phone call only. "
        "A consultation slot belongs in `facts.booking`, never in `callback`.\n"
        "Do not assign final labels and do not compute dates."
    )
    return f"{header}\n\n{outcome}\n\n{callback}\n\n{time_expr}"


def user_message(record: CallRecord) -> str:
    start = parse_call_start(record.call_started_at, record.timezone)
    when = start.strftime("%A %d %B %Y, %H:%M")
    return (
        f"Call started at: {record.call_started_at} ({when}, {record.timezone})\n\n"
        f'Transcript:\n"""\n{normalize(record.transcript)}\n"""'
    )


@dataclass
class Extraction:
    facts: CallFacts
    callback: CallbackExtraction
    usage: Usage


def extract(client: JSONClient, record: CallRecord, calls: int = 2) -> Extraction:
    user = user_message(record)
    usage = Usage()
    if calls == 1:
        both, u = client.complete(system_prompt_both(), user, BothExtraction, "call_and_callback")
        usage += u
        return Extraction(both.facts, both.callback, usage)
    if calls != 2:
        raise ValueError(f"calls must be 1 or 2, got {calls}")
    facts, u1 = client.complete(system_prompt(CALL_OUTCOME), user, CallFacts, "call_facts")
    usage += u1
    callback, u2 = client.complete(system_prompt(CALLBACK), user, CallbackExtraction, "callback")
    usage += u2
    return Extraction(facts, callback, usage)
