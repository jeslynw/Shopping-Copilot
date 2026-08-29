
## §3g Popularity skew

rating_number median — catalog 12, targets 6846 (p25 986, p90 41917); 163/200 targets in the top-10 most-reviewed of their coarse category, 190/200 in the top-50, 70/200 are #1; 142/200 in the global top-1000; median peer set 182

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| pop tie-break, lexicographic (-nmatch, -catmatch, -rating_number) | 1.000 | 0.771 | 1.74 | **0.917** | 1.00 | 27.1/54.5 |
| blend bm25 − 0.5·log1p(pop) | 0.990 | 0.654 | 1.98 | **0.872** | 0.97 | 27.1/52.9 |
| blend bm25 − 1.0·log1p(pop) | 0.990 | 0.730 | 1.86 | **0.897** | 0.97 | 27.0/53.2 |
| blend bm25 − 2.0·log1p(pop) | 0.990 | 0.735 | 1.80 | **0.900** | 0.97 | 27.2/53.5 |
| blend bm25 − 4.0·log1p(pop) | 0.990 | 0.767 | 1.80 | **0.909** | 0.97 | 27.1/53.1 |
| pop tie-break, pool 1000 | 0.995 | 0.716 | 1.65 | **0.899** | 1.00 | 28.5/55.7 |
| PARAPHRASED, template extractor + pop | 0.720 | 0.362 | 4.26 | **0.603** | 0.80 | 32.4/56.8 |
| PARAPHRASED, hybrid extractor (template→clause fallback) + pop | 0.990 | 0.761 | 1.82 | **0.907** | 1.00 | 42.5/69.8 |
| clean, hybrid extractor + pop | 1.000 | 0.771 | 1.74 | **0.917** | 1.00 | 27.5/55.1 |
| no popularity (V6 control) | 0.975 | 0.643 | 2.58 | **0.849** | 0.97 | 28.8/53.5 |

pop per-scenario: boundary HR 1.000/MRR 0.76/MTTC 2.30 · browsing HR 1.000/MRR 0.72/MTTC 1.55 · buying HR 1.000/MRR 0.76/MTTC 1.16 · intent_override HR 1.000/MRR 0.94/MTTC 3.60
pop hit turns: {1: 115, 2: 43, 3: 23, 4: 18, 6: 1}
