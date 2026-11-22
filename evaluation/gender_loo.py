"""Leave-one-out bag-of-words logistic regression for task 2.

This is a comparison, not the submitted method. It learns from the hand
labels, which were themselves read off the same address terms, so a high
score does not show a separate capability. AVT-008 is excluded: it is the
only unclear hand label, and one example cannot train a third class.

    python -m evaluation.gender_loo
"""

from __future__ import annotations

import math
import re
from collections import Counter

from call_labeling.input_records import iter_jsonl, load_calls

_WORD = re.compile(r"[a-z']+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _fit_predict(train: list[tuple[Counter, int]], test: Counter) -> str:
    """L2 logistic regression. y=1 is male. Returns male or female."""
    df = Counter()
    for counts, _ in train:
        df.update(counts.keys())
    vocab = [w for w, n in df.items() if n >= 2]
    index = {w: i for i, w in enumerate(vocab)}
    dim = len(vocab)
    weight = [0.0] * dim
    bias = 0.0
    lr = 0.2
    reg = 0.5
    steps = 250
    for _ in range(steps):
        grad = [0.0] * dim
        grad_b = 0.0
        for counts, y in train:
            z = bias
            present = []
            for word, n in counts.items():
                i = index.get(word)
                if i is None:
                    continue
                value = math.log1p(n)
                present.append((i, value))
                z += weight[i] * value
            pred = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
            err = pred - y
            grad_b += err
            for i, value in present:
                grad[i] += err * value
        scale = lr / len(train)
        bias -= scale * grad_b
        for i in range(dim):
            weight[i] -= scale * (grad[i] + reg * weight[i])
    z = bias
    for word, n in test.items():
        i = index.get(word)
        if i is not None:
            z += weight[i] * math.log1p(n)
    return "male" if z >= 0 else "female"


def leave_one_out(rows: list[tuple[str, str, str]]) -> dict:
    """rows are (transcript_id, transcript, hand label male|female)."""
    prepared = [(tid, Counter(_tokens(text)), 1 if label == "male" else 0, label) for tid, text, label in rows]
    correct = 0
    misses = []
    for held in range(len(prepared)):
        train = [(counts, y) for i, (_, counts, y, _) in enumerate(prepared) if i != held]
        tid, counts, _, label = prepared[held]
        pred = _fit_predict(train, counts)
        correct += pred == label
        if pred != label:
            misses.append((tid, label, pred))
    majority = "male" if sum(y for *_, y, _ in prepared) >= len(prepared) / 2 else "female"
    majority_correct = sum(label == majority for *_, label in prepared)
    return {
        "n": len(prepared),
        "correct": correct,
        "majority": majority,
        "majority_correct": majority_correct,
        "misses": misses,
    }


def main() -> None:
    labels = {}
    for row in iter_jsonl("customer_gender/gender_labels_manual.jsonl"):
        label = row["customer_gender"]
        if label in {"male", "female"}:
            labels[row["transcript_id"]] = label
    rows = []
    for record in load_calls("data/calls_input.jsonl"):
        if record.transcript_id in labels:
            rows.append((record.transcript_id, record.transcript, labels[record.transcript_id]))
    result = leave_one_out(rows)
    n = result["n"]
    print(
        f"LOO bag-of-words logistic regression {result['correct']}/{n} "
        f"= {result['correct'] / n:.1%} on male/female hand labels"
    )
    print(
        f"majority class ({result['majority']}) {result['majority_correct']}/{n} "
        f"= {result['majority_correct'] / n:.1%}"
    )
    print(f"excluded unclear hand labels: {50 - n}")
    if result["misses"]:
        print("misses:")
        for tid, gold, pred in result["misses"]:
            print(f"  {tid} gold={gold} pred={pred}")


if __name__ == "__main__":
    main()
