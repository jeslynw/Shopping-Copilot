
## §3 Realistic policy simulation (200 public sessions, real evaluator)

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| V0 stateless, never asks | 0.115 | 0.069 | 9.89 | **0.100** | 0.10 | 0.0/14.9 |
| V1 accumulate + ask feature→material→color→… | 0.875 | 0.561 | 3.80 | **0.750** | 0.90 | 29.4/50.4 |
| V2 = V1 + boundary re-ask + re-ask while reply yields 2 | 0.885 | 0.568 | 3.81 | **0.757** | 0.90 | 28.8/50.3 |
| V3 = V2 + hard `categories:` filter from turn-1 phrase | 0.805 | 0.536 | 4.37 | **0.696** | 0.87 | 2.1/5.1 |
| V4 ref: ask `other` + catfilter (rule exploit, not to ship) | 0.800 | 0.537 | 4.09 | **0.699** | 0.83 | 2.0/5.0 |

V1 per-scenario: boundary HR 0.600/MRR 0.55/MTTC 7.30 · browsing HR 0.887/MRR 0.52/MTTC 3.65 · buying HR 0.887/MRR 0.55/MTTC 3.26 · intent_override HR 0.900/MRR 0.71/MTTC 4.47
V1 hit-turn distribution: {1: 20, 2: 62, 3: 57, 4: 25, 5: 4, 6: 3, 7: 2, 9: 2}  → misses: 25/200
