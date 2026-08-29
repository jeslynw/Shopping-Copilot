import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_vendored_evaluator_unmodified():
    pinned = (ROOT / "tests" / "evaluator.sha256").read_text().split()[0]
    actual = hashlib.sha256((ROOT / "evaluator" / "local_evaluator.py").read_bytes()).hexdigest()
    assert actual == pinned, "evaluator/local_evaluator.py differs from the pinned kit file"
