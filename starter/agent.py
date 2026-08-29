"""Kit harness entry point: `python -m evaluator.local_evaluator` imports `Agent` from here.

Default → the team agent (`copilot/`). Set `AGENT=baseline` to score the kit's original weak BM25 starter
(`starter/baseline_agent.py`, unchanged) with the same command — a like-for-like A/B.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("AGENT", "").lower() == "baseline":
    from starter.baseline_agent import Agent  # noqa: F401
else:
    from copilot.agent import Agent  # noqa: F401
