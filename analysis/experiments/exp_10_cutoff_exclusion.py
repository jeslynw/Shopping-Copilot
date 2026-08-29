"""§3n — The exact shipped configuration and its neighbours; the final ladder; bootstrap CI; paraphrase headline."""
from dataclasses import replace
import common as C
from evaluator import local_evaluator as ev

cat, S = C.Catalog(), C.load_samples()
old = replace(C.POP(), extractor="hybrid")           # lower-only matcher, three fields
nz = replace(C.NORM(), extractor="hybrid")
ship = C.SHIPPED()
rows = [
    C.run(replace(old, label="old matcher (lower only), R6 cutoff, turn≥5 exclusion", cutoff="R6", exclusion="turn5"), cat, S),
    C.run(replace(nz, label="norm() matcher, R6 cutoff, turn≥5 exclusion", cutoff="R6", exclusion="turn5"), cat, S),
    C.run(replace(nz, label="norm() matcher, info-gated cutoff, turn≥5 exclusion", cutoff="gated", exclusion="turn5"), cat, S),
    C.run(replace(nz, label="norm() matcher, no cutoff, turn≥5 exclusion (conservative fallback)", exclusion="turn5"), cat, S),
    C.run(replace(nz, label="norm() matcher, info-gated cutoff, no exclusion", cutoff="gated"), cat, S),
    C.run(ship, cat, S),
    C.run(replace(ship, label="SHIPPED + gated2 (recognised exhausted/boundary reply counts as yielded)", cutoff="gated2"), cat, S),
    C.run(replace(ship, label="SHIPPED + query from extracted tokens (cap 32, DF-ordered) — P1 design", query_source="extracted", max_terms=32, df_order=True), cat, S),
    C.run(replace(ship, label="SHIPPED + extracted tokens + pool ∪ category members — P1 design", query_source="extracted", max_terms=32, df_order=True, pool_union_category=True), cat, S),
    C.run(replace(ship, label="SHIPPED + pool 1000", pool=1000), cat, S),
    C.run(replace(ship, label="DEGENERATE always top-1 + prev-turn exclusion (disclosed, not shipped)", cutoff="top1"), cat, S),
]
prow = [
    C.run(replace(ship, label="PARAPHRASED — SHIPPED"), cat, S, paraphrase=True),
    C.run(replace(ship, label="PARAPHRASED — SHIPPED + extracted tokens + pool ∪ category", query_source="extracted", max_terms=32, df_order=True, pool_union_category=True), cat, S, paraphrase=True),
    C.run(replace(ship, label="PARAPHRASED — SHIPPED with template-only extractor (what breaks)", extractor="template"), cat, S, paraphrase=True),
    C.run(replace(nz, label="PARAPHRASED — no cutoff, no exclusion (hybrid extractor)"), cat, S, paraphrase=True),
]
C.header("§3n Shipped configuration and neighbours (pool 300, popularity tie-break, parent_asin final key)")
print(C.table(rows)); print("\n### Paraphrased (synthetic in-process paraphraser — dev harness, not the official score)\n"); print(C.table(prow))
s = rows[5]; mean, lo, hi = C.bootstrap_ci(s["sessions"])
print(f"\nSHIPPED per-scenario: {C.per_scenario(s)}\nSHIPPED hit turns {s['hit_turns']} · rank at hit {s['rank_at_hit']}")
print(f"SHIPPED bootstrap 95% CI [{lo:.3f}, {hi:.3f}] (half-width {(hi-lo)/2:.3f})")
# final ladder
ladder = [("starter (kit baseline)", 0.10671), ("BM25 + ask (V1)", None), ("+ constraint rerank + category key (V6)", None),
          ("+ popularity tie-break", None), ("+ norm() six-field matcher", None), ("+ R6 cutoff", None), ("+ info-gated cutoff + previous-turn exclusion (SHIPPED)", s["recommended_technical_score"])]
lad = [C.run(c, cat, S, verbose=False) for c in (C.V1(), C.V6(), C.POP(), C.NORM(), C.R6())]
print("\n### Ladder\n\n| Layer | TechScore |\n|---|---|")
for (name, v), r in zip(ladder, [None] + lad + [None]):
    print(f"| {name} | {v if v is not None else r['recommended_technical_score']:.3f} |")
C.save("exp_10_cutoff_exclusion", rows + prow + lad, {"shipped_ci95": [lo, hi]})
