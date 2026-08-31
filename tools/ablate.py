from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evaluator import local_evaluator as ev  # noqa: E402
from copilot.agent import Agent  # noqa: E402
from copilot.config import Config, from_env  # noqa: E402
from tools.run_eval import Checked  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
DATASET = ROOT / "data" / "public_set.jsonl"
DEFAULT_OUTPUT = ROOT / "docs" / "results" / "ablation.json"

# The ladder: each row adds one layer to the previous one; the last row is exactly Config() — the shipped agent.
# (key, label, overrides on copilot.Config; None = the kit's own starter agent)
LADDER: list[tuple[str, str, dict | None]] = [
    ("starter", "kit starter (stateless BM25, never asks)", None),
    ("bm25_ask", "BM25 over accumulated messages + fixed ask order feature→material→color→…",
     dict(query_source="messages", rerank=False, cat_sort_key=False, norm_match=False, match_fields="three",
          tiebreak="bm25", cutoff="none", exclusion="none")),
    ("rerank", "+ verbatim constraint-satisfaction rerank of the BM25 top-300",
     dict(query_source="messages", rerank=True, cat_sort_key=False, norm_match=False, match_fields="three",
          tiebreak="bm25", cutoff="none", exclusion="none")),
    ("category", "+ coarse-category match as the 2nd sort key",
     dict(query_source="messages", rerank=True, cat_sort_key=True, norm_match=False, match_fields="three",
          tiebreak="bm25", cutoff="none", exclusion="none")),
    ("popularity", "+ popularity tie-break inside the tied tier (MostPop, `rating_number`)",
     dict(query_source="messages", rerank=True, cat_sort_key=True, norm_match=False, match_fields="three",
          tiebreak="popularity", cutoff="none", exclusion="none")),
    ("norm", "+ norm() six-field matcher (incl. description), extracted-term query",
     dict(cutoff="none", exclusion="none")),
    ("r6", "+ R6 cutoff: tier > 10 & turn ≤ 3 → single pick (ungated)", dict(cutoff="R6", exclusion="none")),
    ("gated", "+ information gate on the cutoff (template-provenance, previous reply yielded)", dict(exclusion="none")),
    ("shipped", "SHIPPED = + previous-turn-only exclusion (no detection, self-healing)", dict()),
]

# Disclosed, not shipped. Each is the shipped Config with one flag changed.
NOT_SHIPPED: list[tuple[str, str, dict]] = [
    ("top1", "always exactly 1 item, no gate — metric artefact, NOT shipped", dict(cutoff="top1")),
    ("no_pop", "no popularity prior (BM25 tie-break), otherwise shipped", dict(tiebreak="bm25")),
    ("no_cutoff", "shipped without the cutoff (always the full shelf)", dict(cutoff="none")),
    ("no_excl", "shipped without exclusion", dict(exclusion="none")),
    ("turn5", "cumulative exclusion from turn ≥ 5 (earlier revision)", dict(exclusion="turn5")),
    ("naive_excl", "naive cumulative exclusion — deletes the target in override sessions", dict(exclusion="naive")),
    ("gated2", "gate also released by recognised exhausted/boundary replies", dict(cutoff="gated2")),
    ("pool_union", "pool = top-300 ∪ matched-category members", dict(pool_union_category=True)),
    ("pool1000", "pool 1000 instead of 300", dict(pool=1000)),
    ("clause", "clause-only extractor (robustness tax on clean strings)", dict(extractor="clause")),
]

# Reference-implementation rows (analysis/experiments/common.py) — these layers were never built into copilot/.
REFERENCE: list[tuple[str, str, str]] = [
    ("hard_cat", "hard `categories:` FTS filter instead of the sort key (V3) — reference impl.", "hard_cat"),
    ("other", "`other` ask exploit (V4) — reference impl.", "other"),
    ("detect_excl", "detection-gated (override-safe) cumulative exclusion — reference impl.", "detect_excl"),
]


def technical(res: dict) -> dict:
    return {"technical_score": res["recommended_technical_score"], "hit_rate_at_10": res["hit_rate_at_10"],
            "mrr": res["mrr"], "mttc": res["mttc"],
            "override_hr": res["scenario_metrics"].get("intent_override", {}).get("hit_rate_at_10"),
            "scenario_metrics": res["scenario_metrics"]}


