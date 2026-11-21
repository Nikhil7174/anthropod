"""Task 1. Label call transcripts: input JSONL in, prediction JSONL out.

    python -m call_labeling.run_labeling \\
        --input data/calls_input.jsonl --output outputs/labeling_predictions.jsonl

Reads the provider's API key from the environment (or a local .env). Only the input
fields transcript_id, call_started_at, timezone and transcript are used.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .input_records import load_calls, write_jsonl
from .label_one_call import label_record
from .llm_client import JSONClient, LLMError, QuotaExhausted
from .settings import DEFAULT_PROVIDER, PROVIDERS, SETTINGS, settings_for

log = logging.getLogger("run")


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _load_checkpoint(path: Path, wanted: set[str]) -> dict[str, tuple[dict, dict]]:
    """Finished records from an earlier run. Fallbacks are dropped so they get another try."""
    done: dict[str, tuple[dict, dict]] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line cut short by a kill
        tid = row["prediction"]["transcript_id"]
        if tid in wanted and not row["debug"].get("fallback"):
            done[tid] = (row["prediction"], row["debug"])
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="input JSONL")
    ap.add_argument("--output", required=True, help="prediction JSONL (exactly five keys per line)")
    ap.add_argument("--debug", help="per-record evidence and trace JSONL (default: outputs/debug/<output stem>.jsonl)")
    ap.add_argument("--concurrency", type=int, default=SETTINGS.concurrency)
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default=DEFAULT_PROVIDER,
                    help="inference host (default: cerebras, open model gpt-oss-120b). Groq is --provider groq")
    ap.add_argument("--model", default=None,
                    help="model id; omitted means the provider's pinned model, recorded in the meta file")
    ap.add_argument("--ids", help="comma-separated transcript_ids to run (development only)")
    ap.add_argument("--limit", type=int, help="run only the first N records after --ids filtering")
    ap.add_argument("--fresh", action="store_true", help="ignore the checkpoint and relabel every record")
    ap.add_argument("--calls", type=int, choices=(1, 2), default=1,
                    help="model calls per record: 1 (outcome and callback in one JSON object) or 2")
    ap.add_argument("--votes", type=int, default=1,
                    help="repeat the extraction this many times and keep a blocker only when a majority agrees")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _load_dotenv()
    settings = settings_for(args.provider, model=args.model, concurrency=args.concurrency)

    records = load_calls(args.input)
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        records = [r for r in records if r.transcript_id in wanted]
    if args.limit:
        records = records[: args.limit]

    debug_path = Path(args.debug) if args.debug else Path("outputs/debug") / (Path(args.output).stem + ".jsonl")
    checkpoint_path = debug_path.with_suffix(".checkpoint.jsonl")
    results = {} if args.fresh else _load_checkpoint(checkpoint_path, {r.transcript_id for r in records})
    todo = [r for r in records if r.transcript_id not in results]
    log.info("%d records; %d already in checkpoint, %d to label; provider=%s model=%s calls=%d votes=%d",
             len(records), len(results), len(todo), settings.provider, settings.model, args.calls, args.votes)

    try:
        client = JSONClient(settings) if todo else None
    except LLMError as exc:
        log.error("%s", exc)
        return 2

    t0 = time.monotonic()
    lock = threading.Lock()
    stop = threading.Event()
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    interrupted = False

    with open(checkpoint_path, "w" if args.fresh else "a", encoding="utf-8") as ckpt:
        def work(record):
            if stop.is_set():
                return
            try:
                pred, debug = label_record(client, record, calls=args.calls, votes=args.votes)
            except QuotaExhausted:
                stop.set()
                raise
            with lock:
                results[record.transcript_id] = (pred, debug)
                ckpt.write(json.dumps({"prediction": pred, "debug": debug}, ensure_ascii=False) + "\n")
                ckpt.flush()
                log.info("[%d/%d] %s %s/%s in %.1fs%s", len(results), len(records), record.transcript_id,
                         pred["disposition"], pred["sub_disposition"], debug["seconds"],
                         " (FALLBACK)" if debug.get("fallback") else "")

        pool = ThreadPoolExecutor(max_workers=max(1, settings.concurrency))
        futures = [pool.submit(work, r) for r in todo]
        try:
            for f in as_completed(futures):
                f.result()
            pool.shutdown()
        except (KeyboardInterrupt, QuotaExhausted) as exc:
            interrupted = True
            reason = "interrupted" if isinstance(exc, KeyboardInterrupt) else f"stopping, {exc}"
            log.warning("%s: writing the %d finished records; rerun the same command to resume", reason, len(results))
            pool.shutdown(wait=False, cancel_futures=True)
    wall = time.monotonic() - t0

    finished = [results[r.transcript_id] for r in records if r.transcript_id in results]  # input order
    predictions = [p for p, _ in finished]
    debug_rows = [d for _, d in finished]
    write_jsonl(args.output, predictions)
    write_jsonl(debug_path, debug_rows)

    usage = [d.get("usage", {}) for d in debug_rows]
    prompt = sum(u.get("prompt_tokens", 0) for u in usage)
    completion = sum(u.get("completion_tokens", 0) for u in usage)
    meta = {
        "records": len(predictions),
        "records_requested": len(records),
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
        "llm_calls_per_record": args.calls,
        "votes": args.votes,
        "settings": settings.as_dict(),
    }
    Path(args.output).with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    log.info("wrote %s (%d/%d records, %d fallbacks) in %.1fs; tokens in/out %d/%d; ~$%.4f",
             args.output, meta["records"], len(records), meta["fallbacks"], wall, prompt, completion,
             meta["estimated_cost_usd"])
    return STOPPED_EARLY if interrupted else 0


STOPPED_EARLY = 3

if __name__ == "__main__":
    code = main()
    if code == STOPPED_EARLY:
        logging.shutdown()
        os._exit(code)  # worker threads may be asleep in backoff; do not wait for them
    sys.exit(code)
