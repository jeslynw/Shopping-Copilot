
## §3k Seen-set exclusion

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| R0 top-10 (control) | 1.000 | 0.771 | 1.74 | **0.916** | 1.00 | 27.5/54.1 |
| R0 + naive exclusion (cumulative, always) | 0.855 | 0.656 | 2.79 | **0.788** | 0.03 | 35.8/67.1 |
| R0 + override-safe exclusion (detection-gated) | 1.000 | 0.791 | 1.73 | **0.923** | 1.00 | 27.0/54.7 |
| R6 cutoff (control) | 1.000 | 0.925 | 2.15 | **0.955** | 1.00 | 28.4/53.8 |
| R6 + override-safe exclusion (detection-gated) — not shipped | 1.000 | 0.954 | 2.10 | **0.964** | 1.00 | 28.1/54.0 |
| R6 + cumulative exclusion from turn ≥ 5 (turns ≥ 4 only) | 1.000 | 0.929 | 2.14 | **0.956** | 1.00 | 28.5/53.8 |
| R6 + previous-turn-only exclusion (detection-free, self-healing) | 1.000 | 0.948 | 2.18 | **0.961** | 1.00 | 28.4/56.2 |
| R6 + override-safe exclusion, detector forced to 'buying' (paraphrase failure simulation) | 0.865 | 0.823 | 3.09 | **0.837** | 0.10 | 34.2/67.1 |
| R6 + previous-turn-only exclusion, detector forced to 'buying' (no dependency) | 1.000 | 0.948 | 2.18 | **0.961** | 1.00 | 28.7/56.4 |

Reading: any cumulative set whose detection fails deletes the target in override sessions (pre-override hits don't count); previous-turn-only exclusion needs no detection and is back to a full shelf the next turn.
