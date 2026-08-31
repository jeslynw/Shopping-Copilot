from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evaluator import local_evaluator as ev  # noqa: E402
from copilot.agent import Agent  # noqa: E402
from copilot.config import Config, from_env  # noqa: E402
from tools.validate_contract import validate  # noqa: E402


try:
    import resource  # Unix only; --profile RSS reporting degrades gracefully without it (e.g. on Windows)
except ImportError:
    resource = None


def rss_mb() -> float:
    if resource is None:
        return 0.0
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if platform.system() == "Darwin" else r / 1024


class Checked:
    """Wraps the agent: validates every response, counts violations, records per-turn latency."""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.violations: list = []
        self.latency: list[float] = []

    def reset(self, *a):
        return self.agent.reset(*a)

    def respond(self, *a):
        t0 = time.perf_counter()
        out = self.agent.respond(*a)
        self.latency.append((time.perf_counter() - t0) * 1000)
        errs = validate(out)
        if errs:
            self.violations.append(errs)
        return out


def parse_config(pairs: list[str]) -> Config:
    cfg = from_env()
    for p in pairs:
        k, v = p.split("=", 1)
        cur = getattr(cfg, k)
        if isinstance(cur, bool):
            v = v.lower() in ("1", "true", "yes")
        elif isinstance(cur, int):
            v = int(v)
        elif isinstance(cur, float):
            v = float(v)
        elif isinstance(cur, tuple):
            v = tuple(v.split(","))
        cfg = replace(cfg, **{k: v})
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(ROOT / "data/catalog.jsonl"))
    ap.add_argument("--dataset", default=str(ROOT / "data/public_set.jsonl"))
    ap.add_argument("--output", default=str(ROOT / "results.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--config", nargs="*", default=[])
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    samples = ev.load_jsonl(args.dataset)
    if args.limit:
        samples = samples[:args.limit]
    ids, cats, products = ev.catalog_index(args.catalog)
    t0 = time.perf_counter()
    agent = Agent(args.catalog, parse_config(args.config))
    startup = time.perf_counter() - t0
    checked = Checked(agent)
    t1 = time.perf_counter()
    res = ev.evaluate(checked, samples, ids, cats, products)
    wall = time.perf_counter() - t1
    lat = sorted(checked.latency)
    prof = {
        "startup_s": round(startup, 2), "eval_wall_s": round(wall, 1), "turns": len(lat),
        "p50_ms": round(lat[len(lat) // 2], 1), "p95_ms": round(lat[int(len(lat) * 0.95) - 1], 1), "max_ms": round(lat[-1], 1),
        "rss_mb_incl_harness": round(rss_mb(), 1), "internal_exceptions": agent.internal_exceptions,
        "agent_contract_violations": agent.contract_violations, "harness_contract_violations": len(checked.violations),
        "init_error": agent.init_error, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "config": agent.cfg.__dict__, "llm": agent.llm.summary() if agent.llm else None,
    }
    res["profile"] = prof
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(res, indent=2) + "\n")
    if not args.quiet:
        print(f"TechnicalScore {res['recommended_technical_score']:.4f}  HR@10 {res['hit_rate_at_10']:.3f}  MRR {res['mrr']:.4f}  "
              f"MTTC {res['mttc']:.3f}  efficiency {res['efficiency']:.3f}  (n={res['sample_count']})")
        print("| scenario | n | HR@10 | MRR | MTTC |\n|---|---|---|---|---|")
        for k, v in res["scenario_metrics"].items():
            print(f"| {k} | {v['sample_count']} | {v['hit_rate_at_10']:.3f} | {v['mrr']:.3f} | {v['mttc']:.2f} |")
        hits = Counter(s["first_hit_turn"] for s in res["sessions"] if s["hit"])
        print("hit turns:", dict(sorted(hits.items())), "· rank at hit:",
              dict(sorted(Counter(s["best_rank"] for s in res["sessions"] if s["hit"]).items())))
        if args.profile:
            print("profile:", json.dumps({k: v for k, v in prof.items() if k != "config"}))
        print(f"wrote {args.output}")
    bad = prof["internal_exceptions"] or prof["agent_contract_violations"] or prof["harness_contract_violations"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
