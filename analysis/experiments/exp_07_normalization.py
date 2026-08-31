from dataclasses import replace
import common as C
from evaluator import local_evaluator as ev

cat, S = C.Catalog(), C.load_samples()
# self-match: do the targets' own constraints match their own text?
def self_match(fields, normalize):
    texts = cat.texts(fields, normalize); total = ok = 0
    for s in S:
        t = s["ground_truth"]["parent_asin"]; card, _ = ev.materialize_hidden_fields(s, cat.products)
        cfg = C.Config(rerank=True, norm_match=normalize, match_fields=fields)
        st = C.State(constraints=[(c, "template") for c in dict.fromkeys(card["hard_constraints"] + card["soft_preferences"])])
        for m in C.ExpAgent(cfg, cat)._matchers(st):
            total += 1; ok += bool(m(texts[t], t))
    return ok, total
C.header("§3i Self-match of the 200 targets' own constraints")
for fields, nz in [("three", False), ("three", True), ("six", True)]:
    ok, total = self_match(fields, nz)
    print(f"- matcher {'norm()' if nz else 'lower-only'} over {fields} fields: {ok}/{total}")
rows = [C.run(replace(C.POP(), label="POP control (lower-only matcher, three fields)"), cat, S),
        C.run(replace(C.POP(), label="+ norm() matcher, three fields", norm_match=True), cat, S),
        C.run(C.NORM(), cat, S, diag=True)]
print(); print(C.table(rows))
# why not #1: for hits at rank 2–10, does the #1 item satisfy the same constraints & category and simply have more reviews?
res = rows[2]; agent = res["_agent"]; same = 0; n = 0; examples = []
probe = C.ExpAgent(C.NORM(), cat); texts = cat.texts("six", True)
for s, st, sample in zip(res["sessions"], agent.sessions, S):
    if not s["hit"] or s["best_rank"] == 1:
        continue
    n += 1; t = sample["ground_truth"]["parent_asin"]; top1 = st.diag[-1]["top1"]
    ms = probe._matchers(st)
    nt = sum(m(texts[t], t) for m in ms); n1 = sum(m(texts[top1], top1) for m in ms)
    if nt == n1 and (cat.coarse[top1] in st.cat_set) == (cat.coarse[t] in st.cat_set) and cat.pop[top1] >= cat.pop[t]:
        same += 1
        if len(examples) < 3:
            examples.append(f"{cat.products[t]['title'][:40]} ({cat.pop[t]:,}) behind {cat.products[top1]['title'][:40]} ({cat.pop[top1]:,})")
print(f"\nrank 2–10 hits: {n}; #1 satisfies the same constraints+category and is more popular in {same}/{n}. e.g. " + " · ".join(examples))
print("→ MRR can only improve by not showing a wide tie: recommend fewer items when the top tier is broad (§3j).")
C.save("exp_07_normalization", rows, {"same_tier_more_popular": [same, n]})
