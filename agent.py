"""Submission entry file (rules: 'one Python agent entry file exporting Agent'). Works from any CWD and when copied
next to copilot/ into an organizer layout."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from copilot.agent import Agent  # noqa: E402,F401
