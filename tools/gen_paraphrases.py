"""Dev-time, run once: paraphrase every simulator string of the public set with Claude via the Message Batches API.

    python tools/gen_paraphrases.py --dry-run                # count strings / requests, no API call
    python tools/gen_paraphrases.py --styles 4               # ~4k requests, Haiku, a few minutes, ~$1–2
    python tools/gen_paraphrases.py --resume msgbatch_xxx    # fetch results of an existing batch

Output: data/paraphrases.jsonl  {"text": <exact simulator string>, "style": <name>, "paraphrase": <text>}
Product facts (constraint values) must survive verbatim inside the paraphrase; a paraphrase that breaks one is dropped
and counted. tools/paraphrase_eval.py reads only this fixture — deterministic, offline, CI-runnable.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evaluator import local_evaluator as ev  # noqa: E402
from copilot.config import ATTRS  # noqa: E402

OUT = ROOT / "data" / "paraphrases.jsonl"
STYLES = {
    "terse": "a terse shopper who types short fragments",
    "chatty": "a chatty, friendly shopper who adds small talk",
    "formal": "a polite, formal shopper writing full sentences",
    "casual": "a casual shopper using everyday phrasing and contractions",
    "indirect": "a shopper who states things indirectly (e.g. 'ideally', 'I tend to prefer')",
}
SYSTEM = ("Rewrite the customer's message in the voice described, keeping the exact same meaning and information. "
          "Product facts inside the message — everything after 'requirement is:', 'what matters is:' or 'What I need is:' "
          "and the product category — MUST be copied verbatim, character for character. Do not add new requirements. "
          "No spelling errors. Reply with the rewritten message only.")


def simulator_strings(samples, products, categories) -> dict[str, list[str]]:
    """Every string the public-set simulator can emit, keyed by string → the product facts it must preserve."""
    out: dict[str, list[str]] = {}
    for s in samples:
        t = str(s["ground_truth"]["parent_asin"])
        card, beh = ev.materialize_hidden_fields(s, products)
        es = {**s, "intent_card": card, "behavior": beh}
        cat = ev.coarse_category(categories.get(t, []))
        opener = ev.initial_message(es, cat, set())
        out.setdefault(opener, [cat] + [str(card["hard_constraints"][0])] if s["scenario_type"] == "buying" else [cat])
        if beh.get("override"):
            o = beh["override"]
            out.setdefault(o["message"], [str(o["new_value"])])
        cons = [*map(str, card.get("hard_constraints", [])), *map(str, card.get("soft_preferences", []))]
        pre = {str(card["hard_constraints"][0])} if s["scenario_type"] == "buying" and card["hard_constraints"] else set()
        removals = [set(), {str(beh["override"]["new_value"])}] if beh.get("override") else [set()]
        for a in ATTRS:
            for rem in removals:
                pool = [c for c in cons if c not in pre | rem and ev.classify_constraint(c) == a]
                for i in range(0, max(len(pool), 1), 2):
                    chunk = pool[i:i + 2]
                    if chunk:
                        out.setdefault("For that, what matters is: " + "; ".join(chunk) + ".", chunk)
            out.setdefault(f"I don't have an additional preference for {a}.", [])
            out.setdefault(f"I don't have a preference for {a}; please use your judgment.", [])
    out.setdefault("Those options are not quite right yet. Ask me about one specific attribute.", [])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--styles", type=int, default=4)
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--limit", type=int, default=0, help="only the first N strings (smoke test)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", default="", help="batch id to fetch instead of creating")
    args = ap.parse_args()
    samples = ev.load_jsonl(ROOT / "data/public_set.jsonl")
    ids, cats, products = ev.catalog_index(ROOT / "data/catalog.jsonl")
    strings = simulator_strings(samples, products, cats)
    keys = list(strings)[:args.limit] if args.limit else list(strings)
    styles = list(STYLES)[:args.styles]
    print(f"{len(strings)} distinct simulator strings → {len(keys) * len(styles)} requests ({len(keys)} × {styles})", file=sys.stderr)
    if args.dry_run:
        return 0
    import anthropic
    client = anthropic.Anthropic()
    if args.resume:
        batch = client.messages.batches.retrieve(args.resume)
    else:
        reqs = []
        for i, text in enumerate(keys):
            for st in styles:
                reqs.append({"custom_id": f"{i}-{st}", "params": {
                    "model": args.model, "max_tokens": 300, "system": SYSTEM, "thinking": {"type": "disabled"},
                    "messages": [{"role": "user", "content": f"Voice: {STYLES[st]}.\n<message>\n{text}\n</message>"}]}})
        batch = client.messages.batches.create(requests=reqs)
        print(f"batch {batch.id} created ({len(reqs)} requests); polling…", file=sys.stderr)
    while batch.processing_status != "ended":
        time.sleep(15)
        batch = client.messages.batches.retrieve(batch.id)
        print(f"  {batch.processing_status} {batch.request_counts}", file=sys.stderr)
    kept = dropped = errors = 0
    with OUT.open("w", encoding="utf-8") as fh:
        for r in client.messages.batches.results(batch.id):
            i, st = r.custom_id.split("-", 1)
            text = keys[int(i)]
            if r.result.type != "succeeded":
                errors += 1
                continue
            para = "".join(b.text for b in r.result.message.content if b.type == "text").strip()
            if not para or any(fact not in para for fact in strings[text] if fact):
                dropped += 1
                continue
            fh.write(json.dumps({"text": text, "style": st, "paraphrase": para}, ensure_ascii=False) + "\n")
            kept += 1
    print(f"kept {kept}, dropped {dropped} (facts not verbatim), errors {errors} → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
