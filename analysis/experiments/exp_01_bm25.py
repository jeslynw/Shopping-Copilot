"""§3 — Realistic policy simulation through the REAL evaluate(): V0 (≈starter) … V4 (`other` exploit)."""
from dataclasses import replace
import common as C

cat, S = C.Catalog(), C.load_samples()
variants = [
    C.V0(), C.V1(), C.V2(),
    replace(C.V2(), label="V3 = V2 + hard `categories:` filter from turn-1 phrase", cat_hard_filter=True),
    replace(C.V2(), label="V4 ref: ask `other` + catfilter (rule exploit, not to ship)", cat_hard_filter=True, ask_other=True),
]
rows = [C.run(v, cat, S) for v in variants]
C.header("§3 Realistic policy simulation (200 public sessions, real evaluator)")
print(C.table(rows))
v1 = rows[1]
print(f"\nV1 per-scenario: {C.per_scenario(v1)}")
print(f"V1 hit-turn distribution: {v1['hit_turns']}  → misses: {sum(1 for s in v1['sessions'] if not s['hit'])}/200")
C.save("exp_01_bm25", rows)
