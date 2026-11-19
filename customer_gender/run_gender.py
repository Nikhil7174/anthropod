"""Task 2 command line. Not implemented yet.

    python -m customer_gender.run_gender \\
        --input data/calls_input.jsonl --output outputs/gender_predictions.jsonl
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print("customer gender is not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
