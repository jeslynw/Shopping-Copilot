
## §3i Self-match of the 200 targets' own constraints

- matcher lower-only over three fields: 765/800
- matcher norm() over three fields: 795/800
- matcher norm() over six fields: 800/800

| Variant | HR@10 | MRR | MTTC | TechScore | override HR | p50/p95 ms |
|---|---|---|---|---|---|---|
| POP control (lower-only matcher, three fields) | 1.000 | 0.771 | 1.74 | **0.917** | 1.00 | 27.1/54.1 |
| + norm() matcher, three fields | 1.000 | 0.771 | 1.74 | **0.917** | 1.00 | 26.8/54.8 |
| + norm() six-field matcher | 1.000 | 0.771 | 1.74 | **0.916** | 1.00 | 27.0/54.4 |

rank 2–10 hits: 68; #1 satisfies the same constraints+category and is more popular in 68/68. e.g. RITERA Plus Size Tops for Women Off the  (797) behind Sarin Mathews Womens Shirts Casual Tee S (19,378) · Hanes Womens Wireless Bra, Full-Coverage (30,628) behind Duufin 5 Pcs Lace Bralettes for Women Br (32,502) · Angel Barcelo Roomy Fashion Hobo Womens  (12,633) behind Women's Soft Faux Leather Tote Shoulder  (60,265)
→ MRR can only improve by not showing a wide tie: recommend fewer items when the top tier is broad (§3j).
