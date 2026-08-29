
## §3f Tie-break, paraphrase, ask order

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| V6 exact-match, tie-break BM25 (control) | 0.975 | 0.643 | 2.58 | **0.849** | 0.97 | 27.3/50.7 |
| V6 exact-match, tie-break rating_number (popularity prior) | 1.000 | 0.771 | 1.74 | **0.917** | 1.00 | 26.3/53.0 |
| V6 soft-match (≥80% of constraint tokens) | 0.955 | 0.601 | 2.79 | **0.822** | 0.93 | 30.1/54.6 |
| PARAPHRASED msgs, template extractor | 0.585 | 0.364 | 5.89 | **0.504** | 0.67 | 30.8/46.4 |
| PARAPHRASED msgs, clause extractor + exact match | 0.970 | 0.634 | 2.62 | **0.843** | 0.97 | 39.4/66.0 |
| PARAPHRASED msgs, clause extractor + soft match | 0.955 | 0.595 | 2.80 | **0.820** | 0.97 | 39.8/65.3 |
| clean msgs, clause extractor + soft match (robustness tax) | 0.960 | 0.606 | 2.81 | **0.826** | 0.93 | 35.1/62.1 |
| clean msgs, clause extractor + exact match | 0.970 | 0.640 | 2.69 | **0.843** | 0.97 | 35.0/63.3 |
| ask order material→feature→color | 0.975 | 0.652 | 2.65 | **0.850** | 0.97 | 25.8/51.4 |
| ask order feature→color→material | 0.975 | 0.626 | 2.75 | **0.840** | 0.97 | 28.9/51.0 |
| ask order color→feature→material | 0.975 | 0.615 | 3.12 | **0.830** | 0.97 | 28.4/51.1 |

Paraphrase rows use the synthetic in-process paraphraser (common.Paraphraser) — simpler than an LLM's; treat as optimistic.
