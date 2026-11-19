"""Score task-2 gender predictions against the hand labels. Not implemented yet.

    python -m evaluation.eval_gender \\
        --pred outputs/gender_predictions.jsonl --gold customer_gender/gender_labels_manual.jsonl
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print("gender evaluation is not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
