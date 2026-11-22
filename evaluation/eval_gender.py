"""Score task-2 gender predictions against the hand labels.

    python -m evaluation.eval_gender \\
        --pred outputs/gender_predictions.jsonl \\
        --gold customer_gender/gender_labels_manual.jsonl

Accuracy is computed on committed predictions only (pred is male or female,
and the hand label is too). Unknown is reported as its own rate. Hand labels
of "unclear" are read as unknown.

Also reports whether family A agrees with families B and C on calls where
both kinds of cue fired. That agreement does not use the hand labels.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from call_labeling.input_records import iter_jsonl

LABELS = ("male", "female", "unknown")


def _norm(label: str | None) -> str:
    if label in {None, "", "unclear"}:
        return "unknown"
    return str(label)


def _family_side(cues: list[dict], families: set[str]) -> str | None:
    sides = {c["side"] for c in cues if c.get("family") in families}
    if sides == {"female"}:
        return "female"
    if sides == {"male"}:
        return "male"
    return None


def score(preds: dict[str, dict], golds: dict[str, dict]) -> dict:
    confusion = Counter()
    mismatches = []
    committed_correct = committed = 0
    unknown_pred = 0
    family_agree = family_both = 0
    for tid, gold in golds.items():
        pred = preds.get(tid)
        gold_label = _norm(gold.get("customer_gender"))
        pred_label = "missing" if pred is None else _norm(pred.get("customer_gender"))
        confusion[(gold_label, pred_label)] += 1
        if pred_label == "unknown":
            unknown_pred += 1
        if pred_label in {"male", "female"} and gold_label in {"male", "female"}:
            committed += 1
            committed_correct += pred_label == gold_label
        if pred is not None and pred_label != gold_label:
            mismatches.append((tid, gold_label, pred_label, pred.get("cues") or []))
        if pred is not None:
            cues = pred.get("cues") or []
            a_side = _family_side(cues, {"A"})
            bc_side = _family_side(cues, {"B", "C"})
            if a_side and bc_side:
                family_both += 1
                family_agree += a_side == bc_side
    return {
        "n": len(golds),
        "committed": committed,
        "committed_correct": committed_correct,
        "unknown_pred": unknown_pred,
        "confusion": confusion,
        "mismatches": mismatches,
        "family_both": family_both,
        "family_agree": family_agree,
    }


def report(result: dict) -> str:
    n = result["n"]
    committed = result["committed"]
    accuracy = result["committed_correct"] / committed if committed else 0.0
    lines = [
        f"n={n}",
        f"committed accuracy {result['committed_correct']}/{committed} = {accuracy:.1%}",
        f"unknown predictions {result['unknown_pred']}/{n} = {result['unknown_pred'] / n if n else 0:.1%}",
        f"family A vs B/C agreement {result['family_agree']}/{result['family_both']}",
        "confusion (gold -> pred):",
    ]
    for gold in LABELS:
        for pred in (*LABELS, "missing"):
            count = result["confusion"][(gold, pred)]
            if count:
                lines.append(f"  {gold} -> {pred}: {count}")
    if result["mismatches"]:
        lines.append("mismatches:")
        for tid, gold, pred, cues in result["mismatches"]:
            families = ",".join(f"{c['family']}:{c['side']}" for c in cues[:8])
            lines.append(f"  {tid} gold={gold} pred={pred} cues={families}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--gold", default="customer_gender/gender_labels_manual.jsonl")
    ap.add_argument("--split", choices=("all", "holdout", "design"), default="all")
    ap.add_argument("--holdout", default="data/splits/gender_holdout_ids.txt")
    args = ap.parse_args(argv)

    golds = {g["transcript_id"]: g for g in iter_jsonl(args.gold)}
    preds = {p["transcript_id"]: p for p in iter_jsonl(args.pred)}
    if args.split != "all":
        held = set(Path(args.holdout).read_text().split())
        if args.split == "holdout":
            golds = {k: v for k, v in golds.items() if k in held}
        else:
            golds = {k: v for k, v in golds.items() if k not in held}
    print(f"[{args.split}] " + report(score(preds, golds)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
