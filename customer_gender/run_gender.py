"""Task 2. Infer the caller's gender from speech cues. No model API is called.

    python -m customer_gender.run_gender \\
        --input data/calls_input.jsonl --output outputs/gender_predictions.jsonl

"Customer" is the person labeled Customer, not the patient. The label is
unknown when the cue families do not agree by enough of a margin.
"""

from __future__ import annotations

import argparse
import sys

from call_labeling.input_records import load_calls, write_jsonl

from .gender_scoring import predict_gender


def label_calls(records) -> list[dict]:
    rows = []
    for record in records:
        prediction = predict_gender(record.transcript)
        rows.append({"transcript_id": record.transcript_id, **prediction})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="input JSONL (transcript_id and transcript)")
    ap.add_argument("--output", required=True, help="prediction JSONL")
    args = ap.parse_args(argv)
    rows = label_calls(load_calls(args.input))
    write_jsonl(args.output, rows)
    print(f"wrote {args.output} ({len(rows)} records)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