def run_copilot(cfg: Config | None, samples, ids, cats, products, para) -> dict:
    if cfg is None:
        from starter.baseline_agent import Agent as Baseline
        agent, subject, checked = Baseline(str(CATALOG)), None, None
        subject = agent
    else:
        agent = Agent(CATALOG, cfg)
        checked = Checked(agent)
        subject = checked
    if para:
        para.install()
    t0 = time.perf_counter()
    try:
        res = ev.evaluate(subject, samples, ids, cats, products)
    finally:
        if para:
            para.uninstall()
    row = {**technical(res), "wall_s": round(time.perf_counter() - t0, 1), "sessions": res["sessions"],
           "config": dict(cfg.__dict__) if cfg is not None else None}
    if checked is not None:
        lat = sorted(checked.latency) or [0.0]
        row.update(p50_ms=round(lat[len(lat) // 2], 1), p95_ms=round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
                   internal_exceptions=agent.internal_exceptions, contract_violations=len(checked.violations),
                   llm=agent.llm.summary() if agent.llm else None)
    return row


def run_reference(kind: str, samples, para, cache: dict) -> dict:
    sys.path.insert(0, str(ROOT / "analysis" / "experiments"))
    import common as C  # noqa: E402
    if "catalog" not in cache:
        cache["catalog"] = C.Catalog(CATALOG, verbose=False)
    if kind == "hard_cat":
        cfg = replace(C.BASE(), cat_hard_filter=True)
    elif kind == "other":
        cfg = replace(C.BASE(), ask_other=True)
    elif kind == "detect_excl":
        cfg = replace(C.SHIPPED(), exclusion="override_safe")
    else:
        raise ValueError(kind)
    if para:
        para.install()
    try:
        res = C.run(cfg, cache["catalog"], samples, verbose=False)
    finally:
        if para:
            para.uninstall()
    return {**technical(res), "wall_s": res["wall_s"], "sessions": res["sessions"], "p50_ms": res["p50_ms"],
            "p95_ms": res["p95_ms"], "internal_exceptions": res["agent_exceptions"], "contract_violations": None,
            "config": res["config"]}


def per_session_accounting(gated: dict, full: dict) -> dict:
    """Cutoff accounting (PLAN §7b): per-session TechScore contribution of the gated cutoff vs always top-10.
    contribution = 0.5·hit + 0.3·RR + 0.2·(11 − hit_turn)/10 — its mean over sessions IS the TechnicalScore."""
    def contrib(s: dict) -> float:
        turn = s["first_hit_turn"] if s["first_hit_turn"] is not None else ev.MAX_TURNS + 1
        return 0.5 * (1.0 if s["hit"] else 0.0) + 0.3 * s["reciprocal_rank"] + 0.2 * (11.0 - turn) / 10.0
    by = {s["sample_id"]: s for s in full["sessions"]}
    out = {"sessions": 0, "delayed": 0, "lost": 0, "rank_improved": 0, "net_hurt": 0, "net_helped": 0, "unchanged": 0}
    deltas = []
    for g in gated["sessions"]:
        f = by.get(g["sample_id"])
        if f is None:
            continue
        d = contrib(g) - contrib(f)
        deltas.append(d)
        out["sessions"] += 1
        if f["hit"] and not g["hit"]:
            out["lost"] += 1
        elif f["hit"] and g["hit"] and g["first_hit_turn"] > f["first_hit_turn"]:
            out["delayed"] += 1
        if f["hit"] and g["hit"] and (g["best_rank"] or 99) < (f["best_rank"] or 99):
            out["rank_improved"] += 1
        if d < -1e-9:
            out["net_hurt"] += 1
        elif d > 1e-9:
            out["net_helped"] += 1
        else:
            out["unchanged"] += 1
    if deltas:
        out.update(mean_delta=round(sum(deltas) / len(deltas), 4), worst_delta=round(min(deltas), 4),
                   best_delta=round(max(deltas), 4))
    return out


def fmt_table(rows: list[dict], shipped: dict | None) -> str:
    cols = ["key", "variant", "HR@10", "MRR", "MTTC", "TechScore", "Δ vs shipped", "override HR", "p50/p95 ms"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        d = "" if shipped is None else f"{r['technical_score'] - shipped['technical_score']:+.3f}"
        lat = f"{r['p50_ms']}/{r['p95_ms']}" if r.get("p50_ms") is not None else "—"
        ts = f"**{r['technical_score']:.3f}**" if r["key"] == "shipped" else f"{r['technical_score']:.3f}"
        ovr = f"{r['override_hr']:.2f}" if r.get("override_hr") is not None else "—"
        out.append(f"| {r['key']} | {r['label']} | {r['hit_rate_at_10']:.3f} | {r['mrr']:.3f} | {r['mttc']:.2f} | {ts} | {d} | {ovr} | {lat} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", default="", help="comma-separated row keys (default: ladder + not-shipped)")
    ap.add_argument("--reference", action="store_true", help="include analysis/experiments reference rows")
    ap.add_argument("--paraphrase", action="store_true", help="run every row under the paraphrase fixture (dev harness)")
    ap.add_argument("--styles", nargs="*", default=None, help="fixture styles to use with --paraphrase")
    ap.add_argument("--llm-extract", action="store_true", help="add the grounded LLM-extraction row (needs an API key)")
    ap.add_argument("--per-session", action="store_true", help="cutoff accounting: shipped vs cutoff=none")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--keep-sessions", action="store_true", help="write per-session outcomes into the JSON too")
    args = ap.parse_args()

    samples = ev.load_jsonl(DATASET)
    if args.limit:
        samples = samples[:args.limit]
    ids, cats, products = ev.catalog_index(CATALOG)

    para = None
    if args.paraphrase:
        from tools.paraphrase_eval import FIXTURE, FixtureParaphraser
        if not FIXTURE.is_file():
            print(f"fixture {FIXTURE} missing — run tools/gen_paraphrases.py first", file=sys.stderr)
            return 2
        para = FixtureParaphraser(FIXTURE, args.styles)

    plan: list[tuple[str, str, object, str]] = [(k, l, ov, "copilot") for k, l, ov in LADDER]
    plan += [(k, l, ov, "copilot") for k, l, ov in NOT_SHIPPED]
    if args.reference:
        plan += [(k, l, kind, "reference") for k, l, kind in REFERENCE]
    if args.llm_extract:
        cfg = from_env()
        if not cfg.llm:
            print("--llm-extract: no API key in the environment / .env — row skipped", file=sys.stderr)
        else:
            plan.append(("llm_extract", "grounded LLM extraction when no template matched (polish off)",
                         replace(cfg, llm_extract=True, llm_polish=False), "llm"))
    if args.per_session:
        keys = {k for k, *_ in plan}
        for need in ("shipped", "no_cutoff"):
            if need not in keys:
                plan.append(next((k, l, ov, "copilot") for k, l, ov in LADDER + NOT_SHIPPED if k == need))
    if args.rows:
        want = {k.strip() for k in args.rows.split(",") if k.strip()}
        if args.per_session:
            want |= {"shipped", "no_cutoff"}
        plan = [p for p in plan if p[0] in want]

    rows: list[dict] = []
    cache: dict = {}
    for key, label, spec, kind in plan:
        t0 = time.perf_counter()
        if kind == "reference":
            row = run_reference(spec, samples, para, cache)
        elif kind == "llm":
            row = run_copilot(spec, samples, ids, cats, products, para)
        else:
            row = run_copilot(None if spec is None else Config(**spec), samples, ids, cats, products, para)
        row.update(key=key, label=label, kind=kind)
        rows.append(row)
        print(f"  {key:<12} TS {row['technical_score']:.3f}  HR {row['hit_rate_at_10']:.3f}  MRR {row['mrr']:.3f}  "
              f"MTTC {row['mttc']:.2f}  ovr {row['override_hr'] if row['override_hr'] is not None else float('nan'):.2f}"
              f"  ({time.perf_counter() - t0:.0f}s)", file=sys.stderr)

    shipped = next((r for r in rows if r["key"] == "shipped"), None)
    title = "Ablation ladder — 200 public sessions, official evaluator"
    if args.paraphrase:
        title += f" — PARAPHRASED (fixture styles: {', '.join(para.styles)}; dev harness, not the official score)"
    print(f"\n## {title}\n")
    print(fmt_table(rows, shipped))

    accounting = None
    if args.per_session and shipped is not None:
        full = next((r for r in rows if r["key"] == "no_cutoff"), None)
        if full is not None:
            accounting = per_session_accounting(shipped, full)
            print("\n### Cutoff accounting — information-gated cutoff vs always top-10 (per session)\n")
            print("| sessions | delayed | lost | rank improved | net hurt | net helped | unchanged | mean Δ | worst Δ | best Δ |")
            print("|---|---|---|---|---|---|---|---|---|---|")
            print(f"| {accounting['sessions']} | {accounting['delayed']} | {accounting['lost']} | {accounting['rank_improved']} | "
                  f"{accounting['net_hurt']} | {accounting['net_helped']} | {accounting['unchanged']} | "
                  f"{accounting.get('mean_delta')} | {accounting.get('worst_delta')} | {accounting.get('best_delta')} |")

    out = {
        "date": date.today().isoformat(), "dataset": str(DATASET.relative_to(ROOT)), "sessions": len(samples),
        "paraphrase": bool(args.paraphrase), "styles": para.styles if para else None,
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "rows": [{k: v for k, v in r.items() if k != "sessions" or args.keep_sessions} for r in rows],
        "per_session_cutoff_accounting": accounting,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"\nwrote {args.output}")
    bad = [r["key"] for r in rows if r.get("internal_exceptions") or r.get("contract_violations")]
    if bad:
        print(f"WARNING: internal exceptions / contract violations in rows: {bad}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
