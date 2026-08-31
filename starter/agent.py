import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("AGENT", "").lower() == "baseline":
    from starter.baseline_agent import Agent  # noqa: F401
else:
    from copilot.agent import Agent  # noqa: F401
