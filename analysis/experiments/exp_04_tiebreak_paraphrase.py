from dataclasses import replace
import common as C

cat, S = C.Catalog(), C.load_samples()
v6 = C.V6()
rows = [
    C.run(replace(v6, label="V6 exact-match, tie-break BM25 (control)"), cat, S),
    C.run(replace(v6, label="V6 exact-match, tie-break rating_number (popularity prior)", tiebreak="popularity"), cat, S),
    C.run(replace(v6, label="V6 soft-match (≥80% of constraint tokens)", match_mode="soft"), cat, S),
    C.run(replace(v6, label="PARAPHRASED msgs, template extractor"), cat, S, paraphrase=True),
    C.run(replace(v6, label="PARAPHRASED msgs, clause extractor + exact match", extractor="clause"), cat, S, paraphrase=True),
    C.run(replace(v6, label="PARAPHRASED msgs, clause extractor + soft match", extractor="clause", match_mode="soft"), cat, S, paraphrase=True),
    C.run(replace(v6, label="clean msgs, clause extractor + soft match (robustness tax)", extractor="clause", match_mode="soft"), cat, S),
    C.run(replace(v6, label="clean msgs, clause extractor + exact match", extractor="clause"), cat, S),
]
for order in [("material", "feature", "color"), ("feature", "color", "material"), ("color", "feature", "material")]:
    full = order + tuple(a for a in C.ATTRS if a not in order)
    rows.append(C.run(replace(v6, label=f"ask order {'→'.join(order)}", ask_order=full), cat, S))
C.header("§3f Tie-break, paraphrase, ask order")
print(C.table(rows))
print("\nParaphrase rows use the synthetic in-process paraphraser (common.Paraphraser) — simpler than an LLM's; treat as optimistic.")
C.save("exp_04_tiebreak_paraphrase", rows)
