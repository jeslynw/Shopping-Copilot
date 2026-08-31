import common as C

cat, S = C.Catalog(), C.load_samples()
res = C.run(C.POP(), cat, S)
mean, lo, hi = C.bootstrap_ci(res["sessions"], n=2000)
C.header("§3h Bootstrap (2,000 resamples of 200 sessions)")
print(f"TechScore {mean:.3f}, 95% CI [{lo:.3f}, {hi:.3f}], half-width {(hi-lo)/2:.3f} → on 800 private sessions expect ≈ ±{(hi-lo)/4:.3f}")
print(f"rank at hit: {res['rank_at_hit']} → {sum(v for k, v in res['rank_at_hit'].items() if k and k >= 2)} sessions at rank 2–10 are the MRR headroom")
print("Rule adopted: ship a change only if Δ ≥ +0.02 on the public set, or a robustness gain with no regression.")
C.save("exp_06_bootstrap", [res], {"ci95": [lo, hi]})
