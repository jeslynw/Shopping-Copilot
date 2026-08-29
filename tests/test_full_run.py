"""Slow gates on the full 200 public sessions through the REAL evaluator (≈20 s each)."""
import json
import os
import random
import subprocess
import sys

import pytest

from tests.conftest import CATALOG, PUBLIC, ROOT
from tools.run_eval import Checked


@pytest.fixture(scope="module")
def shipped(agent, harness):
    ev, samples, ids, cats, products = harness
    checked = Checked(agent)
    res = ev.evaluate(checked, samples, ids, cats, products)
    res["_checked"] = checked
    return res


def test_shipped_gates(shipped, agent):
    assert shipped["recommended_technical_score"] >= 0.93, shipped["recommended_technical_score"]
    assert shipped["scenario_metrics"]["intent_override"]["hit_rate_at_10"] == 1.0
    assert all(v["hit_rate_at_10"] >= 0.95 for v in shipped["scenario_metrics"].values()), shipped["scenario_metrics"]
    assert agent.internal_exceptions == 0 and agent.contract_violations == 0
    assert shipped["_checked"].violations == []
    lat = sorted(shipped["_checked"].latency)
    print("p95 ms", lat[int(len(lat) * 0.95) - 1])
    gate_ms = float(os.environ.get("COPILOT_P95_GATE_MS", "150"))   # dev machine ≈ 67 ms; shared CI runners ≈ 155 ms (eval.yml sets 400)
    assert lat[int(len(lat) * 0.95) - 1] < gate_ms


def test_lost_turn_amplification(agent, harness):
    """Harness drops 5% of turns (exception/timeout) after the agent answered: HR must stay ≥ 0.99, override HR 1.0."""
    ev, samples, ids, cats, products = harness
    rng = random.Random(7)

    class Dropper:
        def reset(self, *a): return agent.reset(*a)
        def respond(self, *a):
            out = agent.respond(*a)
            return {"message": "", "ask_attribute": None, "recommendations": []} if rng.random() < 0.05 else out
    res = ev.evaluate(Dropper(), samples, ids, cats, products)
    assert res["hit_rate_at_10"] >= 0.99, res["hit_rate_at_10"]
    assert res["scenario_metrics"]["intent_override"]["hit_rate_at_10"] == 1.0


def test_offline_flags_do_not_change_results(shipped):
    """COPILOT_OFFLINE=1 + dead ANTHROPIC_BASE_URL run (40 sessions) equals the default run session-for-session."""
    script = ("import json,sys; sys.path.insert(0, %r); from evaluator import local_evaluator as ev; from copilot.agent import Agent; "
              "S=ev.load_jsonl(%r)[:40]; ids,cats,prod=ev.catalog_index(%r); r=ev.evaluate(Agent(%r),S,ids,cats,prod); "
              "print(json.dumps(r['sessions']))" % (str(ROOT), str(PUBLIC), str(CATALOG), str(CATALOG)))
    env = {**os.environ, "COPILOT_OFFLINE": "1", "ANTHROPIC_BASE_URL": "http://127.0.0.1:9", "PYTHONHASHSEED": "12345"}
    r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    want = shipped["sessions"][:40]
    assert got == want


def test_determinism_across_hash_seeds():
    script = ("import json,sys; sys.path.insert(0, %r); from evaluator import local_evaluator as ev; from copilot.agent import Agent; "
              "S=ev.load_jsonl(%r)[:30]; ids,cats,prod=ev.catalog_index(%r); r=ev.evaluate(Agent(%r),S,ids,cats,prod); "
              "print(json.dumps(r['sessions']))" % (str(ROOT), str(PUBLIC), str(CATALOG), str(CATALOG)))
    outs = []
    for seed in ("0", "424242"):
        r = subprocess.run([sys.executable, "-c", script], env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append(r.stdout.strip().splitlines()[-1])
    assert outs[0] == outs[1]
