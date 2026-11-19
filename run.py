"""Label call transcripts: input JSONL in, prediction JSONL out.

    python run.py --input data/calls.jsonl --output outputs/predictions.jsonl

Reads GROQ_API_KEY from the environment (or a local .env). Only the input
fields transcript_id, call_started_at, timezone and transcript are used.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from fde.io import load_calls, write_jsonl
from fde.labeler.config import SETTINGS
from fde.labeler.llm import GroqJSONClient, LLMError
from fde.labeler.pipeline import label_record

log = logging.getLogger("run")


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="input JSONL")
    ap.add_argument("--output", required=True, help="prediction JSONL (exactly five keys per line)")
    ap.add_argument("--debug", help="per-record extraction/trace JSONL (default: <output dir>/debug.jsonl)")
    ap.add_argument("--concurrency", type=int, default=SETTINGS.concurrency)
    ap.add_argument("--ids", help="comma-separated transcript_ids to run (development only)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _load_dotenv()
    settings = replace(SETTINGS, concurrency=args.concurrency)

    records = load_calls(args.input)
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        records = [r for r in records if r.transcript_id in wanted]
    log.info("loaded %d records; model=%s", len(records), settings.model)

    try:
        client = GroqJSONClient(settings)
    except LLMError as exc:
        log.error("%s", exc)
        return 2

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, settings.concurrency)) as pool:
        results = list(pool.map(lambda r: label_record(client, r), records))  # preserves input order
    wall = time.monotonic() - t0

    predictions = [p for p, _ in results]
    debug_rows = [d for _, d in results]
    write_jsonl(args.output, predictions)
    debug_path = Path(args.debug) if args.debug else Path(args.output).parent / "debug.jsonl"
    write_jsonl(debug_path, debug_rows)

    usage = [d.get("usage", {}) for d in debug_rows]
    prompt = sum(u.get("prompt_tokens", 0) for u in usage)
    completion = sum(u.get("completion_tokens", 0) for u in usage)
    meta = {
        "records": len(predictions),
        "fallbacks": sum(1 for d in debug_rows if d.get("fallback")),
        "wall_seconds": round(wall, 1),
        "mean_record_seconds": round(sum(d["seconds"] for d in debug_rows) / max(1, len(debug_rows)), 2),
        "requests": sum(u.get("requests", 0) for u in usage),
        "retries": sum(u.get("retries", 0) for u in usage),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "estimated_cost_usd": round(
            prompt / 1e6 * settings.price_input_per_m + completion / 1e6 * settings.price_output_per_m, 4
        ),
        "settings": settings.as_dict(),
    }
    Path(args.output).with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    log.info("wrote %s (%d records, %d fallbacks) in %.1fs; tokens in/out %d/%d; ~$%.4f",
             args.output, meta["records"], meta["fallbacks"], wall, prompt, completion, meta["estimated_cost_usd"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
