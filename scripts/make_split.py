"""Deterministic stratified dev/holdout split. Evaluation tooling only.

Stratifies on (disposition, sub_disposition) so rare classes land in both
sides where possible. Writes one id per line to data/splits/.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from call_labeling.input_records import iter_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", default="data/gold_labels.jsonl")
    ap.add_argument("--out", default="data/splits")
    ap.add_argument("--holdout-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=20261019)
    args = ap.parse_args()

    strata: dict[tuple, list[str]] = defaultdict(list)
    for g in iter_jsonl(args.gold):
        strata[(g["disposition"], g["sub_disposition"])].append(g["transcript_id"])

    rng = random.Random(args.seed)
    dev, holdout = [], []
    for key in sorted(strata):
        ids = sorted(strata[key])
        rng.shuffle(ids)
        n_hold = round(len(ids) * args.holdout_frac) if len(ids) > 1 else 0
        holdout += ids[:n_hold]
        dev += ids[n_hold:]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dev_ids.txt").write_text("\n".join(sorted(dev)) + "\n")
    (out / "holdout_ids.txt").write_text("\n".join(sorted(holdout)) + "\n")
    (out / "seed.txt").write_text(f"{args.seed}\n")
    print(f"dev={len(dev)} holdout={len(holdout)} -> {out}/")


if __name__ == "__main__":
    main()
