"""The two evidence calls: call outcome, then callback. Neither returns a final label."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .evidence_schema import CallbackExtraction, CallFacts
from .input_records import CallRecord
from .llm_client import GroqJSONClient, Usage
from .next_call_resolver import parse_call_start
from .transcript_text import normalize

PROMPT_DIR = Path(__file__).parent / "prompts"
CALL_OUTCOME = "extract_call_outcome"
CALLBACK = "extract_callback"


@lru_cache(maxsize=None)
def system_prompt(name: str) -> str:
    time_expr = (PROMPT_DIR / "time_expression.md").read_text(encoding="utf-8")
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").replace("{time_expr}", time_expr).strip()


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


def extract(client: GroqJSONClient, record: CallRecord) -> Extraction:
    user = user_message(record)
    usage = Usage()
    facts, u1 = client.complete(system_prompt(CALL_OUTCOME), user, CallFacts, "call_facts")
    usage += u1
    callback, u2 = client.complete(system_prompt(CALLBACK), user, CallbackExtraction, "callback")
    usage += u2
    return Extraction(facts, callback, usage)
