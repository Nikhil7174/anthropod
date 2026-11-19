"""Static guardrails on the inference path: no gold labels, no machine clock, no per-record logic."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFERENCE_FILES = [ROOT / "run.py", ROOT / "fde" / "io.py", ROOT / "fde" / "transcript.py"] + [
    p for p in (ROOT / "fde" / "labeler").rglob("*.py") if p.name != "evaluate.py"
]
PROMPTS = list((ROOT / "fde" / "labeler" / "prompts").glob("*.md"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_inference_never_touches_gold_or_evaluator():
    for path in INFERENCE_FILES:
        src = path.read_text()
        assert "gold" not in src.lower(), path
        assert not any("evaluate" in name for name in _imports(path)), path


def test_inference_never_reads_machine_clock():
    pattern = re.compile(r"datetime\.now|date\.today|datetime\.today|time\.time\(\)|utcnow")
    for path in INFERENCE_FILES:
        assert not pattern.search(path.read_text()), path


def test_no_transcript_ids_hardcoded():
    pattern = re.compile(r"AVT-\d{3}")
    for path in INFERENCE_FILES + PROMPTS:
        assert not pattern.search(path.read_text()), path
