import json
import os
import shutil
import subprocess
import sys

from tests.conftest import CATALOG, ROOT

SCRIPT = """
import json, sys
import agent
a = agent.Agent(sys.argv[1])
a.reset("s", {"purchase_frequency": "", "average_prior_rating": None, "rating_style": "", "preference_tags": [], "summary": ""})
out = [a.respond("s", m, i + 1, 10)["recommendations"] for i, m in enumerate([
    "I'm looking for Basketball Men, but I'm still exploring.", "For that, what matters is: Drawstring closure."])]
print(json.dumps(out))
"""


def _run(cwd, pythonpath, catalog):
    env = {**os.environ, "PYTHONPATH": pythonpath}
    r = subprocess.run([sys.executable, "-c", SCRIPT, str(catalog)], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_three_import_modes_agree(tmp_path):
    a = _run(ROOT, str(ROOT), "data/catalog.jsonl")                      # repo root, relative catalog path (harness style)
    b = _run("/", str(ROOT), "data/catalog.jsonl")                       # CWD=/ → path resolved relative to the package
    bundle = tmp_path / "submission"
    bundle.mkdir()
    shutil.copy(ROOT / "agent.py", bundle / "agent.py")
    shutil.copytree(ROOT / "copilot", bundle / "copilot", ignore=shutil.ignore_patterns("__pycache__"))
    c = _run(bundle, str(bundle), CATALOG)                               # organizer layout: agent.py + copilot/ only
    assert a == b == c and a[0], (a, b, c)


def test_kit_harness_import_path():
    """`from starter.agent import Agent` (what evaluator/local_evaluator.py does) resolves to the copilot Agent."""
    r = subprocess.run([sys.executable, "-c", "from starter.agent import Agent; import copilot.agent as c; "
                        "assert Agent is c.Agent; print('ok')"], cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr[-1000:]


def test_agent_env_switch_selects_baseline():
    """AGENT=baseline makes the kit harness import the untouched kit starter instead of the team agent."""
    r = subprocess.run([sys.executable, "-c", "from starter.agent import Agent; import starter.baseline_agent as b; "
                        "assert Agent is b.Agent; print('ok')"], cwd=ROOT, env={**os.environ, "AGENT": "baseline"},
                       capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr[-1000:]
