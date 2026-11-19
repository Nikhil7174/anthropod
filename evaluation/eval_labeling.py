"""Score task-1 predictions against the reference answers. Never imported by call_labeling.

    python -m evaluation.eval_labeling --pred outputs/labeling_predictions.jsonl --split dev
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from call_labeling.input_records import iter_jsonl
from call_labeling.output_validator import contract_errors

FIELDS = ("disposition", "sub_disposition", "lead_quality", "next_call_at")
WEIGHTS = {"disposition": 15, "sub_disposition": 20, "lead_quality": 15, "next_call_at": 20}


def field_correct(pred: dict, gold: dict, field: str) -> bool:
    if field == "sub_disposition":  # credited only with the correct parent
        return pred["disposition"] == gold["disposition"] and pred["sub_disposition"] == gold["sub_disposition"]
    return pred.get(field) == gold[field]


def score(preds: dict[str, dict], golds: dict[str, dict]) -> dict:
    n = len(golds)
    correct = Counter()
    exact = 0
    mismatches = []
    confusion = Counter()
    for tid, gold in golds.items():
        pred = preds.get(tid)
        if pred is None or contract_errors(pred):
            mismatches.append((tid, "missing or invalid record", None, None))
            continue
        ok = {f: field_correct(pred, gold, f) for f in FIELDS}
        correct.update(f for f, v in ok.items() if v)
        exact += all(ok.values())
        confusion[(gold["sub_disposition"], pred["sub_disposition"])] += 1
        for f, v in ok.items():
            if not v:
                mismatches.append((tid, f, gold[f], pred.get(f)))
    acc = {f: correct[f] / n for f in FIELDS}
    return {
        "n": n,
        "accuracy": acc,
        "exact_match": exact / n,
        "label_points_of_70": sum(acc[f] * WEIGHTS[f] for f in FIELDS),
        "mismatches": mismatches,
        "confusion": confusion,
    }


def report(result: dict) -> str:
    lines = [f"n={result['n']}"]
    for f, a in result["accuracy"].items():
        lines.append(f"  {f:<16} {a:6.1%}")
    lines.append(f"  {'exact match':<16} {result['exact_match']:6.1%}")
    lines.append(f"  label points     {result['label_points_of_70']:.1f} / 70")
    off_diag = [(k, v) for k, v in result["confusion"].most_common() if k[0] != k[1]]
    if off_diag:
        lines.append("sub_disposition confusions (gold -> pred):")
        lines += [f"  {g} -> {p}: {c}" for (g, p), c in off_diag]
    if result["mismatches"]:
        lines.append("mismatches:")
        lines += [f"  {tid} {f}: gold={g!r} pred={p!r}" for tid, f, g, p in result["mismatches"]]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--gold", default="data/gold_labels.jsonl")
    ap.add_argument("--split", choices=("all", "dev", "holdout"), default="all")
    ap.add_argument("--splits", default="data/splits", help="directory with dev_ids.txt and holdout_ids.txt")
    args = ap.parse_args()

    golds = {g["transcript_id"]: g for g in iter_jsonl(args.gold)}
    if args.split != "all":
        ids = (Path(args.splits) / f"{args.split}_ids.txt").read_text().split()
        golds = {k: v for k, v in golds.items() if k in set(ids)}
    preds = {p["transcript_id"]: p for p in iter_jsonl(args.pred)}
    print(f"[{args.split}] " + report(score(preds, golds)))


if __name__ == "__main__":
    main()
