"""Per-record labeling with failure isolation: always returns one valid prediction."""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Optional

from .evidence_extraction import extract
from .evidence_schema import Blockers
from .input_records import CallRecord
from .label_rules import combine
from .label_vocabulary import UNABLE
from .llm_client import JSONClient, QuotaExhausted, Usage
from .output_validator import OUTPUT_KEYS, contract_errors, fallback_prediction
from .transcript_text import customer_word_count, parse_turns

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


_BLOCKER_ORDER = ("family", "cost", "travel", "current_treatment", "treatment_concern", "info_review")


def _majority(values: list, need: int):
    """The value shared by at least `need` samples. No majority returns None."""
    if not values:
        return None
    value, count = Counter(values).most_common(1)[0]
    return value if count >= need else None


def vote_blockers(blockers: list[Blockers]) -> Blockers:
    """Keep a blocker only when a strict majority of samples report it.

    `primary` is None when the samples do not agree. A listed blocker is kept
    when more than half the samples include it.
    """
    if not blockers:
        return Blockers()
    need = len(blockers) // 2 + 1
    primary = _majority([b.primary for b in blockers], need)
    counts = Counter(name for b in blockers for name in b.final_unresolved)
    unresolved = [name for name in _BLOCKER_ORDER if counts[name] >= need]
    if primary and primary not in unresolved:
        unresolved.append(primary)
    evidence = next((b.evidence for b in blockers if b.primary == primary and b.evidence), None)
    return Blockers(final_unresolved=unresolved, primary=primary, evidence=evidence)


def label_record(client: Optional[JSONClient], record: CallRecord, calls: int = 2, votes: int = 1) -> tuple[dict, dict]:
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
            samples = []
            usage = Usage()
            for _ in range(max(1, votes)):
                ex = extract(client, record, calls=calls)
                usage += ex.usage
                samples.append(ex)
            voted = vote_blockers([s.facts.blockers for s in samples])
            chosen = next((s for s in samples if s.facts.blockers.primary == voted.primary), samples[0])
            facts = chosen.facts.model_copy(update={"blockers": voted})
            debug["llm_calls"] = calls
            debug["votes"] = votes
            debug["vote_primaries"] = [s.facts.blockers.primary for s in samples]
            labels = combine(facts, chosen.callback, record.call_started_at, record.timezone)
            pred = _prediction(record.transcript_id, labels)
            debug.update(
                facts=facts.model_dump(),
                callback=chosen.callback.model_dump(),
                trace=labels.trace,
                usage=vars(usage),
            )
        errors = contract_errors(pred)
        if errors:
            raise ValueError(f"contract violation: {errors}")
    except QuotaExhausted:
        raise  # every later record would fail the same way; let the runner stop
    except Exception as exc:  # per-record isolation: one bad record must not sink the run
        log.error("%s: falling back (%s: %s)", record.transcript_id, type(exc).__name__, exc)
        pred = fallback_prediction(record.transcript_id, record.call_started_at, record.timezone)
        debug["error"] = f"{type(exc).__name__}: {exc}"
        debug["fallback"] = True

    debug["seconds"] = round(time.monotonic() - t0, 2)
    return pred, debug
