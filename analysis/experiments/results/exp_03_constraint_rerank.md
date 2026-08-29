
## §3c Constraint-satisfaction rerank

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| V1 control (+ boundary re-ask) | 0.880 | 0.562 | 3.71 | **0.754** | 0.90 | 30.0/51.0 |
| V5 rerank top-300 by #verbatim constraint matches | 0.950 | 0.631 | 2.90 | **0.826** | 0.97 | 28.2/53.2 |
| V6 rerank top-300 by #verbatim matches, category 2nd key | 0.975 | 0.643 | 2.58 | **0.849** | 0.97 | 27.3/50.6 |
| V7 = V6 + constraints also as FTS5 phrase terms | 0.975 | 0.647 | 2.58 | **0.850** | 0.97 | 28.7/51.7 |
| V8 = V6 with pool 1000 | 0.975 | 0.640 | 2.58 | **0.848** | 0.97 | 29.3/53.7 |

V7 per-scenario: boundary HR 0.900/MRR 0.60/MTTC 3.90 · browsing HR 0.988/MRR 0.62/MTTC 2.40 · buying HR 0.975/MRR 0.62/MTTC 2.09 · intent_override HR 0.967/MRR 0.82/MTTC 3.97
V7 hit turns: {1: 34, 2: 83, 3: 53, 4: 23, 5: 1, 6: 1}
