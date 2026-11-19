"""Runner checkpointing: finished records survive a stop and are not relabeled on rerun."""

from __future__ import annotations

import json
import sys

from call_labeling import run_labeling
from call_labeling.output_validator import fallback_prediction


def _write_calls(path, n):
    with open(path, "w") as fh:
        for i in range(n):
            fh.write(json.dumps({"transcript_id": f"T-{i}", "call_started_at": "2026-11-09T14:00:00+05:30",
                                 "timezone": "Asia/Kolkata", "transcript": "Customer: knee pain"}) + "\n")


def _run(monkeypatch, tmp_path, *extra):
    out = tmp_path / "pred.jsonl"
    argv = ["run_labeling", "--input", str(tmp_path / "calls.jsonl"), "--output", str(out),
            "--debug", str(tmp_path / "debug.jsonl"), "--concurrency", "1", *extra]
    monkeypatch.setattr(sys, "argv", argv)
    assert run_labeling.main() == 0
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_rerun_resumes_and_retries_fallbacks(monkeypatch, tmp_path):
    _write_calls(tmp_path / "calls.jsonl", 3)
    labeled = []

    def fake_label(client, record):
        labeled.append(record.transcript_id)
        pred = fallback_prediction(record.transcript_id, record.call_started_at)
        debug = {"transcript_id": record.transcript_id, "seconds": 0.0}
        if record.transcript_id == "T-1" and labeled.count("T-1") == 1:
            debug["fallback"] = True  # first attempt failed
        return pred, debug

    monkeypatch.setattr(run_labeling, "GroqJSONClient", lambda settings: object())
    monkeypatch.setattr(run_labeling, "label_record", fake_label)

    first = _run(monkeypatch, tmp_path)
    assert [p["transcript_id"] for p in first] == ["T-0", "T-1", "T-2"]

    second = _run(monkeypatch, tmp_path)
    assert labeled == ["T-0", "T-1", "T-2", "T-1"]  # only the fallback is retried
    assert [p["transcript_id"] for p in second] == ["T-0", "T-1", "T-2"]


def test_limit_caps_the_run(monkeypatch, tmp_path):
    _write_calls(tmp_path / "calls.jsonl", 5)
    monkeypatch.setattr(run_labeling, "GroqJSONClient", lambda settings: object())
    monkeypatch.setattr(run_labeling, "label_record", lambda c, r: (
        fallback_prediction(r.transcript_id, r.call_started_at), {"transcript_id": r.transcript_id, "seconds": 0.0}))
    assert len(_run(monkeypatch, tmp_path, "--limit", "2")) == 2
