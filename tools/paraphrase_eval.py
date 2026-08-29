"""Paraphrase robustness: run the official evaluate() with the simulator's strings replaced by paraphrases.

    python tools/paraphrase_eval.py                       # fixture data/paraphrases.jsonl (from gen_paraphrases.py)
    python tools/paraphrase_eval.py --synthetic           # built-in template paraphraser (analysis/experiments/common.py)
    python tools/paraphrase_eval.py --config llm=false    # any Config override, e.g. compare LLM extraction on/off

Monkeypatches initial_message / customer_reply / behavior_for in-process; the evaluator file is never edited.
The score is a DEV-HARNESS number (labelled as such in the report), not the official local score.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis" / "experiments"))
from evaluator import local_evaluator as ev  # noqa: E402
from copilot.agent import Agent  # noqa: E402
from tools.run_eval import Checked, parse_config  # noqa: E402

FIXTURE = ROOT / "data" / "paraphrases.jsonl"


class FixtureParaphraser:
    """Swap each simulator string for a paraphrase from the fixture (style chosen per session); fall back to the original."""

    def __init__(self, path: Path, styles: list[str] | None):
        self.table: dict[str, dict[str, str]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if not styles or r["style"] in styles:
                    self.table.setdefault(r["text"], {})[r["style"]] = r["paraphrase"]
        self.styles = sorted({s for v in self.table.values() for s in v})
        self.hits = self.misses = 0
        self._orig = (ev.initial_message, ev.customer_reply, ev.behavior_for)
        self._sid = ""

    def _swap(self, text: str) -> str:
        opts = self.table.get(text)
        if not opts:
            self.misses += 1
            return text
        style = self.styles[int(hashlib.md5(self._sid.encode()).hexdigest(), 16) % len(self.styles)]
        self.hits += 1
        return opts.get(style) or next(iter(opts.values()))

    def initial_message(self, sample, category, disclosed):
        self._sid = sample.get("sample_id", "")
        return self._swap(self._orig[0](sample, category, disclosed))

    def customer_reply(self, sample, ask_attribute, disclosed, boundary_used):
        text, flag = self._orig[1](sample, ask_attribute, disclosed, boundary_used)
        return self._swap(text), flag

    def behavior_for(self, scenario, card, rng):
        b = self._orig[2](scenario, card, rng)
        if "override" in b:
            b["override"]["message"] = self._swap(b["override"]["message"])
        return b

    def install(self):
        ev.initial_message, ev.customer_reply, ev.behavior_for = self.initial_message, self.customer_reply, self.behavior_for
        return self

    def uninstall(self):
        ev.initial_message, ev.customer_reply, ev.behavior_for = self._orig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default=str(FIXTURE))
    ap.add_argument("--styles", nargs="*", default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--config", nargs="*", default=[])
    ap.add_argument("--no-clean", action="store_true", help="skip the clean reference run")
    ap.add_argument("--output", default=str(ROOT / "results_paraphrase.json"))
    args = ap.parse_args()
    samples = ev.load_jsonl(ROOT / "data/public_set.jsonl")
    if args.limit:
        samples = samples[:args.limit]
    ids, cats, products = ev.catalog_index(ROOT / "data/catalog.jsonl")
    cfg = parse_config(args.config)
    rows = []

    def run(label, para):
        agent = Agent(ROOT / "data/catalog.jsonl", cfg)
        checked = Checked(agent)
        if para:
            para.install()
        try:
            res = ev.evaluate(checked, samples, ids, cats, products)
        finally:
            if para:
                para.uninstall()
        res["label"] = label
        res["llm"] = agent.llm.summary() if agent.llm else None
        res["violations"] = len(checked.violations)
        res["exceptions"] = agent.internal_exceptions
        rows.append(res)
        print(f"| {label} | {res['hit_rate_at_10']:.3f} | {res['mrr']:.3f} | {res['mttc']:.2f} | **{res['recommended_technical_score']:.3f}** | "
              f"{res['scenario_metrics'].get('intent_override', {}).get('hit_rate_at_10', 0):.2f} | {res['llm']['calls'] if res['llm'] else 0} |")

    print("| run | HR@10 | MRR | MTTC | TechScore | override HR | LLM calls |\n|---|---|---|---|---|---|---|")
    if not args.no_clean:
        run("clean (official strings)", None)
    if args.synthetic:
        import common as C  # analysis/experiments
        run("paraphrased — synthetic templates (dev harness)", C.Paraphraser())
    else:
        p = Path(args.fixture)
        if not p.is_file():
            print(f"fixture {p} missing — run tools/gen_paraphrases.py first, or pass --synthetic", file=sys.stderr)
            return 2
        fp = FixtureParaphraser(p, args.styles)
        run(f"paraphrased — fixture ({', '.join(fp.styles)}) (dev harness)", fp)
        print(f"\nfixture coverage: {fp.hits} strings swapped, {fp.misses} fell back to the original")
    Path(args.output).write_text(json.dumps([{k: v for k, v in r.items() if k != 'sessions'} for r in rows], indent=1) + "\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
