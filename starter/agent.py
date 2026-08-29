"""Kit-harness shim: `python -m evaluator.local_evaluator` does `from starter.agent import Agent` — re-export the copilot Agent.
The kit's weak BM25 baseline this file replaces is preserved in git history (commit "P0: kit vendored…")."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from copilot.agent import Agent  # noqa: E402,F401
