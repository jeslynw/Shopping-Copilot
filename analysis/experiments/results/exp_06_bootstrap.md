
## §3h Bootstrap (2,000 resamples of 200 sessions)

TechScore 0.917, 95% CI [0.903, 0.929], half-width 0.013 → on 800 private sessions expect ≈ ±0.007
rank at hit: {1: 132, 2: 23, 3: 14, 4: 13, 5: 5, 6: 3, 7: 5, 8: 3, 9: 1, 10: 1} → 68 sessions at rank 2–10 are the MRR headroom
Rule adopted: ship a change only if Δ ≥ +0.02 on the public set, or a robustness gain with no regression.
