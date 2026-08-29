
## §3n Shipped configuration and neighbours (pool 300, popularity tie-break, parent_asin final key)

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| old matcher (lower only), R6 cutoff, turn≥5 exclusion | 1.000 | 0.922 | 2.15 | **0.954** | 1.00 | 28.1/53.4 |
| norm() matcher, R6 cutoff, turn≥5 exclusion | 1.000 | 0.929 | 2.14 | **0.956** | 1.00 | 28.4/53.7 |
| norm() matcher, info-gated cutoff, turn≥5 exclusion | 1.000 | 0.922 | 2.12 | **0.954** | 1.00 | 28.6/54.1 |
| norm() matcher, no cutoff, turn≥5 exclusion (conservative fallback) | 1.000 | 0.775 | 1.73 | **0.918** | 1.00 | 27.0/54.2 |
| norm() matcher, info-gated cutoff, no exclusion | 1.000 | 0.918 | 2.12 | **0.953** | 1.00 | 28.0/53.4 |
| SHIPPED: norm() + info-gated cutoff + previous-turn-only exclusion | 1.000 | 0.937 | 2.15 | **0.958** | 1.00 | 28.1/55.7 |
| SHIPPED + gated2 (recognised exhausted/boundary reply counts as yielded) | 1.000 | 0.948 | 2.18 | **0.961** | 1.00 | 28.4/56.0 |
| SHIPPED + query from extracted tokens (cap 32, DF-ordered) — P1 design | 1.000 | 0.937 | 2.15 | **0.958** | 1.00 | 27.8/53.9 |
| SHIPPED + extracted tokens + pool ∪ category members — P1 design | 1.000 | 0.925 | 2.13 | **0.955** | 1.00 | 28.2/55.3 |
| SHIPPED + pool 1000 | 1.000 | 0.933 | 2.15 | **0.957** | 1.00 | 30.9/60.0 |
| DEGENERATE always top-1 + prev-turn exclusion (disclosed, not shipped) | 0.950 | 0.950 | 2.60 | **0.928** | 0.97 | 30.8/58.5 |

### Paraphrased (synthetic in-process paraphraser — dev harness, not the official score)

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| PARAPHRASED — SHIPPED | 0.995 | 0.793 | 1.85 | **0.918** | 1.00 | 42.7/70.5 |
| PARAPHRASED — SHIPPED + extracted tokens + pool ∪ category | 1.000 | 0.724 | 1.68 | **0.904** | 1.00 | 41.2/69.9 |
| PARAPHRASED — SHIPPED with template-only extractor (what breaks) | 0.770 | 0.386 | 3.92 | **0.642** | 0.83 | 33.4/59.3 |
| PARAPHRASED — no cutoff, no exclusion (hybrid extractor) | 0.995 | 0.773 | 1.79 | **0.914** | 1.00 | 42.1/70.3 |

SHIPPED per-scenario: boundary HR 1.000/MRR 0.78/MTTC 2.30 · browsing HR 1.000/MRR 0.95/MTTC 1.98 · buying HR 1.000/MRR 0.93/MTTC 1.57 · intent_override HR 1.000/MRR 0.97/MTTC 4.13
SHIPPED hit turns {1: 70, 2: 69, 3: 35, 4: 12, 5: 14} · rank at hit {1: 180, 2: 9, 3: 5, 4: 3, 5: 1, 6: 1, 8: 1}
SHIPPED bootstrap 95% CI [0.948, 0.967] (half-width 0.009)

### Ladder

| Layer | TechScore |
|---|---|
| starter (kit baseline) | 0.107 |
| BM25 + ask (V1) | 0.750 |
| + constraint rerank + category key (V6) | 0.849 |
| + popularity tie-break | 0.917 |
| + norm() six-field matcher | 0.916 |
| + R6 cutoff | 0.955 |
| + info-gated cutoff + previous-turn exclusion (SHIPPED) | 0.958 |
