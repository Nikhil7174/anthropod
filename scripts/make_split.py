"""Deterministic stratified dev/holdout split of the labeled calls.

Stratifies on (disposition, sub_disposition) so rare classes land in both
sides where possible. Writes data/splits.json; evaluation tooling only.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fde.io import iter_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", default="data/gold.jsonl")
    ap.add_argument("--out", default="data/splits.json")
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

    Path(args.out).write_text(
        json.dumps({"seed": args.seed, "dev": sorted(dev), "holdout": sorted(holdout)}, indent=2) + "\n"
    )
    print(f"dev={len(dev)} holdout={len(holdout)} -> {args.out}")


if __name__ == "__main__":
    main()
