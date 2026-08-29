# Paraphrase robustness — measured 29 Aug 2026 (dev harness, not the official score)

Fixture: `data/paraphrases.jsonl` — 1,910 paraphrases of 534 distinct simulator strings, 4 styles (terse / chatty / formal /
casual), generated once with `gpt-4.1-mini` via `tools/gen_paraphrases.py`; 322 outputs discarded for altering a product fact.
Evaluation: `tools/paraphrase_eval.py` swaps the simulator's strings in-process (evaluator unmodified), one style per session.

| configuration (200 public sessions) | HR@10 | MRR | MTTC | TechScore | override HR |
|---|---|---|---|---|---|
| clean — official simulator strings | 1.000 | 0.937 | 2.15 | **0.958** | 1.00 |
| paraphrased — deterministic clause extractor, before 29 Aug fixes | 0.975 | 0.782 | 2.17 | 0.899 | 1.00 |
| **paraphrased — deterministic clause extractor (shipped)** | 0.995 | 0.820 | 1.98 | **0.924** | 1.00 |
| paraphrased — LLM grounded extraction (`llm_extract`, gpt-4.1-mini), ablation | 0.995 | 0.800 | 1.96 | 0.918 | 1.00 |

What the diagnosis found and fixed (deterministically): request lead-ins glued to constraints ("Oh, for that one, what matters
is: Imported", "Key requirement is: spandex") and category phrases with "&"/"-" not being removed before clause splitting.
Category resolution was already 200/200 on paraphrased openers.

LLM layer status: `llm_polish` on when a key is present (message only; 83/83 turns identical ask/recs vs offline in a live
40-session run; p50 1.7 s/turn; ≈ $0.09 per 200 sessions). `llm_extract` and `llm_rerank` are ablation flags, off.
