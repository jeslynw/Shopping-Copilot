"""§3c — Constraint-satisfaction rerank on the BM25 top-N: V5 (#verbatim matches) → V6 (+category key) → V7 (+phrases) → V8 (pool 1000)."""
from dataclasses import replace
import common as C

cat, S = C.Catalog(), C.load_samples()
base = C.BASE()
variants = [
    replace(base, label="V1 control (+ boundary re-ask)"),
    replace(base, label="V5 rerank top-300 by #verbatim constraint matches", rerank=True),
    C.V6(),
    replace(C.V6(), label="V7 = V6 + constraints also as FTS5 phrase terms", phrase_terms=True),
    replace(C.V6(), label="V8 = V6 with pool 1000", pool=1000),
]
rows = [C.run(v, cat, S) for v in variants]
C.header("§3c Constraint-satisfaction rerank")
print(C.table(rows))
print(f"\nV7 per-scenario: {C.per_scenario(rows[3])}\nV7 hit turns: {rows[3]['hit_turns']}")
C.save("exp_03_constraint_rerank", rows)
