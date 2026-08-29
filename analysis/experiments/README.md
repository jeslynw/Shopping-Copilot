# analysis/experiments — reference implementation of docs/PLAN.md §3

`common.py` is a single configurable agent (`Config` = one flag per layer) plus a runner that
calls the **real, unmodified** `evaluator/local_evaluator.py::evaluate()` on the 200 public sessions.
Each `exp_NN_*.py` maps to a §3 subsection and prints a markdown table (saved to `results/`).

| script | PLAN.md | what it measures |
|---|---|---|
| `exp_01_bm25.py` | §3 | V0 stateless → V1 accumulate+ask → V2 re-ask → V3 hard category filter → V4 `other` exploit |
| `exp_02_miss_analysis.py` | §3b | rank of the target in the final-turn query for V1 misses |
| `exp_03_constraint_rerank.py` | §3c | verbatim constraint-satisfaction rerank, category sort key, phrase terms, pool size |
| `exp_04_tiebreak_paraphrase.py` | §3f | popularity tie-break, soft vs exact match, paraphrase × extractor, ask order |
| `exp_05_popularity.py` | §3g | target skew statistics, lexicographic vs blend, paraphrase × popularity |
| `exp_06_bootstrap.py` | §3h | bootstrap CI, rank-at-hit distribution |
| `exp_07_normalization.py` | §3i | `norm()` matcher, self-match test, why-not-#1 |
| `exp_08_cutoff.py` | §3j | R0…R8, information-gated, degenerate top-1, phantom injection, per-session accounting |
| `exp_09_exclusion.py` | §3k | naive / override-safe / turn≥5 / previous-turn-only exclusion, inverse detection test |
| `exp_10_cutoff_exclusion.py` | §3n | shipped configuration and neighbours, paraphrase headline, ladder, CI |

Run one: `.venv/bin/python analysis/experiments/exp_10_cutoff_exclusion.py` (from the repo root or anywhere).
Run all: `analysis/experiments/run_all.sh`. `common.Paraphraser` is the synthetic paraphrase harness
(monkeypatches the simulator strings in-process; the evaluator file is never edited).

These scripts keep per-product text in Python for speed of iteration; the shipped `copilot/` package
fetches pool text from FTS5 instead (memory-lean, see docs/PLAN.md §5). `tools/ablate.py` is built on them.
