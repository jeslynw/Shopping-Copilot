
## §3j Cutoff rules (on the popularity variant, hybrid extractor)

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| R0 always top-10 (control) | 1.000 | 0.771 | 1.74 | **0.917** | 1.00 | 26.9/53.7 |
| R1 turn 1 & 0 constraints → top-3 | 1.000 | 0.800 | 1.80 | **0.924** | 1.00 | 26.7/53.9 |
| R2 turn 1 & 0 constraints → top-1 | 1.000 | 0.820 | 1.85 | **0.929** | 1.00 | 26.7/53.8 |
| R3 turn 1 & 0 constraints → [] (pure ask) | 1.000 | 0.820 | 1.98 | **0.926** | 1.00 | 26.6/54.1 |
| R4 turn ≤2 & <2 constraints → top-3 | 1.000 | 0.824 | 1.86 | **0.930** | 1.00 | 26.9/53.9 |
| R5 tier_size>10 & turn ≤2 → top-3 | 1.000 | 0.830 | 1.89 | **0.931** | 1.00 | 26.9/53.2 |
| R6 tier_size>10 & turn ≤3 → top-1 | 1.000 | 0.917 | 2.15 | **0.952** | 1.00 | 27.7/53.2 |
| R7 tier_size>30 & turn ≤2 → top-1 | 1.000 | 0.876 | 2.00 | **0.943** | 1.00 | 27.2/53.5 |
| R8 turn 1 → top-1 always | 1.000 | 0.861 | 1.98 | **0.939** | 1.00 | 27.0/52.8 |
| information-gated R6 (turn 1 or reply yielded a template constraint; no clause constraints) | 1.000 | 0.910 | 2.12 | **0.950** | 1.00 | 27.8/52.7 |
| information-gated R6, recognised exhausted/boundary reply counts as yielded | 1.000 | 0.917 | 2.15 | **0.952** | 1.00 | 27.8/53.1 |
| DEGENERATE always top-1 (metric artifact — disclosed, never shipped) | 0.900 | 0.900 | 2.93 | **0.881** | 0.93 | 32.0/55.5 |

R6 per-scenario: boundary HR 1.000/MRR 0.91/MTTC 2.70 · browsing HR 1.000/MRR 0.92/MTTC 2.06 · buying HR 1.000/MRR 0.90/MTTC 1.61 · intent_override HR 1.000/MRR 0.95/MTTC 3.63
R6 vs R0 per session: withheld a would-be hit 58 (delayed 58, lost 0); net-hurt 10 (worst -0.060), net-helped 48, mean Δ +0.0357

### Phantom-phrase injection (p = 0.10 per turn)

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| phantom p=0.10 (template-tagged) + R0 | 0.990 | 0.766 | 1.81 | **0.908** | 1.00 | 27.4/53.2 |
| phantom p=0.10 (template-tagged) + R6 | 1.000 | 0.912 | 2.15 | **0.951** | 1.00 | 27.9/52.7 |
| phantom p=0.10 (template-tagged) + gated | 1.000 | 0.897 | 2.12 | **0.946** | 1.00 | 28.0/52.9 |
| phantom p=0.10 (clause-tagged) + R0 | 0.990 | 0.766 | 1.81 | **0.908** | 1.00 | 27.5/53.1 |
| phantom p=0.10 (clause-tagged) + R6 | 1.000 | 0.912 | 2.15 | **0.951** | 1.00 | 27.7/52.8 |
| phantom p=0.10 (clause-tagged) + gated | 1.000 | 0.880 | 2.10 | **0.942** | 1.00 | 27.7/53.0 |

Reading: the cutoff multiplies extraction errors; the gate releases to a full shelf when a constraint is clause-tagged, but cannot see a phantom that passes as template — hence no LLM extractor in the scored path.
