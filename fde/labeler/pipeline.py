"""Per-record labeling with failure isolation: always returns one valid prediction."""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..io import CallRecord
from ..transcript import customer_word_count, parse_turns
from .combine import combine
from .extract import extract
from .llm import GroqJSONClient
from .taxonomy import UNABLE
from .validate import OUTPUT_KEYS, contract_errors, fallback_prediction

log = logging.getLogger(__name__)


def _prediction(transcript_id: str, labels) -> dict:
    values = {
        "transcript_id": transcript_id,
        "disposition": labels.disposition,
        "sub_disposition": labels.sub_disposition,
        "lead_quality": labels.lead_quality,
        "next_call_at": labels.next_call_at,
    }
    return {k: values[k] for k in OUTPUT_KEYS}


def label_record(client: Optional[GroqJSONClient], record: CallRecord) -> tuple[dict, dict]:
    """Return (prediction, debug). Never raises."""
    t0 = time.monotonic()
    debug: dict = {"transcript_id": record.transcript_id}
    try:
        if customer_word_count(parse_turns(record.transcript)) == 0:
            # Nothing the customer said: no evidence to extract, skip the model.
            pred = {
                "transcript_id": record.transcript_id,
                "disposition": UNABLE,
                "sub_disposition": "Incomplete Conversation",
                "lead_quality": "Not Assessable",
                "next_call_at": None,
            }
            debug["trace"] = ["no customer speech -> D5"]
        else:
            ex = extract(client, record)
            labels = combine(ex.facts, ex.callback, record.call_started_at, record.timezone)
            pred = _prediction(record.transcript_id, labels)
            debug.update(
                facts=ex.facts.model_dump(),
                callback=ex.callback.model_dump(),
                trace=labels.trace,
                usage=vars(ex.usage),
            )
        errors = contract_errors(pred)
        if errors:
            raise ValueError(f"contract violation: {errors}")
    except Exception as exc:  # per-record isolation: one bad record must not sink the run
        log.error("%s: falling back (%s: %s)", record.transcript_id, type(exc).__name__, exc)
        pred = fallback_prediction(record.transcript_id, record.call_started_at, record.timezone)
        debug["error"] = f"{type(exc).__name__}: {exc}"
        debug["fallback"] = True

    debug["seconds"] = round(time.monotonic() - t0, 2)
    return pred, debug
