import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Unit tests run the deterministic agent even when a real key is in .env; LLM tests inject fake clients explicitly.
os.environ["COPILOT_LLM"] = "0"

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"
PROFILE = {"purchase_frequency": "3-4 prior purchases", "average_prior_rating": 4.5, "rating_style": "usually positive",
           "preference_tags": ["fit"], "summary": "Prior purchases emphasize fit."}


@pytest.fixture(scope="session")
def agent():
    from copilot.agent import Agent
    a = Agent(CATALOG)
    assert a.init_error is None, a.init_error
    return a


@pytest.fixture(scope="session")
def harness():
    from evaluator import local_evaluator as ev
    samples = ev.load_jsonl(PUBLIC)
    ids, cats, products = ev.catalog_index(CATALOG)
    return ev, samples, ids, cats, products


@pytest.fixture(scope="session")
def cards(harness):
    """(sample, target, coarse category, intent card) for the 200 public sessions."""
    ev, samples, ids, cats, products = harness
    out = []
    for s in samples:
        t = str(s["ground_truth"]["parent_asin"])
        card, _ = ev.materialize_hidden_fields(s, products)
        out.append((s, t, ev.coarse_category(cats[t]), card))
    return out
