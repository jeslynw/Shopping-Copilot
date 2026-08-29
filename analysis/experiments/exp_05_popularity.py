"""§3g — Popularity: target skew, lexicographic tie-break vs blends, interaction with paraphrase / extractor."""
import statistics
from dataclasses import replace
import common as C

cat, S = C.Catalog(), C.load_samples()
targets = [s["ground_truth"]["parent_asin"] for s in S]
tp = sorted(cat.pop[t] for t in targets); cp = sorted(cat.pop.values())
in10 = in50 = rank1 = 0; peers = []
glob = sorted(cat.pop.values(), reverse=True)[999]
top1000 = sum(1 for t in targets if cat.pop[t] >= glob)
for t in targets:
    members = sorted(cat.members[cat.coarse[t]], key=lambda a: -cat.pop[a])
    r = members.index(t) + 1
    in10 += r <= 10; in50 += r <= 50; rank1 += r == 1; peers.append(len(members))
C.header("§3g Popularity skew")
print(f"rating_number median — catalog {statistics.median(cp):.0f}, targets {statistics.median(tp):.0f} "
      f"(p25 {tp[len(tp)//4]}, p90 {tp[int(len(tp)*0.9)]}); {in10}/200 targets in the top-10 most-reviewed of their coarse category, "
      f"{in50}/200 in the top-50, {rank1}/200 are #1; {top1000}/200 in the global top-1000; median peer set {statistics.median(peers):.0f}")
pop = C.POP()
rows = [
    C.run(replace(pop, label="pop tie-break, lexicographic (-nmatch, -catmatch, -rating_number)"), cat, S),
    *[C.run(replace(pop, label=f"blend bm25 − {w}·log1p(pop)", tiebreak="blend", blend_w=w), cat, S) for w in (0.5, 1.0, 2.0, 4.0)],
    C.run(replace(pop, label="pop tie-break, pool 1000", pool=1000), cat, S),
    C.run(replace(pop, label="PARAPHRASED, template extractor + pop"), cat, S, paraphrase=True),
    C.run(replace(pop, label="PARAPHRASED, hybrid extractor (template→clause fallback) + pop", extractor="hybrid"), cat, S, paraphrase=True),
    C.run(replace(pop, label="clean, hybrid extractor + pop", extractor="hybrid"), cat, S),
    C.run(replace(pop, label="no popularity (V6 control)", tiebreak="bm25"), cat, S),
]
print(); print(C.table(rows))
print(f"\npop per-scenario: {C.per_scenario(rows[0])}\npop hit turns: {rows[0]['hit_turns']}")
C.save("exp_05_popularity", rows, {"in_top10_of_category": in10, "in_top50": in50, "rank1": rank1, "global_top1000": top1000})
