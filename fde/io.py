"""JSONL I/O and the input-record contract shared by every task."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from pydantic import BaseModel, ConfigDict

INPUT_FIELDS = ("transcript_id", "call_started_at", "timezone", "transcript")


class CallRecord(BaseModel):
    """The only fields allowed into an inference workflow."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    transcript_id: str
    call_started_at: str
    timezone: str = "Asia/Kolkata"
    transcript: str


def iter_jsonl(path: str | Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON ({exc})") from exc


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_calls(path: str | Path) -> list[CallRecord]:
    """Load input records, dropping every non-input key (labels never pass this boundary)."""
    records = [CallRecord.model_validate(row) for row in iter_jsonl(path)]
    ids = [r.transcript_id for r in records]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate transcript_id(s) in {path}: {sorted(dupes)}")
    return records
