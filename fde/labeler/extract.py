"""Prompt assembly and the two extraction calls (facts, callback)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..io import CallRecord
from ..transcript import normalize
from .callback import parse_call_start
from .llm import GroqJSONClient, Usage
from .schema import CallbackExtraction, CallFacts

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def system_prompt(name: str) -> str:
    time_expr = (PROMPT_DIR / "time_expr.md").read_text(encoding="utf-8")
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
    facts, u1 = client.complete(system_prompt("facts"), user, CallFacts, "call_facts")
    usage += u1
    callback, u2 = client.complete(system_prompt("callback"), user, CallbackExtraction, "callback")
    usage += u2
    return Extraction(facts, callback, usage)
