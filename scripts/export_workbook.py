"""Export the candidate workbook into input-only and gold-only JSONL files.

Inputs and gold labels are written to separate files so the inference path
can never read a label by accident.

    python scripts/export_workbook.py --workbook "FDE Hiring Assignment ....xlsx"
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fde.io import INPUT_FIELDS, write_jsonl  # noqa: E402

SHEET = "50 Labeled Calls"
GOLD_FIELDS = ("disposition", "sub_disposition", "lead_quality", "next_call_at")


def _null(value):
    return None if value is None or str(value).strip().lower() == "null" else value


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", help="path to the candidate .xlsx (default: first *.xlsx in repo root)")
    ap.add_argument("--out-dir", default="data")
    args = ap.parse_args()

    workbook = args.workbook or next(iter(sorted(glob.glob("*.xlsx"))), None)
    if not workbook:
        sys.exit("no workbook found; pass --workbook")

    ws = openpyxl.load_workbook(workbook, read_only=True)[SHEET]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() for h in next(rows)]
    missing = set(INPUT_FIELDS + GOLD_FIELDS) - set(header)
    if missing:
        sys.exit(f"sheet {SHEET!r} missing columns: {sorted(missing)}")

    calls, gold = [], []
    for raw in rows:
        rec = dict(zip(header, raw))
        if not rec.get("transcript_id"):
            continue
        calls.append({k: rec[k] for k in INPUT_FIELDS})
        gold.append({"transcript_id": rec["transcript_id"], **{k: _null(rec[k]) for k in GOLD_FIELDS}})

    out = Path(args.out_dir)
    write_jsonl(out / "calls.jsonl", calls)
    write_jsonl(out / "gold.jsonl", gold)
    print(f"wrote {len(calls)} calls and {len(gold)} gold rows to {out}/")


if __name__ == "__main__":
    main()
