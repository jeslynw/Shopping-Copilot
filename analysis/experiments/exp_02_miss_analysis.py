"""§3b — Miss analysis: where does the target sit in the final-turn query for the V1 sessions that never hit?"""
from collections import Counter
import common as C

cat, S = C.Catalog(), C.load_samples()
res = C.run(C.V1(), cat, S, diag=True)
agent = res["_agent"]
buckets = Counter(); rows = []
for s, st, sample in zip(res["sessions"], agent.sessions, S):
    if s["hit"]:
        continue
    terms = st.diag[-1]["terms"]
    expr = " OR ".join(f'"{t}"' for t in terms)
    ranked = [a for a, _ in cat.fts(expr, 3000)] if terms else []
    t = sample["ground_truth"]["parent_asin"]
    r = ranked.index(t) + 1 if t in ranked else None
    b = "absent" if r is None else "11–50" if r <= 50 else "51–200" if r <= 200 else "201–3000"
    buckets[b] += 1
    rows.append((sample["sample_id"], sample["scenario_type"], sample["difficulty_bucket"], r, [c for c, _ in st.constraints][:3]))
C.header("§3b Miss analysis (V1 sessions that never hit)")
print(f"misses: {len(rows)}/200 · target rank in final-turn query: {dict(buckets)}")
print("by scenario:", dict(Counter(r[1] for r in rows)), "· by difficulty:", dict(Counter(r[2] for r in rows)))
print("\n| sample | scenario | difficulty | target rank | disclosed constraints (first 3) |\n|---|---|---|---|---|")
for sid, sc, d, r, cons in rows:
    print(f"| {sid} | {sc} | {d} | {r} | {'; '.join(c[:40] for c in cons)} |")
print("\nReading: the tail is reachable — a ranking problem inside the BM25 top-N, not a recall problem (→ §3c).")
C.save("exp_02_miss_analysis", [res], {"buckets": dict(buckets), "misses": [(a, b, c, d) for a, b, c, d, _ in rows]})
