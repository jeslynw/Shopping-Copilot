"""Offline CLI transcript of ONE public session through the evaluator's own simulator — recorded for the demo video
(docs/PLAN.md §6 P5). Nothing here touches the scored path; the agent is the same `copilot.agent.Agent`.

    .venv/bin/python tools/demo.py --session public_0042 --redact-brands
    .venv/bin/python tools/demo.py --index 7 --paraphrase casual        # fixture paraphrases: clause fallback + gate release
    .venv/bin/python tools/demo.py --session public_0042 --llm           # message polish on (needs a key); default is offline
    .venv/bin/python tools/demo.py --list buying                         # sample ids by scenario, to pick a session

Every turn prints the full top-`--top` shelf (default 10) with a movement column so you can watch the list react to
each answer: `NEW` = not on last turn's shelf, `↑n`/`↓n` = moved up/down n places, `=` = held its rank; a
`dropped out of the top N` line lists items the last shelf had that this one doesn't.

The simulator functions are the evaluator's (`initial_message`, `customer_reply`, `behavior_for`, `intent_card`,
`materialize_hidden_fields`, `normalize_recommendations`), imported unmodified; only one sample is run, and the catalog is
read once for the agent's FTS5 index plus a single streaming pass to fetch the target listing — so a session runs in a
few seconds. `--redact-brands` masks every shown item's `store` name in titles and messages (video trademark rule).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):        # box-drawing / arrow glyphs need UTF-8 even on a cp1252 console
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

CATALOG = ROOT / "data" / "catalog.jsonl"
DATASET = ROOT / "data" / "public_set.jsonl"
MASK = "▇▇▇▇"
WIDTH = 100


def target_product(catalog_path: Path, asin: str) -> dict:
    """One streaming pass; only lines that mention the asin are parsed."""
    from copilot.catalog import _open_text, resolve_catalog_path
    path = resolve_catalog_path(catalog_path) or catalog_path
    needle = f'"{asin}"'
    with _open_text(Path(path)) as fh:
        for line in fh:
            if needle in line:
                p = json.loads(line)
                if str(p.get("parent_asin")) == asin:
                    return p
    raise SystemExit(f"target {asin} not found in {path}")


def redactor(stores: set[str]):
    pats = [re.compile(r"(?<![a-z0-9])" + re.escape(s.strip()) + r"(?![a-z0-9])", re.I) for s in stores if len(s.strip()) >= 3]

    def redact(text: str) -> str:
        for p in pats:
            text = p.sub(MASK, text)
        return text
    return redact


def wrap(prefix: str, text: str) -> str:
    return textwrap.fill(" ".join(text.split()), WIDTH, initial_indent=prefix, subsequent_indent=" " * len(prefix))


def shelf_delta(asin: str, rank: int, prev: list[str]) -> str:
    """One-token movement tag for a shelf item versus the previous turn's shelf."""
    if not prev:
        return ""
    if asin not in prev:
        return "NEW"
    was = prev.index(asin) + 1
    if was == rank:
        return "="
    return f"{'↑' if was > rank else '↓'}{abs(was - rank)}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--session", help="sample_id, e.g. public_0042")
    g.add_argument("--index", type=int, help="0-based position in data/public_set.jsonl")
    g.add_argument("--list", metavar="SCENARIO", nargs="?", const="all",
                   help="print sample ids (optionally for one scenario: buying|browsing|intent_override|boundary) and exit")
    ap.add_argument("--redact-brands", action="store_true", help="mask store/brand names of shown items (video)")
    ap.add_argument("--paraphrase", metavar="STYLE", nargs="?", const="", default=None,
                    help="swap the simulator's strings for fixture paraphrases (data/paraphrases.jsonl); optional style")
    ap.add_argument("--llm", action="store_true", help="enable the LLM message polish (needs a key); default: offline")
    ap.add_argument("--top", type=int, default=10, help="how many shelf items to print per turn")
    ap.add_argument("--reveal", action="store_true", help="show the hidden target's rank on every turn, not only at the hit")
    ap.add_argument("--catalog", default=str(CATALOG))
    args = ap.parse_args()

    if not args.llm:
        os.environ["COPILOT_OFFLINE"] = "1"      # deterministic core; no key lookup, no network
    from evaluator import local_evaluator as ev
    from copilot.agent import Agent
    from copilot.rank import compile_matchers

    samples = ev.load_jsonl(DATASET)
    if args.list is not None:
        for s in samples:
            if args.list == "all" or s["scenario_type"] == args.list:
                print(f"{s['sample_id']}  {s['scenario_type']:<16} {s.get('difficulty_bucket', '')}")
        return 0
    if args.session:
        sample = next((s for s in samples if s["sample_id"] == args.session), None)
        if sample is None:
            raise SystemExit(f"no sample {args.session}")
    else:
        sample = samples[args.index if args.index is not None else 0]

    para = None
    if args.paraphrase is not None:
        from tools.paraphrase_eval import FIXTURE, FixtureParaphraser
        if not FIXTURE.is_file():
            raise SystemExit(f"fixture {FIXTURE} missing — run tools/gen_paraphrases.py first")
        para = FixtureParaphraser(FIXTURE, [args.paraphrase] if args.paraphrase else None).install()

    t_start = time.perf_counter()
    agent = Agent(args.catalog)
    if agent.catalog is None:
        raise SystemExit(f"agent could not load the catalog: {agent.init_error}")
    init_s = time.perf_counter() - t_start
    target = str(sample["ground_truth"]["parent_asin"])
    product = target_product(Path(args.catalog), target)
    card, behavior = ev.materialize_hidden_fields(sample, {target: product})
    eff = {**sample, "intent_card": card, "behavior": behavior}
    category = ev.coarse_category([str(v) for v in product.get("categories") or []])
    cat = agent.catalog
    stores: set[str] = set()
    if args.redact_brands and product.get("store"):
        stores.add(str(product["store"]))
    redact = redactor(stores) if args.redact_brands else (lambda t: t)

    mode = "LLM polish on" if (agent.llm is not None and agent.llm.enabled) else "offline, deterministic"
    print(f"Shopping Copilot — session {sample['sample_id']} · scenario {sample['scenario_type']} · "
          f"difficulty {sample.get('difficulty_bucket', '?')} · {mode}"
          + (f" · paraphrased ({', '.join(para.styles)})" if para else ""))
    print(f"catalog: {len(cat.ids):,} products indexed in {init_s:.1f}s · hidden target: "
          f"{'(revealed at the end)' if not args.reveal else target}")
    print("═" * WIDTH)

    sid = f"demo_{sample['sample_id']}"
    agent.reset(sid, sample["user_profile"])
    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    msg = ev.initial_message(eff, category, disclosed)
    hit_turn = best_rank = None
    turn_ms: list[float] = []
    prev_recs: list[str] = []            # last turn's shelf, for the movement column
    for turn in range(1, ev.MAX_TURNS + 1):
        print(f"\n── turn {turn} " + "─" * (WIDTH - 10))
        print(wrap("customer › ", msg))
        t0 = time.perf_counter()
        out = agent.respond(sid, msg, turn, ev.TOP_K)
        ms = (time.perf_counter() - t0) * 1000
        turn_ms.append(ms)
        st = agent.sessions.get(sid)
        parsed = getattr(st, "last_parsed", None)

        # what the agent understood this turn (provenance-tagged)
        if st is not None:
            new = [c for c in st.constraints if c.turn == st.turn]
            bits = []
            if turn == 1:
                bits.append(f"category: {', '.join(st.categories) if st.categories else '—'} ({st.cat_prov})")
            if parsed is not None:
                bits.append(f"reply shape: {parsed.kind}{'' if parsed.template else ' (no template matched → clause extractor)'}")
            if new:
                bits.append("new constraints: " + "; ".join(f'"{c.text}" [{c.provenance}]' for c in new))
            if turn > 1 and not new and parsed is not None and parsed.kind in ("exhausted", "boundary", "noinfo"):
                bits.append("no new constraint")
            print(wrap("  understood  ", " · ".join(bits)))
            print(f"  ledger      {len(st.constraints)} constraint{'s' if len(st.constraints) != 1 else ''} accumulated "
                  f"(nothing is ever erased) · attributes asked so far: {', '.join(sorted(st.consumed)) or '—'}")

        recs = ev.normalize_recommendations(out.get("recommendations"), cat.ids)
        titles = cat.titles(recs)
        if args.redact_brands:
            stores |= {s for _, s in titles.values() if s}
            redact = redactor(stores)
        matched: dict[str, tuple] = {}
        if st is not None and st.constraints and recs:
            matchers = compile_matchers(st.constraints, agent.cfg, cat)
            texts = cat.texts(recs, agent.cfg.match_fields)
            for a in recs:
                matched[a] = tuple(m.label for m in matchers if m.fn(texts.get(a, ""), a))

        print(wrap("  copilot ›   ", redact(out["message"])))
        shelf = f"shelf: {len(recs)} item{'s' if len(recs) != 1 else ''}"
        if len(recs) == 1 and turn <= 3:
            shelf += " — many candidates tie on everything stated so far, so the copilot commits to one pick and asks the tie-splitting question"
        churn = "" if not prev_recs else f"   ·   vs. last turn: {len(set(recs[:args.top]) - set(prev_recs[:args.top]))} new"
        print(f"  ask         {out['ask_attribute']}   ·   {shelf}{churn}   ·   {ms:.0f} ms")
        for i, a in enumerate(recs[:args.top], 1):
            title, store = titles.get(a, ("", ""))
            title = " ".join(str(title).split())[:70]
            why = f"  matched on: {'; '.join(repr(m) for m in matched.get(a, ())[:3])}" if matched.get(a) else ""
            mark = "  ◀ target" if (a == target and (args.reveal or (override_applied and a == target))) else ""
            delta = shelf_delta(a, i, prev_recs)
            print(f"    {i:>2}. {delta:<4} {a}  ★{cat.pop.get(a, 0):>7,} reviews  {redact(title)}{why}{mark}")
        if len(recs) > args.top:
            print(f"    … {len(recs) - args.top} more")
        if prev_recs and len(recs) >= args.top:
            gone = [x for x in prev_recs[:args.top] if x not in recs[:args.top]]
            if gone:
                print(f"    dropped out of the top {args.top}: {', '.join(gone)}")
        prev_recs = list(recs)

        if override_applied and target in recs:
            best_rank, hit_turn = recs.index(target) + 1, turn
            print(f"\n  ✓ target found at rank {best_rank} on turn {turn}")
            break
        if not override_applied and target in recs and args.reveal:
            print("  (target shown, but hits before the intent override do not count)")
        if turn == ev.MAX_TURNS:
            break
        override = eff.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            new_value = str(override.get("new_value", ""))
            if new_value:
                disclosed.add(new_value)
            msg = str(override.get("message", "Actually, please ignore my earlier preference."))
        else:
            msg, boundary_used = ev.customer_reply(eff, out.get("ask_attribute"), disclosed, boundary_used)

    if para:
        para.uninstall()
    print("\n" + "═" * WIDTH)
    ttitle = " ".join(str(product.get("title", "")).split())[:80]
    rr = 0.0 if best_rank is None else 1.0 / best_rank
    eff_turn = hit_turn if hit_turn is not None else ev.MAX_TURNS + 1
    print(f"target: {target}  {redact(ttitle)}  (★{cat.pop.get(target, 0):,} reviews · {category})")
    print(f"hidden intent card: hard {card['hard_constraints']} · soft {card['soft_preferences']}")
    if hit_turn is not None:
        print(f"result: HIT on turn {hit_turn} at rank {best_rank}  →  session score 0.5·1 + 0.3·{rr:.2f} + 0.2·{(11 - eff_turn) / 10:.2f} = "
              f"{0.5 + 0.3 * rr + 0.2 * (11 - eff_turn) / 10:.3f}")
    else:
        print("result: MISS after 10 turns (session score 0.000)")
    print(f"timing: agent init {init_s:.1f}s · turns p50 {sorted(turn_ms)[len(turn_ms) // 2]:.0f} ms, max {max(turn_ms):.0f} ms · "
          f"total {time.perf_counter() - t_start:.1f}s · LLM {agent.llm.summary() if agent.llm else 'off'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
