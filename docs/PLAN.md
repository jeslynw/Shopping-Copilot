# Shopping Copilot — TikTok TechJam 2026 PS4 Build Plan

> Status: FINAL. Measurements complete (§3), decisions taken (§4), all 6 adversarial lenses merged (§7b); 8 of 10 refuter verdicts received — 4 "already superseded by the plan", 1 confirmed (memory, slim design measured 348 MB), 3 not read; the synthesizer was stopped for token budget. Read §4 → §6 → §10 to execute; §3 is the evidence; §7b is the stress test.

## 1. Context

Building the PS4 "Shopping Copilot" agent for TikTok TechJam 2026. A multi-turn agent must surface a hidden target product (exact `parent_asin`) from a frozen 50k-product Amazon Clothing/Shoes/Jewelry catalog within 10 turns, against a **deterministic rule-based customer simulator**. Scored by `TechnicalScore = 0.5·HitRate@10 + 0.3·MRR + 0.2·Efficiency` on 800 private sessions, which then feeds the 35% "Technical Execution" judging criterion; the other 65% is judged on writeup, demo, innovation, feasibility.

Build window: **29 Aug 12:00 → 1 Sep 12:00** (72h). Today is 28 Aug — this is the planning day. Shipped baseline: TechnicalScore **0.107**.

Session memory lives in the Obsidian vault `shopping_copilot_tiktok_hackathon/` — notes `09 — Evaluator Mechanics (Verified)` and `10 — Catalog Profile & Oracle Ceiling` are the ground truth; earlier notes carry supersede banners.

## 2. Verified facts that drive every decision

**Evaluator (`evaluator/local_evaluator.py`, read in full):**
- Agent gets `reset(session_id, user_profile)` then up to 10× `respond(session_id, user_message, turn, top_k=10)` → `{message, ask_attribute, recommendations, usage}`.
- **Every turn is scored AND asked** — recommendations are checked for the target every turn, then the simulator replies based on `ask_attribute`. No ask-vs-show tradeoff exists. Always do both.
- `customer_reply()` is a pure rule function. `ask_attribute=None` → zero information ("Those options are not quite right yet…"). Each ask reveals ≤2 undisclosed constraints whose `classify_constraint()` bucket matches.
- Intent card per target: `hard_constraints = cleaned[:2]`, `soft_preferences = cleaned[2:4]` — ≤4 strings, lifted **verbatim** from the target's `features`/`details`/material-regex/color-regex/price.
- `classify_constraint()` only ever returns `budget, material, color, size, style, use_case, feature`. **`category` and `brand` can never match → dead asks.**
- Turn-1 message reveals `coarse_category()` = last two non-generic category-path parts of the *target* (e.g. "Earrings Hoop") → a free, near-exact structured cue.
- Scenarios (fixed mix, same on private): buying 40% (1 hard constraint pre-disclosed), browsing 40% (nothing disclosed), intent_override 15% (old=soft pref, new=hard constraint of the **same** target; fires turn 3|4, seeded by sample_id; **pre-override hits don't count**), boundary 5% (first ask returns "no preference… use your judgment" once).
- Override "ignore my earlier preference" is a **trap** — both values describe the same product. Accumulate everything, erase nothing.
- Miss = turn 11 for MTTC. Exceptions/invalid output/timeouts may count as a miss.

**Catalog (`catalog.jsonl.gz`, SHA256 verified, profiled):**
- 100%: `parent_asin, title, categories, average_rating, rating_number`. 96.7% `details`, 89.6% `features`, 52% `description`.
- **`price` 79% null. `details.Size` 1.9%, `Color` 4.9%, `Material` 4.1%, `Brand` 4.7%, `Style` 3.5%.** Structured-predicate filtering is unbuildable except on `categories` (100%) and `details.Department` (87%).
- Ask payoff (P(session has ≥1 constraint of type)): **feature 95.8% · material 56.8% · color 42.5%** · style 16.7% · size 7.6% · use_case 1.9% · budget 0.6% · category/brand 0%.
- Oracle (all 4 constraints + coarse category, plain BM25): HitRate@10 **0.775**, MRR **0.625** → TechnicalScore ≈ **0.70**. Median rank when hit = 1, but every miss sits at rank 11–441 of the same query (§3b) → the problem is **ranking inside the BM25 top-500**, solved deterministically by constraint-satisfaction + popularity (§3c–3g), not by dense retrieval.

**Rules (`docs/submission_rules.md`, `docs/competition_specification.md`):**
- **"For official final scoring, organizer policy may disable network access."** → core must be fully offline; any LLM is optional with documented fallback.
- **"If natural-language paraphrasing is added by the organizer, it cannot decide correctness."** → private simulator messages may be paraphrased. Extraction must not depend on exact templates.
- Organizer may impose **CPU, memory, timeout** limits. Python 3.10+ recommended; starter is stdlib-only.
- Submission: `agent.py` exporting `Agent`, helpers, `requirements.txt`, README with one-command run, report disclosing latency/tokens/cost, offline-capability statement. No evaluator modification, no secrets, no undeclared external services for final scoring.
- Deliverables also: Devpost writeup, public GitHub repo, public YouTube demo of one multi-turn session.
- Innovation directions the spec names: Buying/Browsing routing, hybrid retrieval, semantic reranking, structured constraint state + override handling, **adaptive clarification and question-value estimation**, safe profile use, **failure detection / strategy switching / low latency / low token cost**, **transparent recommendation explanations**.

**Environment:** macOS, Apple M3 Pro 11-core, 18 GB. System Python **3.14** (too new for torch/ST wheels) — `uv` available → pin 3.11. SQLite 3.50 with **FTS5** (stdlib, fast, column-weighted BM25 — what the starter uses). `gh` authenticated. Project dir `~/Documents/Projects/shopping_copilot/` holds `data/catalog.jsonl.gz` + `analysis/{local_evaluator.py, public_set.jsonl}`; not a git repo yet.

## 3. Realistic policy simulation — run through the REAL `evaluate()` on the 200 public sessions

In-memory FTS5 index (build 1.0s), starter column weights `title 6, categories 4, features 2.5, details 2.5, store 1.5, description 1`, OR-query over ≤40 accumulated unique terms (template boilerplate stop-worded).

| Variant | HR@10 | MRR | MTTC | **TechScore** | latency p50/p95 |
|---|---|---|---|---|---|
| V0 stateless, never asks (≈ starter) | 0.115 | 0.066 | 9.89 | **0.099** | 0/6 ms |
| **V1 accumulate all msgs + ask feature→material→color→style→size→use_case→budget** | **0.875** | **0.561** | **3.72** | **0.752** | 17/36 ms |
| V2 = V1 + re-ask attr while reply yields 2 items | 0.880 | 0.561 | 3.83 | 0.751 | 16/34 ms |
| V3 = V2 + hard `categories:` filter from turn-1 phrase | 0.850 | 0.556 | 4.14 | 0.729 | 2/6 ms |
| V4 ref: ask `other` + catfilter (rule-exploit, not to ship) | 0.835 | 0.571 | 3.87 | 0.731 | 2/6 ms |

V1 per-scenario: buying HR .887/MTTC 3.26 · browsing .875/3.67 · override .900/4.47 · boundary .700/5.50. Hit-turn distribution V1: `{1:20, 2:62, 3:60, 4:25, 5:4, 6:3, 7:1}` → 81% of hits by turn 3.

**Readings:**
- A ~150-line stdlib agent already reaches **0.75 ≈ 7× baseline**. This is the floor to ship on day 1, not the target.
- Re-asking is neutral. Hard category filter **hurts** (buying HR .887→.812) — root cause not diagnosed; superseded by using category as a *sort key* (§3c, +.013), so the hard filter is a "not shipped" ablation row only.
- The `other` exploit is *not* better than honest asking (0.731 vs 0.752) — no temptation there.
- **12.5% of sessions never hit** (25/200) at this stage → analysed in §3b; fully recovered by §3k (HR .995).
- V1 boundary HR is only .700 — the one-shot "no preference" reply wastes the ask; V2's re-ask policy fixes it (.900). Take V2's boundary handling, V1's everything else.

### 3b. Miss analysis (the 25 V1 sessions that never hit)

- **Target rank in the final-turn query: 11–50 → 14 sessions · 51–200 → 7 · 201–3000 → 4 · absent → 0.** No duplicate titles. **The tail is entirely reachable — it is a ranking problem inside the top ~500, not a recall problem.**
- Cause: disclosed constraints are generic low-IDF strings (`Imported`, `100% Cotton`, `Rubber sole`, `Zipper closure`, `Machine Wash`, `leather`, `color: black`) shared by thousands of same-category items. The target's discriminating title words (brand, product name) are **never revealed** by the simulator.
- Misses by scenario: browsing 10, buying 9, override 3, boundary 3. By difficulty: easy 9, medium 13, hard 3 — "easy" misses exist, so difficulty bucket ≠ our difficulty.
- **Exploitable structure:** `intent_card()` lifts constraints *verbatim* from the target's `features`/`details`. A candidate containing all disclosed strings as exact substrings is almost certainly the target. → Constraint-satisfaction rerank (count verbatim matches over `searchable_text`) on the BM25 top-N. Measured in §3c.
- `intent_card` ordering: `[material_regex, "color: X", *features, *details, "budget around $price"]` → hard = first 2 (material + color when both regex-match), soft = next 2 (usually `features[0..1]`). `details` strings and price almost never make the top 4 — explains budget 0.6%.

### 3c. Constraint-satisfaction rerank — measured

Retrieve BM25 top-N, then sort by `(-#disclosed_constraints_found_verbatim_in_searchable_text, -category_match, bm25_rank)`.

| Variant | HR@10 | MRR | MTTC | **TechScore** | p50/p95 |
|---|---|---|---|---|---|
| V1 control | .875 | .561 | 3.72 | 0.752 | 16/33 ms |
| V5 rerank top-300 by #verbatim constraint matches | .955 | .634 | 2.88 | 0.830 | 16/39 |
| **V6 = V5 + coarse-category match as 2nd sort key** | **.970** | .642 | 2.72 | **0.843** | 16/39 |
| V7 = V6 + constraints also as FTS5 phrase terms | .970 | **.651** | 2.71 | **0.846** | 17/44 |
| V8 = V6 with pool 1000 | .970 | .639 | 2.72 | 0.842 | 20/43 |

V7 per-scenario: buying HR .963/MTTC 2.27 · browsing .988/2.51 · override .967/3.97 · boundary .900/3.90. Hit turns `{1:27, 2:82, 3:59, 4:24, 5:1, 6:1}` → 84% of hits by turn 3.

**Readings:** (1) The centerpiece is a ~30-line deterministic reranker; it lifts HR .875→.970 and cuts MTTC by a full turn. (2) Category works as a *sort key* (+.013) where it failed as a hard filter (−.023). (3) Pool 300 is enough. (4) Remaining headroom is MRR (.65) — target is in top-10 but not #1 — and robustness to paraphrase, since verbatim matching is template-dependent. Measured next in §3f.

### 3f. Tie-break, paraphrase, ask order, memory — measured

| Experiment | HR@10 | MRR | MTTC | **TechScore** |
|---|---|---|---|---|
| V6 exact-match, tie-break BM25 (control; stopwords slightly changed vs §3c) | .960 | .644 | 2.79 | 0.837 |
| **V6 exact-match, tie-break `rating_number` (popularity prior)** | **.995** | **.741** | **1.78** | **0.904** |
| V6 soft-match (≥80% of constraint tokens) | .940 | .605 | 3.03 | 0.811 |
| PARAPHRASED msgs, template extractor | .855 | .546 | 3.88 | **0.734** ← breaks |
| PARAPHRASED msgs, clause extractor + exact match | .915 | .611 | 3.23 | 0.796 |
| PARAPHRASED msgs, clause extractor + soft match | .890 | .566 | 3.52 | 0.764 |
| clean msgs, clause extractor + soft match (robustness tax) | .940 | .608 | 3.03 | 0.812 |
| ask order material→feature→color | .955 | .642 | 2.88 | 0.832 |
| ask order feature→color→material | .960 | .614 | 2.93 | 0.826 |
| ask order color→feature→material | .950 | .582 | 3.37 | 0.802 |

RSS with catalog dicts + FTS5 in memory: **0.52 GB**.

**Readings:**
- **Popularity prior is the second big lever (+0.07).** Sessions are sampled from real purchases (leave-last-out), so heavily-reviewed items are disproportionately the targets; among candidates that satisfy the same disclosed constraints, prefer the most-reviewed. Uses only a participant-visible field; it is what every real shop does. Skew check + blend weights in §3g.
- **Paraphrase is a real ~0.10 risk** for template-dependent extraction (synthetic test — my paraphrase templates are simpler than an LLM's would be, so treat 0.734 as optimistic). Clause-based extraction recovers most of it. **Exact substring matching beats soft matching in both regimes** — generic tokens make soft matching produce false positives. → Hybrid extractor: template-first, clause fallback; exact matching; build a paraphrase test harness (LLM-generated paraphrases during dev) to measure honestly.
- Ask order `feature→material→color→style→size→use_case→budget` confirmed best of 5 tested. Re-asking `feature` after 3 asks is neutral.

### 3g. Popularity: skew, blend, and paraphrase interaction — measured

**Target skew is extreme:** `rating_number` median — catalog **12**, targets **6,614** (p25 863, p90 40,492). **163/200 targets are among the 10 most-reviewed items of their own coarse category; 190/200 in the top 50.** Median coarse-category peer set = 182 products. This is the leave-last-out-on-5-core sampling showing through; the spec says the private split is sampled the same way.

| Variant | HR@10 | MRR | MTTC | **TechScore** |
|---|---|---|---|---|
| **pop tie-break, lexicographic `(-nmatch, -catmatch, -rating_number)`** | **.995** | **.741** | **1.78** | **0.904** |
| blend `bm25 − 0.5·log1p(pop)` | .985 | .631 | 2.07 | 0.861 |
| blend `bm25 − 1.0·log1p(pop)` | .985 | .698 | 1.91 | 0.884 |
| blend `bm25 − 2.0·log1p(pop)` | .985 | .711 | 1.85 | 0.889 |
| blend `bm25 − 4.0·log1p(pop)` | .985 | .735 | 1.84 | 0.896 |
| pop tie-break, pool 1000 | .990 | .690 | 1.70 | 0.888 |
| PARAPHRASED, template extractor + pop | .760 | .421 | 4.04 | **0.646** ← worst case |
| **PARAPHRASED, hybrid extractor (template→clause fallback) + pop** | .940 | .622 | 2.44 | **0.828** |
| clean, hybrid extractor + pop | .995 | .741 | 1.78 | 0.904 |

Pop-variant per-scenario: buying HR .988/MTTC 1.29 · browsing 1.000/1.54 · override 1.000/3.60 · boundary 1.000/2.30. Hit turns `{1:114, 2:44, 3:22, 4:18, 6:1}` — **57% of sessions solved at turn 1** from coarse category + popularity (+ the one buying constraint).

**Readings:**
- Lexicographic popularity beats every blend; heavy blend (w=4) is within noise (0.896) and is the safer *hedge* if the private skew were weaker. Decide at build time with bootstrap CIs.
- **Under paraphrase, the template extractor + popularity is the worst combination (0.646)** — when category/constraint extraction fails, popularity ranks the wrong category's bestsellers confidently. The hybrid extractor recovers to 0.828. Category extraction must also be template-free: match turn-1 tokens against the finite vocabulary of `coarse_category()` values computed over the catalog (a few hundred phrases).
- Judge framing: "bestsellers in the stated category, filtered by every constraint the customer states, verbatim" is what a real shop does; the ablation ladder BM25 0.75 → +constraint rerank 0.84 → +popularity 0.90 is honest and each rung is a one-line idea.

### 3h. Statistical noise & MRR headroom — measured

- **Bootstrap (2,000 resamples) of the V-final score on 200 sessions: 0.904, 95% CI [0.887, 0.919], half-width 0.016.** On 800 private sessions expect ≈ ±0.008. → **Adopt rule for every experiment: Δ ≥ +0.02 on the public set, or a robustness gain with no regression. Anything smaller is noise; log it as an ablation row, don't ship it.**
- Rank at hit (V-final): `{1:124, 2:25, 3:13, 4:16, 5:7, 6:4, 7:4, 8:2, 9:2, 10:2}` → 75 sessions at rank 2–10 are the MRR headroom (max +0.08 TechScore if all became #1).
- Constructed constraints: `intent_card` fabricates `"color: {x}"` and `"budget around ${price}"` — these are not verbatim product text, so exact substring matching under-counts the target's own constraints. Normalization experiment in §3i.

### 3i. Constraint normalization & why-not-#1 — measured

- Normalizing `color: x` → token match and `budget around $p` → ±20% price window: **0.904 → 0.904, no change.** Hits happen at turn 1–2, before color/budget are ever disclosed. Keep as a cheap correctness fix, not a lever.
- **Every one of the 75 rank-2–10 hits has the same cause: the #1 item satisfies the same constraints and category and is simply more popular.** Examples: target Hanes V-neck (16.5k reviews) behind Fruit of the Loom crew (100k); Travelambo wallet (67k) behind Buffway (94k). Since a hit *ends the session*, MRR can only improve by **not showing a wide tie** — recommend fewer items when the top tier is broad and ask one more question instead. This is literally pillar II's "retrieval cutoff on over-generality". Measured in §3j.

### 3j. Confidence-gated cutoff policy — measured

`tier_size` = number of candidates sharing the top `(n_constraints, cat_match)` tier — a direct uncertainty estimate. Rule returns the top-*n* only when uncertain.

| Rule | HR@10 | MRR | MTTC | **TechScore** |
|---|---|---|---|---|
| R0 always top-10 (control) | .995 | .741 | 1.78 | 0.904 |
| R1 turn 1 & 0 constraints → top-3 | .995 | .776 | 1.85 | 0.913 |
| R2 turn 1 & 0 constraints → top-1 | .995 | .790 | 1.91 | 0.916 |
| R3 turn 1 & 0 constraints → [] (pure ask) | .995 | .790 | 2.02 | 0.914 |
| R4 turn ≤2 & <2 constraints → top-3 | .995 | .805 | 1.92 | 0.920 |
| R5 tier_size>10 & turn ≤2 → top-3 (conservative) | .995 | .824 | 1.98 | 0.925 |
| **R6 tier_size>10 & turn ≤3 → top-1** | **.995** | **.915** | 2.27 | **0.947** |
| R7 tier_size>30 & turn ≤2 → top-1 | .995 | .852 | 2.08 | 0.932 |
| R8 turn 1 → top-1 always | .995 | .834 | 2.03 | 0.927 |

R6 per-scenario MRR: buying .91 · browsing .91 · override .94 · boundary .91 (all ≥ .91 vs .69–.92 before).

**Readings:** (1) HR is untouched by every rule *on clean extraction* — the cutoff never loses a session there. (2) R6 trades 0.5 turn of MTTC (−0.010) for +0.174 MRR (+0.052): net **+0.043, ~2.7× the noise half-width.** (3) This is the brief's pillar II "Proactive Guidance: retrieval cutoff on Over-Generality" made concrete: tier width is the over-generality signal. (4) **Perception risk:** judges may read "return 1 item when unsure" as metric gaming. Framing: *"when 40 bestsellers tie on everything the customer has said, showing all of them is noise; the copilot commits to its single best guess and asks the one question that splits the tie."* Ship R6 with the ablation row and this rationale. (5) **Corrected by §7b:** my caveat "a failing extractor keeps the tier wide → HR should hold" was **falsified** by the adversarial lens — with a *wrong* (phantom) constraint the tier is wrong, not merely wide: at p=0.10 phantom-phrase injection R0 loses 0.016 but R6 loses 0.040 and override HR drops to 0.93. Hence the cutoff is **information-gated and provenance-conditioned**: return top-1 only if (turn == 1) or (the previous reply yielded ≥ 1 *template-extracted* constraint); if the last ask produced nothing, or any counted constraint came from the clause fallback, return the full top-10 — this makes the cutoff fail-safe under paraphrase instead of persisting top-1 for 3 turns on a wide, wrong tier. Thresholds tuned split-half under a phantom-injection harness. (6) **Honesty requirement (§7b, rules/judges lens, measured):** an *ungated* "always return exactly 1 item" policy scores **0.969** — higher than the gated 0.962 — because the metric's 0.3·MRR vs 0.02·turn weights reward singletons at every rank ≤ 10. So the gate is a **product choice, not a score choice**: we return a full shelf whenever the constraints actually discriminate. The REPORT/ablation must show the degenerate row ("always top-1: 0.969, not shipped") next to the shipped one and say why; the video demos the gate *releasing* to a full shelf on a buying session. Without that disclosure the "proactive guidance" story collapses under one judge question.

### 3k. Seen-set exclusion (implicit negative feedback) — measured

Any ASIN shown on a scored turn that did not end the session is a proven non-target (the session ends on the first hit, evaluator L252–255). Exclude it from later turns. **Danger:** in `intent_override` sessions pre-override hits don't count, so items shown before the override message may include the target.

| Variant | HR@10 | MRR | MTTC | **TechScore** | override HR |
|---|---|---|---|---|---|
| R0 top-10 (control) | .995 | .741 | 1.78 | 0.904 | 1.00 |
| R0 + naive exclusion (always) | .850 | .634 | 2.85 | 0.778 | **0.03** ← lethal |
| R0 + override-safe exclusion | .995 | .767 | 1.77 | 0.912 | 1.00 |
| R6 cutoff (control) | .995 | .915 | 2.27 | 0.947 | 1.00 |
| **R6 cutoff + override-safe exclusion** | **.995** | **.948** | **2.21** | **0.958** | 1.00 |
| R6 + exclusion with scenario/override detection disabled (paraphrase simulation) | .995 | .919 | 2.27 | 0.948 | 1.00 |

**Override-safe rule as first designed:** exclude the previous turn's shown items only if (turn-1 shape was confidently buying/browsing) OR (the override message has already been seen on an *earlier* turn) OR (turn ≥ 5 — the previous turn is then always post-override). **When the override message arrives on turn *t*, do NOT exclude turn *t−1*'s items** — that is the bug that reproduced the 0.03.

**SHIPPED RULE — revised twice by the adversarial pass (§7b): previous-turn-only exclusion, no cumulative set, no detection.** Exclude only the items shown on the *immediately previous* turn. It is self-healing: if a misfire ever excludes the target (e.g. on the override turn, where 27/30 public override sessions had displayed the target pre-override), it is back the very next turn — the evaluator-mechanics lens measured override HR 1.00 under every misfire tested, versus 0.10 for any cumulative variant whose detection fails. It costs ~0.003 vs cumulative-with-perfect-detection (inside noise) and needs zero scenario/override detection. (The earlier revision — cumulative from turn ≥ 5 — remains a flag; it is also safe but worth only +0.002.) **Recorded exception to the §3h Δ ≥ 0.02 rule:** exclusion is kept as a robustness-neutral, detection-free UX behaviour ("never re-show what the shopper just passed on"), not for its score.

*Earlier revision, superseded:* exclude from turn ≥ 5 only. Two independent lenses showed the detection clauses are an asymmetric bet: they are worth **+0.010 (0.958 vs 0.948), below the plan's own 0.016 noise floor and its Δ ≥ 0.02 ship rule**, while a single false-positive under organizer paraphrase (a paraphrased override opener read as "browsing") reproduces the **−0.13 cliff** on 15% of sessions — and a paraphrase-tolerant buying detector fires on 30/30 public override openers. The override message text is also sample data, not a contract. So: no scenario or override-message detection anywhere in the scoring path; the "turn ≥ 5" floor derives from the spec ("turn 3 or 4"). Detection-gated exclusion stays as an ablation row: *"+0.010, not shipped — within noise, template-dependent."*

**Final measured ladder (200 public sessions, real evaluator, pure stdlib):** starter 0.107 → BM25 + ask 0.752 → + constraint rerank 0.843 → + popularity 0.904 → + confidence cutoff 0.947 → **+ turn≥5 exclusion 0.948 (shipped)**. Not shipped, disclosed in the ablation table: detection-gated exclusion 0.958; **always-top-1 (no gate) 0.969** — see §3j (6).

### 3n. The exact shipped configuration — measured after the adversarial pass

| Configuration (all: pool 300, popularity tie-break, `parent_asin` final key) | HR@10 | MRR | MTTC | **TechScore** |
|---|---|---|---|---|
| old matcher (lower only), R6 cutoff, turn≥5 exclusion (= §3k "detection disabled") | .995 | .919 | 2.27 | 0.948 |
| **norm() matcher**, R6 cutoff, turn≥5 exclusion | .995 | .932 | 2.28 | 0.951 |
| **norm() matcher, information-gated cutoff, turn≥5 exclusion ← SHIPPED** | **.995** | **.916** | **2.23** | **0.948** |
| norm() matcher, no cutoff, turn≥5 exclusion (conservative fallback) | .995 | .750 | 1.78 | 0.907 |
| norm() matcher, information-gated cutoff, no exclusion | .995 | .911 | 2.23 | 0.946 |

**Final re-measurement after the evaluator-mechanics lens (six-field matcher incl. description, both detail forms):**

| Configuration | HR@10 | MRR | MTTC | **TechScore** | override HR |
|---|---|---|---|---|---|
| info-gated cutoff, no exclusion | .995 | .915 | 2.23 | 0.947 | 1.00 |
| info-gated cutoff, cumulative exclusion from turn ≥ 5 | .995 | .920 | 2.23 | 0.949 | 1.00 |
| **info-gated cutoff, previous-turn-only exclusion ← SHIPPED** | **.995** | **.937** | **2.25** | **0.954** | **1.00** |

- **Self-match of targets' own constraints: 754/800 → 795/800 (title/features/details) → 800/800 with all six evaluator fields incl. description** — confirms both lenses; score effect is inside noise but a whole class of silent misses is gone.
- Previous-turn-only exclusion beats the cumulative turn≥5 variant (+0.005) *and* is detection-free and self-healing. **P1 gate stands at clean ≥ 0.93 (shipped measured 0.954).**
- The **information gate costs 0.003 on clean data** vs plain R6: boundary sessions' "no preference… use your judgment" reply yields no constraint, so the gate releases to a full shelf at turn 2 and the hit lands at rank > 1 (boundary MRR 1.00 → 0.85). Tuning item for P3a: treat a *recognized* boundary/exhausted reply shape as "yielded" (harmless if the recognizer misfires — it only affects the cutoff, never exclusion); unrecognized replies still release the gate, which is the fail-safe we want.
- turn≥5 exclusion is worth only +0.002 on clean data (84% of hits land by turn 3). Kept as a cheap, safe flag; low priority.
- **P1 gate stands at clean ≥ 0.93 (shipped measured 0.948).**

### 3l. Data attribution
`DATA_ATTRIBUTION.md`: derived from Amazon Reviews 2023 (McAuley Lab); "use the data only for the competition, research, and other permitted purposes." → **Do not commit the catalog to the public repo.** `.gitignore` it; ship a `make data` / script that downloads `catalog.jsonl.gz` from the kit release and verifies SHA256 `07fd1426…a8f8`.

### 3m. Python
`uv python list` shows cpython 3.11.15 and 3.12.13 downloadable. Pin **3.11** (widest wheel coverage for torch/sentence-transformers if used; organizer says 3.10+).

## 4. Strategy

**Thesis.** A deterministic, fully-offline, stdlib-only core — FTS5 BM25 → verbatim constraint-satisfaction rerank → coarse-category match → popularity prior → confidence-gated cutoff — → previous-turn-only exclusion — scores **0.954** locally as shipped (≈9× the 0.107 baseline) at ~17 ms/turn, with a memory target of ~370 MB including the harness. Measured layer by layer in §3: BM25+ask 0.75 → +constraint rerank 0.84 → +popularity 0.90 → +information-gated cutoff 0.947 → +previous-turn exclusion 0.954. Two higher-scoring variants are deliberately **not shipped** and are disclosed in the ablation table: detection-gated exclusion (0.958, +0.010 inside noise with a −0.13 paraphrase cliff) and ungated always-top-1 (0.969, a metric artifact — see §3j (6)). Every layer is a `Config` flag, so the ablation ladder is regenerated from code. The 72 hours are therefore spent on, in order: (1) shipping that core as a *valid, reproducible* submission within the first ~8 hours; (2) making it robust to the two things the spec warns about — organizer paraphrasing and network/CPU/timeout restrictions; (3) a Claude-powered conversational layer that improves customer-facing language, explanations, and paraphrase-robust extraction, with a hard deterministic fallback so ranking never depends on it; (4) honest ablations, a CLI demo, and a report that presents each layer as a real recommender-systems idea.

**Decisions taken (from the user, 28 Aug):** team of 3–5 · Claude API with offline fallback · prior work allowed, so the core starts tonight · demo = rich CLI transcript + ablation table · **ship the top-1 confidence cutoff, framed transparently as pillar-II proactive guidance** (not the conservative top-3 variant).

**What we deliberately do NOT build:** hard structured filters (metadata coverage <5%); an LLM in the ranking loop (offline risk, latency, non-determinism, no measured upside — median rank on hit is already 1); cross-session personalization (profile is 9 review-aspect tags); cascade-erasure dialog state (the override never contradicts); a web UI; dense retrieval as a core component (stretch ablation only — the discriminating signal is exact attribute strings, not semantics).

**Judge story (one sentence):** *"A shopping copilot that asks the highest-value question each turn, treats every stated requirement as a hard, verifiable constraint against the catalog, and ranks what remains the way a real store does — by what customers actually buy — while explaining every recommendation."*

**Framing rules (§7b, rules/judges lens):** call the popularity prior by its name — **MostPop, the standard strong baseline in recommender evaluation** — and state the leave-last-out sampling effect ourselves (142/200 targets are in the global top-1,000 of 50k by `rating_number`; 70/200 are the single most-reviewed item of their category). Present it as engineering hygiene ("we start from the shelf a real store shows"), never as innovation; include a no-popularity ablation row. Put the innovation weight on the **constraint ledger + verifiable explanations + paraphrase-robust extraction + the information-gated shelf**, and make the paraphrased score a **headline metric next to the clean score** — the verbatim matcher is tuned to an `intent_card()` artifact, and judges scoring "Feasibility: holds under real-world conditions" will ask about real language.

## 5. Architecture

Repo mirrors the kit so the **official harness runs unmodified**: `python -m evaluator.local_evaluator` imports `starter.agent.Agent`; our `starter/agent.py` is a 3-line shim re-exporting `copilot.agent.Agent`.

```
techjam-shopping-copilot/
  evaluator/local_evaluator.py   # vendored UNMODIFIED (sha256 recorded in README)
  agent.py                       # the rules' "one Python agent entry file exporting Agent": sys.path.insert(0, dirname(abspath(__file__))) THEN
                                 # from copilot.agent import Agent — works from any CWD and when copied into an organizer layout (§7b)
  starter/agent.py               # same shim inserting its parent's parent, so the kit harness (`from starter.agent import Agent`) runs unmodified;
                                 # tests/test_import_modes.py: (1) python -m evaluator.local_evaluator from repo root, (2) `import agent` from /,
                                 # (3) agent.py + copilot/ copied into a fresh temp dir — all three reproduce the score
  copilot/
    agent.py       # Agent(catalog_path="data/catalog.jsonl"): reset/respond; global try/except → always a valid 4-key dict
    catalog.py     # load .jsonl/.jsonl.gz streaming; FTS5 index (starter schema, column weights) — FTS5 STORES the columns, so keep NO per-product
                   # dicts or text in Python (§7b: 542 MB RSS incl. the harness's own catalog copy vs starter 356 MB → a 512 MB cap kills __init__).
                   # Python keeps only asin → (rating_number, coarse_category) + COARSE_CATEGORY_VOCAB; the 300-row pool's text (all six fields incl.
                   # description) is fetched from FTS5 per turn (SELECT … WHERE rowid IN (...)) and normalized on the fly. Target RSS ≈ starter (~370 MB)
    extract.py     # (a) scenario detect from turn-1 shape — DIAGNOSTIC/PHRASING ONLY, never feeds ranking or exclusion (§7b);
                   # (b) coarse category: (1) exact turn-1 template regex; (2) else the LONGEST vocab phrase occurring as a whitespace-normalized,
                   #     case-insensitive SUBSTRING of the message (100% on the 200×3 clean templates); (3) else an ORDER-AWARE fuzzy match
                   #     (difflib ratio ≥ 0.8 over the token sequence). Never a bag-of-tokens rule: vocab phrases are permutations/subsets of each other
                   #     ("Shoes Mules & Clogs" vs "Shoes Clogs & Mules"), so even fraction-first token matching mis-resolves 24–27/200 clean openers (−0.008).
                   #     Returns the SET of tied candidates (18 vocab phrases share an identical token multiset with another); rank.py's cat_score tests
                   #     membership in the set and retrieve.py unions the pool over the set. Unit test: all 200 public openers × 3 templates resolve exactly;
                   # (c) constraints: template regexes → clause splitter fallback, each tagged with provenance {template|clause}; NO LLM here (§7b)
                   # (d) reply-shape classifier
    state.py       # SessionState: constraints[], cat_tokens, asked/exhausted, scenario, turn, raw_messages[]  — accumulate only, never erase
    retrieve.py    # FTS5 OR-query over ≤25 accumulated [a-z0-9]+ TOKENS ONLY (drop highest-DF terms first; DF computed once at index build — a 40-term OR
                   # matches ~50k rows and costs 85 ms on M3 Pro, ~250 ms on a slow vCPU). NO phrase terms: V7's phrase boost was +0.003 (noise) and
                   # 61/800 constraints are truncated mid-word, which breaks phrases. NEVER raw text into MATCH (38% of constraint strings contain
                   # FTS5-special chars; 15/800 contain '"'; one bad string in accumulate-only state would fail EVERY later turn → silent miss).
                   # ORDER BY bm25(...), parent_asin for cross-build determinism → top-300, then POOL = top-300 ∪ {all items whose coarse_category ∈ the
                   # matched category set} (≤1,354 extra; asin→coarse_category is already in memory). §7b: a category-only query ranks by doc-length
                   # noise, so the target is outside the bare 300-pool at turn 1 in 40/200 sessions (32/90 browsing openers); the union fixes it
                   # (+0.002, boundary MRR .91→1.00) where simply enlarging the pool to 1000 hurts. Pool size stays a documented hyper-parameter.
                   # Token budget: cap 32 — always include every token of the newest constraints, fill by ascending DF; generic English stoplist +
                   # template stoplist (the template-only stoplist is what keeps counts low on clean data and is fragile under paraphrase).
                   # run_eval.py logs per-turn "target in pool" so leaks are visible under paraphrase_eval. Fuzz test: MATCH over all public
                   # constraints + 5k catalog strings, 0 OperationalError. Count exceptions caught inside the agent; the "0 exceptions" gate includes those.
    rank.py        # constraint match = norm(c) in norm(text), norm = casefold + collapse whitespace; text = the evaluator's SIX SEARCH_FIELDS (title,
                   # features, details, description, categories, store) — INCLUDING description: MATERIAL_RE/COLOR_RE run over the whole searchable_text
                   # and 5/200 public targets' material/colour constraint comes ONLY from the description. Details rendered both as "key: value" (intent_card
                   # form) and "key value" (searchable_text form). Exact substring is the primary satisfier — never last-token-sensitive (61/800 constraints
                   # are truncated mid-word at 180 chars). Per-constraint graceful degradation: a disclosed string matching 0 pool items exactly is retried
                   # with token-subset matching for that string only (private intent cards may be pre-materialized by a different code path — L204–206).
                   # Unit test: ≥ 790/800 public constraints match their own target (measured 795/800). Sort key (-n_match, -cat_score, -rating_number, ε·bm25, parent_asin)
                   # — fully deterministic (86/200 sessions have rating_number ties in their category top-20); lexicographic popularity, no blend (§7b);
                   # tier_size = |candidates sharing the top (n_match, cat_score)| → uncertainty signal; per-item explanation = which constraints matched
    policy.py      # (a) ask queue feature→material→color→style→size→use_case→budget; skip exhausted; boundary → re-ask; never null
                   # (b) confidence-gated cutoff (§3j): top-1 iff tier_size>10 AND turn≤3 AND (turn==1 OR previous reply yielded ≥1 template-extracted
                   #     constraint) AND no counted constraint came from the clause fallback; otherwise full top-10. §7b: the cutoff multiplies extraction
                   #     errors ~2.5× (p=0.10 phantom phrase: R0 −0.016 vs R6 −0.040), so it never runs on empty or low-confidence extraction
                   # (c) previous-turn-only exclusion (§3k): candidates exclude state.prev (last turn's recs) — no cumulative set, self-healing,
                   #     no scenario/override detection anywhere in scoring. (cumulative-from-turn-5 kept as an alternative flag)
                   #     state.prev is written ONLY as the last step of respond(), after the outgoing dict passes validate_contract and the turn's
                   #     wall-clock is under budget; on any internal exception/timeout the fallback response is returned and state.prev = [] —
                   #     the harness discards a turn's recs on exception/timeout/non-str message and the agent cannot observe it (§7b: 5% dropped
                   #     turns with cumulative marking → HR 1.00→0.95, TS −0.037; with correct marking → no loss)
                   # (d) attributes are marked consumed when a REPLY for them is parsed, not on send — the override turn swallows the previous ask
    respond.py     # message: deterministic templates + deterministic "matched on: …" explanation from rank.py; if COPILOT_LLM=1 → one Claude call
                   # rewrites that message within the per-turn budget; strict fallback; never asserts "found it" before turn 3 in override-suspect sessions
    llm.py         # Anthropic client: disabled if COPILOT_OFFLINE=1; otherwise try, and a circuit breaker disables it for the run on the first
                   # exception/timeout of any kind (SDK may resolve credentials from ANTHROPIC_AUTH_TOKEN / ant profiles, so "key unset" is not the test);
                   # timeout 4 s, max_retries 0, effort low; usage accounting into the response's `usage`
  tools/
    run_eval.py        # official evaluator → results.json + per-scenario markdown table
    ablate.py          # V0 → V1 → +rerank → +category → +popularity → +hybrid extractor → +LLM : markdown ladder
    gen_paraphrases.py # dev-time, run ONCE: Claude (Message Batches API) paraphrases every distinct simulator string (~531 openers/replies/overrides on the
                   #     public set) in 3–5 styles → data/paraphrases.jsonl keyed by (exact string, style); committed fixture
    paraphrase_eval.py # reads the fixture only (deterministic, offline, CI-runnable); monkeypatches initial_message/customer_reply in-process; never edits the evaluator
    demo.py            # rich CLI session transcript for the video; `--redact-brands` masks `store` and brand tokens in titles on screen (the popularity
                       # prior puts Hanes/Crocs/Amazon Essentials first, so "pick a generic-brand session" is not achievable — record redacted only);
                       # the video MUST include one paraphrased-opener session showing the clause fallback + gate releasing to a full shelf on buying
    validate_contract.py # JSON-schema check of every response against docs/agent_api_contract.json (additionalProperties:false!)
    download_data.sh   # fetch catalog.jsonl.gz from the kit release + sha256 07fd1426…a8f8
  data/                # public_set.jsonl committed; catalog .gitignored
  docs/                # kit docs copied verbatim
  README.md  REPORT.md  .python-version (3.11)  .env.example
  requirements.txt               # comment-only: "no runtime dependencies" — the OFFICIAL scored configuration needs no packages, env vars, or network
  requirements-llm.txt           # anthropic (optional, demo/dev only); llm.py imports it lazily inside try/except, only when COPILOT_LLM=1
  results/<tag>.json             # committed per tag (v1.0 = guaranteed fallback); rule: never ship a tag with a lower public score than the previous
  .github/workflows/eval.yml   # py 3.10/3.11/3.12 matrix: download data → run evaluator → post score
```

**Per-turn data flow:** `user_message` → `extract` (update state) → `policy` picks `ask_attribute` → `retrieve` pool → `rank` top-10 + explanations → `respond` builds message → return `{message, ask_attribute, recommendations, usage}` — exactly those four keys.

**Existing code to reuse (verified):** starter's FTS5 schema + column weights (`starter/agent.py`), evaluator's `searchable_text`/`coarse_category`/`classify_constraint` (import from vendored evaluator or copy verbatim — copying avoids importing organizer code into the agent), the in-memory experiment scripts from this session (§3) become `tools/ablate.py`.

**LLM scope (Claude) — REVISED after the adversarial pass (§7b): message-only, opt-in, never in the scored path.**
- **Scored configuration is the deterministic core with the LLM off.** The LLM is **opt-in** via `COPILOT_LLM=1` (not opt-out), used for the demo, the video, and dev-time tooling. README/REPORT state this explicitly; the spec anticipates it ("usage is optional when no model is used").
- When on: **one call per turn** that produces the customer-facing `message` (question phrasing + a short "why these" explanation built from the deterministic matched-constraints list). Output is only ever assigned to `message`; the LLM never receives or returns `ask_attribute` or `recommendations` — a structural guarantee, not a test.
- **No runtime LLM constraint extraction in the scored path.** Measured by the adversarial lens on the real evaluator: a single hallucinated phrase that passes a catalog-substring guard, once per session, costs **−0.066**; at p=0.10/turn, −0.040 and override HR 1.00→0.93. Paraphrase robustness comes from the deterministic clause extractor + vocabulary category matcher, validated against a **committed** Claude-generated paraphrase fixture (§P3a).
- Claude's real job is **dev-time**: generate the paraphrase fixture once (Message Batches API, ~120 batched calls, <$5), write the REPORT prose from the ablation JSON, and polish the demo transcript.

**LLM implementation specifics (from the `claude-api` skill, corrected by §7b):** Python SDK `anthropic` 1.x. Model default `claude-opus-5` per skill guidance, `output_config={"effort": "low"}`, **`max_tokens` ≥ 1500** (thinking is on by default on Opus 5 and bills as output — 300 would truncate), configurable via `COPILOT_LLM_MODEL`; **first task of the LLM track is a 100-call latency/cost probe** — if p95 > the per-turn budget, switch to `claude-haiku-4-5` (no thinking) and document. Plain `client.messages.create` with text output — **no `parse()`, no `fallbacks`** (phrasing prompts don't trigger refusals, and mixing `parse()` with the beta `fallbacks` parameter is an unverified call shape that would trip the breaker on call #1). **Per-turn wall-clock budget (1.5 s total for all LLM work), not a per-call timeout**; `max_retries=0`; 429/529 count against a failure budget (e.g. 3 per 20 calls) rather than tripping permanently; a one-line LLM summary (calls, failures, p95, breaker state) is printed at run end for the REPORT. Credential resolution: the SDK also reads `ANTHROPIC_AUTH_TOKEN` and `ant auth` profiles, and **`ANTHROPIC_API_KEY=""` still authenticates with an empty key** — hence opt-in `COPILOT_LLM=1`, and tests also set `ANTHROPIC_BASE_URL=http://127.0.0.1:9` as an independent network kill switch. Prompt hygiene: product text and user messages are wrapped as delimited *data* (6/200 public intent cards contain seller marketing/imperatives, e.g. "please visit our store"); post-filter `message` for URLs and `store` names. Cost to disclose: measured from `usage`, not estimated. Read `python/claude-api/README.md` from the skill before writing `llm.py`.

**Coarse-category matcher feasibility (measured):** 1,115 distinct `coarse_category()` phrases over the catalog; 656 are strict token-subsets of another (e.g. "Women" ⊂ "Women Shoes") → longest-match wins; 0 of the 200 public targets fall to the `"clothing item"` fallback. ~~Match by fraction of phrase tokens present (≥ ⅔, ties → longest).~~ **Corrected by §7b:** longest-first with ⅔ picks a longer sibling on **29/200 clean** messages ("Jewelry Necklaces" → "Jewelry Necklaces & Pendants"); fraction-first ordering reduces this to 2/200; and 100/200 targets have 2-token categories where ⅔ demands both tokens, so a singularized paraphrase ("women dress") is wrong 162/200 times without stemming (21/200 with). → exact-template regex first; fallback stems both sides, compares token multisets, orders by (fraction desc, length desc); rank.py's 2nd key uses a graded overlap score, not binary phrase equality.

## 6. Build sequence (team of 3–5; hours are effort, tracks run in parallel; window 29 Aug 12:00 → 1 Sep 12:00, prior work allowed)

Hours are re-budgeted per the feasibility lens (§7b): the first estimates were 2–3× optimistic. H0 = 29 Aug 12:00 SGT.

| # | Track / step | Effort | Gate (must pass before moving on) |
|---|---|---|---|
| P0 | **Tonight (28 Aug), all hands, ~4 h.** (1) Env + repo per §10; run starter. (2) **Recover the §3 reference scripts** into `analysis/experiments/exp_*.py` and re-run the final one → 0.958 confirmed. (3) **Write the one-page interface contract** (`Config` fields = every §3 layer as a flag; `SessionState` fields; `extract()` return type with provenance tags; `rank()` key; `policy()` signature; `llm.py` API returning `None` on any failure) so B/C/D start coding at H0 without waiting for A. (4) D: copy the PS4 deliverables list from the Lark doc into `docs/PS4_deliverables.md`; create the Devpost draft, add every teammate, capture every required field (built-with tags, representative, bios). **Only kit vendoring + env in the 28 Aug commit** (Devpost "significantly updated after the start" clause). | 4h | baseline 0.125/0.107 reproduced on 3.11; exp script reproduces 0.958; contract merged; Devpost draft exists |
| P1 | **Deterministic core** (A, from the recovered scripts): 8 modules per §5; hybrid extractor with provenance; stemmed multiset category matcher; sanitized ≤25-term FTS5 query; pool 300; normalized 5-key deterministic rerank; information-gated cutoff; turn≥5 exclusion; memory-lean catalog (no per-product Python dicts); exception-proof `__init__`/`reset`/`respond`; `resolve_catalog_path`; sys.path bootstrap in both shims | 10–12h | clean ≥ **0.93** (measured 0.948 for the shipped rule); override HR = 1.00; `validate_contract.py` passes on every response of every run (runs inside `run_eval.py`); ≥ 770/800 public constraints match their own target after `norm()`; FTS5 fuzz 0 errors; import-mode tests pass from `/` and from a copied dir; p95 turn < 100 ms; RSS incl. harness < 400 MB; 0 exceptions (incl. those caught inside the agent). *(No paraphrase gate here — it belongs to P3a.)* |
| P2 | **Hardening → tag v1.0.** `validate_contract.py` on every response; `requirements.txt` (empty runtime); README one-command; REPORT skeleton; CI (one 3.11 job + local `uv run --python 3.10` smoke; 3.12 if cheap) | 5h | fresh clone → `download_data.sh` → one command → same score; CI green; `COPILOT_OFFLINE=1` + `ANTHROPIC_BASE_URL=http://127.0.0.1:9` run identical. **Tag `v1.0` ≈ H14 (30 Aug 02:00) = the real "submittable" milestone.** |
| P3a | **Robustness track (B, starts H0).** `gen_paraphrases.py` (Batches API, fixture committed, <$5, ~10 min); `paraphrase_eval.py`; phantom-injection harness (p ∈ {0.05, 0.10, 0.25}); tune extractor + cutoff thresholds under noise; bootstrap CIs; popularity blend hedge decision | 8h | **first** report the honest paraphrased baseline, whatever it is; then target paraphrased ≥ 0.80 with HR ≥ 0.93 and override HR = 1.00; decisions logged in REPORT |
| P4 | **LLM polisher (C, starts H0 with the latency probe).** 100-call probe → model choice; `llm.py` per §5 (opt-in, one call/turn, per-turn budget, failure budget); `message`-only rewrite + deterministic explanations; real-API invariance run on a 40-session shard, full 200 once before freeze | 3h + probe | with `COPILOT_LLM=1` on a real run: `ask_attribute` and `recommendations` bit-identical to the offline results JSON; p95 within budget; usage/cost recorded from `usage` |
| P5 | **Demo + ablation tooling (D, starts H0 against the interface contract).** `ablate.py` ladder incl. "not shipped" rows; `demo.py` CLI transcript (question, extracted constraints + provenance, tier width, top-k with "matched on", live metrics); pick a **trademark-free, marketing-free** demo session | 5h | ladder reproduces §3 numbers from code; demo runs offline end-to-end in < 5 s |
| P6 | **Report / README / Devpost / video (D + A).** README carries limitations + contributions itself (brief §4.5 requires it in the README, not only REPORT); REPORT: architecture, models, cost, latency, RSS incl. harness, per-scenario table, ablation ladder incl. the not-shipped rows (always-top-1 0.969, detection-gated exclusion 0.958, no-popularity, hard category filter, `other` exploit), paraphrase score labelled *"dev harness — simulator monkeypatched in-process, not the official local score"*; architecture diagram + ablation chart as **Devpost images** (judges may judge on text/images/video alone); 3-min video recorded from a tagged build with `--redact-brands`; YouTube public; repo flipped public; Devpost complete | 10–12h | §9 checklist all ticked; **feature freeze H48 (31 Aug 12:00)**; video recorded H44–48; **submit by 31 Aug 23:59 SGT** (12 h buffer) |
| P7 | *Stretch, only after P6 is done:* entropy question-value ask selection — neutral overall (panel) but design A measured it fixes **boundary** sessions (MTTC 2.4 vs 3.2), so test it as a boundary-targeted rule; Department as 4th sort key; dense-retrieval ablation | 4h | ablation rows only, unless ≥ +0.02 overall or a scenario-specific gain with no overall regression |

Critical path: P0 → P1 → P2(v1.0) → integrate P3a/P5 → P6. **B, C, D start at H0 against the interface contract**, not after P2. Owners: **A** core + integrator (P1/P2), **B** robustness (P3a), **C** LLM polisher (P4) then joins P6, **D** tooling/report/video/Devpost (P5/P6); a 5th person pairs on P1 (tests) then P7.

**Ordered cut list (cut from the top when behind):** (1) P7; (2) LLM polisher entirely — score unchanged by design; (3) CI matrix beyond one 3.11 job; (4) paraphrase styles 5 → 3; (5) popularity blend hedge → ship lexicographic; never cut: exception-proofing, contract validation, override-safety test, fresh-clone reproduction, video, Devpost.

## 7. Risks (own analysis; adversarial findings merged in §7b)

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| R1 | Private simulator **paraphrases** messages; template extraction collapses (measured 0.90 → 0.65 worst case) | critical | hybrid extractor; vocab-based category match; LLM extractor fallback with catalog grounding; report paraphrased score |
| R2 | **Network disabled** at final scoring | critical | `COPILOT_OFFLINE=1` documented for the organizer; otherwise circuit breaker trips on the first failure of any kind; ranking never depends on the LLM; identical score offline (tested in CI with network blocked) |
| R3 | **Contract** `additionalProperties:false`; unknown validator on private harness | high | exactly 4 keys; `validate_contract.py` on every response in tests; `ask_attribute` always in enum |
| R4 | **Timeouts / CPU / memory** limits unknown | high | deterministic p95 < 100 ms; startup < 5 s; 0.5 GB RSS; LLM timeout 4 s + breaker |
| R5 | Exception = miss | high | global try/except → valid empty-safe response; fuzz test with malformed messages |
| R6 | **Popularity skew weaker on private** | low | structurally guaranteed by 5-core leave-last-out (30% of the catalog has < 5 reviews and cannot be a target; skew uniform across difficulty buckets); only a tie-break *after* constraint satisfaction; **no blend hedge** (blends only lose MRR — two lenses agree); REPORT carries a sensitivity table: no-popularity (R6 0.870), lognormal-noised popularity (0.953), ∝rating_number synthetic proxy, plus the 35%/52% rank-1-in-category figures |
| R7 | Overfitting to 200 public sessions | medium | few parameters; bootstrap CIs; split-half validation of cutoff thresholds and blend weight; no per-session tuning; paraphrase fixture as held-out proxy; pool size treated as a hyper-parameter (300 vs 1000 = 0.016 = noise) and stated |
| R8 | Judges read MostPop / verbatim matching / the 1-item shelf as simulator exploitation | **high** | framing rules in §4: name MostPop, disclose the sampling effect and the 0.969 degenerate row, put innovation on the constraint ledger + explanations + paraphrase robustness; paraphrase score as a headline metric; video shows a paraphrased session and the gate releasing to a full shelf |
| R13 | **Memory cap**: 542 MB RSS incl. the harness's catalog copy vs starter 356 MB — a 400–540 MB limit passes the starter and kills our `__init__` (uncaught) | high | memory-lean catalog (§5 catalog.py); target ≈ starter footprint; RSS incl. harness reported in REPORT and asserted in CI |
| R14 | Non-determinism across SQLite builds / `PYTHONHASHSEED` (BM25 ties at the pool boundary; `rating_number` ties in 86/200 sessions) | medium | `ORDER BY bm25, parent_asin`; final key ends in `parent_asin`; never iterate sets in ranking code; CI runs twice with different `PYTHONHASHSEED` and diffs `results.json`; SQLite version recorded |
| R9 | Python version drift (dev 3.14, organizer 3.10+) | medium | `.python-version` 3.11; CI 3.10–3.12; no 3.11+-only syntax |
| R10 | Catalog redistribution / evaluator modification | medium | catalog .gitignored + download script + sha256; evaluator vendored unmodified with recorded sha256 |
| R11 | Team of 3–5 on one repo in 72 h | medium | branch per track, PR + CI gate, one integrator, freeze at 31 Aug 20:00 |
| R12 | Override sessions: pre-override hits don't count; phrasing claims success early | low | policy unchanged (recommend anyway — no cost); message phrasing never asserts "found it" |

### 7a. Adopted from the design panel (3 independent Plan agents, 28 Aug)

Both completed designs (A/C "ship-early", B "judge-facing") independently converged on the same stdlib core measured in §3. Additions adopted:

- **Harness does not catch exceptions in `Agent.__init__` (evaluator L306) or `reset` (L228)** — only `respond` is wrapped. An exception there aborts the *entire* private run. → Both must be exception-proof; index-build failure degrades to an empty-recs agent rather than raising.
- **Harness constructs `Agent(args.catalog)` with the uncompressed `data/catalog.jsonl`.** → `resolve_catalog_path()` tries `.jsonl`/`.jsonl.gz`, sniffs gzip magic bytes, and resolves relative to both CWD and `__file__`; unit-tested for all four cases.
- **Seen-set exclusion (implicit negative feedback):** any ASIN shown on a scored turn that did not end the session is a proven non-target and can be excluded next turn — **but pre-override hits don't count, so a naive rule deletes the target in override sessions (panel measured override HR → 0.10).** Safe rule: exclude only when turn-1 shape is confidently buying/browsing, or after the override message has been seen, or from turn 5 on. Measured with the cutoff policy in §3k.
- **LLM invariance test:** with the LLM polisher on vs off (mocked), `ask_attribute` and `recommendations` must be bit-identical across all 200 sessions — proves the offline fallback is score-invariant. Any diff blocks shipping the LLM option.
- **Tests pin the vendored evaluator's sha256**; results JSON committed per tag (`v1.0` = guaranteed fallback); rule: never ship a tag with a lower public score than the previous.
- **Demo video must avoid third-party trademarks** (deliverable rule) → pick a demo session whose top results are generic-brand items; text only, no logos; dataset attribution in the video description.
- **Popularity weight validated split-half** (even/odd sample index) rather than tuned on the full 200; adopt the setting maximizing the *minimum* of the two halves.
- **Ablation harness via a frozen `Config` dataclass** so every layer is a flag; `ablate.py` regenerates the table (including "not shipped" reference rows: `other` exploit, hard category filter, slot-erasure baseline) in one command.
- Optional insurance, **cut first if behind**: pure-Python BM25 fallback for an organizer Python built without FTS5 (low probability — the official starter itself needs FTS5). ~~Description-free fulltext for the matcher~~ — **struck by the evaluator-mechanics lens:** the material/colour regexes run over the description too and 5/200 targets' constraints come only from it (−0.004 if dropped). The matcher uses all six fields; memory is solved by fetching pool text from FTS5 instead.
- Neither design found the confidence-gated cutoff (§3j, +0.043) — it stays as this plan's addition; panel's question-value estimator (prior × pool entropy) measured neutral vs fixed order → keep fixed order, report entropy variant as an ablation row (demoable rationale, no score claim).

### 7b. Adversarial findings (6-lens workflow against this plan, 28 Aug) — merged as they land

**Lens: LLM layer — all adopted; the LLM scope in §5 was rewritten accordingly.**
- **[critical, measured]** A runtime LLM constraint extractor has negative expected value: one hallucinated phrase passing the catalog-substring guard, once per session → **−0.066**; p=0.10/turn → −0.040 and override HR 1.00→0.93; p=1.0 → 0.557, below the BM25 floor. → **Removed from the scored path.** Paraphrase robustness is deterministic (clause extractor + vocab matcher) and measured against a committed fixture.
- **[high]** `messages.parse()` + `betas`/`fallbacks` is an unverified call shape; `max_tokens` 300 with Opus-5 thinking on truncates → would trip the breaker on call #1 and silently disable the layer. → plain `messages.create`, `max_tokens ≥ 1500`, no `fallbacks`; latency probe first; Haiku 4.5 if p95 exceeds budget.
- **[high]** Per-call timeout ≠ per-turn bound: 3 × 3.9 s calls = 11.7 s/turn with zero breaker trips. → one call per turn, **per-turn wall-clock budget 1.5 s**.
- **[high]** `ANTHROPIC_API_KEY=""` still authenticates (empty key wins its precedence slot); the SDK also resolves `ANTHROPIC_AUTH_TOKEN`/`ant` profiles. → LLM is **opt-in (`COPILOT_LLM=1`)**; offline tests use `COPILOT_OFFLINE=1` **and** `ANTHROPIC_BASE_URL=http://127.0.0.1:9`.
- **[medium]** The mocked invariance test proves only wiring. → structural guarantee (LLM output assigned to `message` only) + one **real-API** run compared bit-for-bit to the offline results JSON.
- **[medium, measured]** The cutoff multiplies extraction errors ~2.5× (p=0.10: R0 −0.016 vs R6 −0.040). → provenance-conditioned cutoff (§3j, §5 policy.py); thresholds tuned under phantom injection.
- **[medium]** Paraphrase generation unbudgeted and non-reproducible. → generate once via Batches API, commit `data/paraphrases.jsonl`, evaluator reads the fixture only.
- **[low]** 6/200 public intent cards carry seller marketing/imperatives ("please visit our store"). → prompts treat product text as delimited data; post-filter `message`; demo session chosen free of it.
- **[low]** `max_retries=0` + first-failure breaker makes a routine 429 fatal for the whole run. → failure budget (3 per 20 calls); end-of-run LLM summary line.

**Lens: time/feasibility — all adopted; §6 re-budgeted, §10 extended.**
- **[high]** Critical path serialized on one person; B/C/D idle ~14 h. → interface contract written tonight; B/C/D start at H0 against it.
- **[high]** P1 gate "paraphrase ≥ 0.85" was never achieved in any measurement (best 0.828) and blocked the critical path. → removed from P1; P3a first *measures* the honest baseline, then targets ≥ 0.80 with HR ≥ 0.93 / override 1.00.
- **[high]** The §3 reference implementation exists only inside this session's transcript. → P0 step: recover the experiment scripts to `analysis/experiments/`, re-run to 0.958 before writing the package (or regenerate from this session's context).
- **[high]** P1 5 h → 10–12 h; "submittable at hour 9" → **tag v1.0 at ≈ H14**. Total budget re-planned; freeze moved to features-at-H48, video from a tagged build H44–48, submit by 31 Aug 23:59.
- **[medium, measured]** 38% of constraint strings contain FTS5-special characters; unsanitized MATCH raises → empty turn. → tokens-only OR query; phrases quoted with doubled `"` and `- : * ^` stripped; fuzz test over all public constraint strings.
- **[medium]** P4 full LLM-on runs cost 30–110 min and $4–13 each. → iterate on a 40-session shard; full 200 once before freeze; response cache keyed by prompt hash.
- **[medium]** Devpost logistics unslotted; PS4 deliverables live behind a login-only Lark page. → D copies them to `docs/PS4_deliverables.md` tonight (they are also in vault note `01` §4.5: description, public repo + README, public YouTube demo); Devpost draft at H0; representative + bios noted.
- **[medium]** P3b re-ran a neutral experiment on the critical-path owner. → **cut**; only the "never claim found-it before turn 3" phrasing rule survives (in `respond.py`).
- **[low]** Runbook nits: `.python-version` never written; `results.json` (evaluator's default output in CWD) and `analysis/` not ignored. → fixed in §10.
- **[low]** Devpost "New & Existing" clause: prior work must be "significantly updated after the start". → 28 Aug commit limited to kit vendoring + env; README states the sequencing.

**Lens: rules & judge-perception — all adopted.**
- **[high, measured]** Ungated always-top-1 = **0.969 > gated 0.962**; the metric rewards singletons at every rank ≤ 10. → gate framed as a product choice; degenerate row disclosed (§3j (6)).
- **[high]** Turn-1 fingerprinting for exclusion: +0.010 (inside noise) vs −0.13 cliff; the most exploit-looking code a judge would read. → exclusion from turn ≥ 5 only (§3k shipped rule).
- **[high, measured]** Popularity prior = MostPop over leave-last-out sampling (142/200 targets in the global top-1,000; 70/200 rank-1 in category). → named and disclosed as hygiene, not innovation (§4 framing rules); no-popularity ablation row.
- **[high]** No root `agent.py`; shim import depends on CWD; `Agent()` construction is outside the harness's try/except. → sys.path bootstrap in both shims; three import-mode tests.
- **[high]** `anthropic` in `requirements.txt` + default-on LLM = scored config depends on the organizer's environment; a bare `import anthropic` can abort the run. → comment-only `requirements.txt`, `requirements-llm.txt`, lazy import, opt-in `COPILOT_LLM=1`.
- **[medium]** Trademark rule vs popularity (top-300 by reviews is Hanes/Amazon Essentials/Crocs…). → `demo.py --redact-brands`; record redacted only.
- **[medium]** Verbatim matching is tuned to an `intent_card()` artifact and gets worse when relaxed (soft 0.811 vs exact 0.904). → paraphrase score as a headline metric; mandatory paraphrased-session demo; reframe as entity linking to the catalog's attribute vocabulary.
- **[medium]** `additionalProperties:false` passes locally (evaluator ignores extras) and fails only on a strict private harness; explanations/usage extras are the likely offenders. → recs dicts exactly `{"parent_asin"}`; usage exactly two ints; explanations only inside `message`; `validate_contract.py` moved into the P1 gate and into `run_eval.py`.
- **[low]** Pre-window public repo/commits. → repo **private tonight**, public at submission; first `copilot/` commit after 29 Aug 12:00; build timeline in README.
- **[low]** README must itself carry limitations + contributions; Devpost needs images; `results/` must be committed per tag; paraphrase numbers labelled non-official. → all in P6 / §10.

**Lens: private-set generalization — all adopted.**
- **[critical, measured]** §3k "fail-safe" was one-directional: a paraphrase-tolerant buying detector fires on **30/30** override openers → −0.13. → detection removed from the scoring path (see above); inverse regression test: force the detector to "buying"/"override seen" for every session → override HR must stay 1.00.
- **[high, measured]** Category matcher wrong on 29/200 clean messages; singularization cliff 162/200 without stemming. → §5 extract.py (b) redesigned.
- **[high, measured]** **RSS 542 MB incl. harness** vs starter 356 MB. → memory-lean catalog; target ~370 MB (R13).
- **[high, measured]** 97/800 (12%) of targets' own constraints fail unnormalized verbatim matching (casefold, whitespace, `key: value` flattening). → `norm()` defined in §5 rank.py + self-match test; **re-run the ladder — likely free MRR upside**.
- **[medium, measured]** A constraint containing `"` in accumulate-only state fails **every later turn** of the session via the global try/except → silent miss the "0 exceptions" gate wouldn't see. → tokenized phrases; internal-exception counter in `run_eval --profile`.
- **[medium]** R6 + exclusion never measured under paraphrase; R6 persists top-1 for 3 turns on a wide wrong tier when extraction yields nothing (est. −0.028 extra). → information-gated cutoff (§3j (5)); measure under the fixture before v1.0.
- **[medium]** Ranking non-deterministic across SQLite builds / hash seeds; pool size is a hidden hyper-parameter. → R14.
- **[low]** 40-term OR query = 85 ms here, ~250 ms on a slow vCPU. → cap ~25 terms by DF.
- **[low]** Override message text is sample data, not a contract. → nothing keys on it.

**Lens: evaluator-mechanics — all adopted.**
- **[critical, measured]** Exclusion *semantics* decide catastrophe vs benign: any cumulative set + failed detection → override HR 0.10 (27/30 override sessions display the target pre-override); **previous-turn-only exclusion with no detection → override HR 1.00, self-healing.** → shipped rule (§3k, §5 policy.py (c)); inverse test in §9.
- **[high]** Exclusion violates the §3h Δ ≥ 0.02 rule (+0.006–0.011, +0.001 detection-free) while being the only layer with a catastrophic mode. → shipped only in the detection-free form as a UX behaviour; exception recorded in REPORT against the rule.
- **[high, measured]** Vocab phrases are permutations of one another; even fraction-first token matching mis-resolves 24–27/200 clean openers (−0.008); literal ⅔-longest 80+/200 (−0.028). → exact longest-substring first (100% on clean), order-aware difflib fallback; 200×3 unit test.
- **[medium]** Private intent cards may be pre-materialized (`materialize_hidden_fields` L204–206 returns them verbatim if present). → per-constraint graceful degradation; drift cases in the harness; stated in limitations.
- **[medium, measured]** Normalization gaps beyond colour/budget: details colon 5/800, whitespace 2/800, **180-char mid-word truncation 61/800** (fatal for phrase/last-token matching), internal "; " 10/800 (fragments harmless). → both detail forms; exact substring primary; **phrase terms dropped from retrieval**.
- **[medium, measured]** "Description-free matcher" was wrong (5/200 targets, −0.004). → struck; six fields.
- **[low, measured]** Pool 300 excludes the target at turn 1 in 40/200 sessions, yet larger pools score lower — pool is a regularizer. → documented as a tuned hyper-parameter.
- **[low]** The override turn swallows the previous ask (7/30 sessions lose a colour constraint). → mark attributes consumed on parsed reply, not on send.
- **[low, measured]** Cutoff is robust to a weaker prior: no-popularity R0 0.852 → R6 0.870; lognormal-noised popularity 0.953. → no-pop and noisy-pop ablation rows replace the blend hedge as the honest answer to R6.
- **[low]** Deterministic final key mandatory. → `parent_asin` last (already in §5).

**Lens: mechanism-adversary (constructed failure sessions) — all adopted.**
- **[critical, measured]** Any fuzzy scenario classifier feeding exclusion → override HR 0.10 (TS 0.963→0.836); by construction every override opener lacks both template markers, so a paraphrase-robust "has a constraint clause vs vague" classifier labels 100% of them buying/browsing. → already resolved by previous-turn-only exclusion with no detection; regression test: paraphrased openers of all four scenario types → override HR 1.00.
- **[high, measured]** **Lost-turn amplification:** the harness discards recs on exception/timeout/non-str `message` and the agent cannot observe it; marking those recs "seen" turns each dropped turn into a miss (5% drops: HR 1.00→0.95, TS −0.037). → `state.prev` written only after the response validates and the turn is under budget; fallback path never marks; **lost-turn injection test** (5% simulated drops → HR ≥ 0.99) in §9.
- **[high, measured]** V7 phrase terms raise on 15/800 constraints (13/200 sessions) and, once in state, fail every later turn. → phrase terms dropped (already); the 15 quote-bearing strings become a tokenizer unit test.
- **[high, measured]** Bag-of-tokens category matcher wrong on 24/200 clean openers even requiring all tokens (18 vocab phrases share a token multiset). → exact longest-substring first (already); **return the set of tied candidates**; 200/200 unit test.
- **[medium, measured]** **Pool leak:** target outside the bare 300-pool at turn 1 in 40/200 sessions (32/90 browsing). → pool = FTS top-300 ∪ matched-category members (+0.002; boundary MRR .91→1.00); per-turn "target in pool" diagnostic.
- **[medium, measured]** Details `Key: Value` vs `Key Value` (5/800) and whitespace (2/800); on a ∝rating_number private proxy 3.8% of sessions have ≥1 unmatched constraint. → both forms + whitespace collapse (already); the 7 public failures become unit tests.
- **[low, measured]** Cutoff per-session accounting: 0 sessions lose a hit; 67 sessions had a would-be hit withheld, 60 delayed 1–3 turns, **9 net-hurt (worst −0.060), 51 net-helped, mean +0.038**. → publish this table in REPORT — it pre-empts the "metric gaming" read better than framing.
- **[low, measured]** Popularity: no public target is structurally buried (185/200 are #1 among same-category items satisfying all four of their constraints; the rest rank 2–7); a ∝rating_number synthetic 400-session set reproduces the public scores. → **drop the w=4 blend hedge** (blends only lose MRR); report the synthetic proxy + weak-skew sensitivity rows instead.
- **[low]** 40-term cap + template-only stoplist is fragile under paraphrase (newest constraint's tokens could be truncated while rank.py still counts them). → cap 32 with newest-constraint tokens guaranteed, DF-ordered fill, generic + template stoplists; measure unique-terms-per-turn under paraphrase.

**Refutation of critical/high findings + synthesis — _pending_**

## 8. Open questions

Answered 28 Aug: team 3–5 · Claude + fallback · prior work allowed · CLI demo · top-1 cutoff shipped with transparent framing.
Remaining (defaults in brackets, proceed unless told otherwise): GitHub repo name/owner [`KevinAldrinTan900/techjam-shopping-copilot`, **private until submission**]; teammate OSes for setup docs [macOS/Linux; Windows via WSL]; who records the video [track D owner]; Anthropic key availability [one shared dev key via `.env`, never committed; needed only for the paraphrase fixture, the demo polisher, and REPORT drafting].

**Decision the adversarial pass re-opened, resolved without asking:** keep the *gated* top-1 cutoff the user chose, even though an ungated always-top-1 scores 0.969 > 0.962. Shipping the ungated version would be pure metric gaming and indefensible to judges; the gated version is defensible **only** if the 0.969 row is disclosed and the gate is framed as a product choice. That disclosure is now mandatory in REPORT/Devpost/video (§3j (6), §4 framing rules).

## 9. Verification

- **Score:** `python -m evaluator.local_evaluator` → `results.json`; clean TechScore ≥ **0.94** (measured 0.958), every scenario HR ≥ 0.95, override HR = 1.00. `tools/paraphrase_eval.py` ≥ **0.85** (Claude-generated paraphrases; the synthetic set gave 0.83–0.95 depending on extractor).
- **Override safety (regression test that must never go red):** exclusion + cutoff with scenario/override detection *forcibly disabled* → override HR still 1.00 (measured 0.948 overall). This guards the one failure mode that silently zeroes 15% of sessions.
- **Contract:** `pytest tests/` — schema validation of 2,000 responses; enum/keys/ordering; ≤10 unique valid ASINs; no exceptions on adversarial inputs (empty string, 10 KB message, unicode, None-like).
- **Reproducibility:** GitHub Action on push: 3.10/3.11/3.12 → download data → evaluate → assert score ≥ threshold → upload results artifact. Fresh-clone runbook executed by a teammate who didn't write the code.
- **Offline / LLM invariance:** the scored configuration has the LLM off (opt-in `COPILOT_LLM=1`). Tests: (a) default run and `COPILOT_OFFLINE=1` + `ANTHROPIC_BASE_URL=http://127.0.0.1:9` run are byte-identical; (b) one **real-API** `COPILOT_LLM=1` run → `ask_attribute` and `recommendations` bit-identical to the offline results JSON for every session (only `message` may differ); (c) structural: `llm.py` output is assigned to `message` and nothing else (grep-level test).
- **FTS5 safety:** fuzz `MATCH` over every public-set constraint string + a 5,000-string catalog sample → 0 `sqlite3.OperationalError`.
- **Extraction noise:** phantom-phrase injection harness at p ∈ {0.05, 0.10, 0.25} → cutoff/exclusion thresholds chosen so HR ≥ 0.97 and override HR = 1.00 at p = 0.10.
- **Latency/memory:** `tools/run_eval.py --profile` prints p50/p95 per turn, startup time, **RSS including the harness's catalog copy** (< 400 MB), and the count of exceptions caught inside the agent (must be 0).
- **Determinism:** CI runs the evaluator twice with different `PYTHONHASHSEED` values and on two SQLite builds if available → identical `results.json`.
- **Import modes:** harness from repo root; `import agent` from `/`; `agent.py` + `copilot/` copied into a fresh temp dir — all reproduce the score.
- **Inverse override test:** force scenario detection to return "buying" and "override seen" for every session → override HR must remain 1.00 (proves nothing in the scoring path depends on detection). Also feed paraphrased openers of all four scenario types.
- **Lost-turn amplification test:** simulate the harness dropping 5% of turns (replace the response with empty recs after the agent returns) → HR ≥ 0.99, override HR = 1.00; proves the fallback path never marks discarded recs as seen.
- **Unit fixtures from the adversarial pass:** the 15 quote-bearing public constraints (tokenizer/MATCH), the 7 constraints that fail unnormalized matching (`norm()`), the 200 × 3 clean openers (category matcher = 200/200), the 18 permutation-tied vocab phrases (set semantics).
- **Cutoff accounting for REPORT:** `tools/ablate.py --per-session` emits withheld / delayed / net-hurt / net-helped counts and the mean per-session delta for the cutoff vs always-top-10.
- **Slice checks before any tag (from design A):** TechScore ≥ 0.90 on each difficulty bucket (easy/medium/hard) and on the least-popular half of targets; with popularity disabled the floor must stay ≥ 0.85 (design A measured 0.893); 2-fold halves must agree within 0.02 for every tuned knob (cutoff thresholds, pool size, term cap).
- **Ablation:** `tools/ablate.py` regenerates the ladder table in REPORT.md from code, not by hand.
- **Demo:** `tools/demo.py --session public_0042` runs a full session offline; recorded for the video.
- **Deliverables checklist:** agent entry + helpers + `requirements.txt` + README (one command, Python version, env vars, network statement) + REPORT (architecture, models, cost, tokens, latency, per-scenario metrics, limitations, contributions) + Devpost text + public YouTube link + public repo.

## 10. P0 runbook (tonight — exact commands, ~2 h)

```bash
cd ~/Documents/Projects/shopping_copilot
uv python install 3.11 && uv venv --python 3.11 .venv && source .venv/bin/activate && echo 3.11 > .python-version
uv pip install pytest jsonschema                       # dev only; runtime core has no deps
# step 0 — recover the planning-session experiment scripts (the §3 reference implementation) before anything else:
#   regenerate from this session (Claude has them in context) into analysis/experiments/exp_01_bm25.py … exp_10_cutoff_exclusion.py,
#   run exp_10 → expect TechnicalScore 0.958; these become tools/ablate.py in P5
# kit files (vendored, unmodified)
mkdir -p evaluator starter docs tools tests copilot
curl -sL https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/evaluator/local_evaluator.py -o evaluator/local_evaluator.py
for f in submission_rules.md competition_specification.md agent_api_contract.json evaluation_config.json baseline_results.json; do
  curl -sL https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/docs/$f -o docs/$f; done
curl -sL https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/starter/agent.py -o starter/agent.py   # baseline, replaced in P1
curl -sL https://raw.githubusercontent.com/TechJam2026/techjam-conversational-search/main/DATA_ATTRIBUTION.md -o DATA_ATTRIBUTION.md
touch evaluator/__init__.py starter/__init__.py copilot/__init__.py
shasum -a 256 evaluator/local_evaluator.py > tests/evaluator.sha256      # pinned by a test
# data: catalog already downloaded & verified in data/; harness wants uncompressed
cp analysis/public_set.jsonl data/ && gzip -dk data/catalog.jsonl.gz     # keeps the .gz too
printf 'data/catalog.jsonl\ndata/catalog.jsonl.gz\n.venv/\nresults.json\n.env\n__pycache__/\n.pytest_cache/\nanalysis/*.jsonl\nanalysis/local_evaluator.py\n' > .gitignore   # results/<tag>.json IS committed
# (analysis/experiments/*.py IS committed — it is the reference implementation; the duplicate evaluator/public_set copies in analysis/ are not)
# gate: reproduce the baseline exactly
python -m evaluator.local_evaluator            # expect hit_rate_at_10 0.125, mrr 0.068034, mttc 9.81
git init -b main && git add -A && git commit -m "P0: kit vendored, baseline reproduced"
gh repo create KevinAldrinTan900/techjam-shopping-copilot --private --source . --push  # private tonight; `gh repo edit --visibility public` at submission (§7b)
```
Then P1 starts from the §3 experiment code (the in-memory scripts from this planning session are the reference implementation of every layer) → `copilot/` package + `starter/agent.py` shim.

## 11. Revision 2 (29 Aug) — network access at scoring is assumed available

**What changed.** The team has confirmed internet access and external LLM APIs are usable. This revision re-scopes the
Claude layer from "opt-in demo polish" (§5) to a first-class, **auto-enabled** layer whenever `ANTHROPIC_API_KEY` is set.
It does **not** move the LLM into ranking by default — every measurement in §3/§7b that argued against that still stands
(one hallucinated constraint per session −0.066; ties are between bestsellers that satisfy identical constraints, so no
model has information to break them; exact matching beats every fuzzier variant). The rules still say the organizer
"may disable network", so the deterministic core remains the guaranteed path and every LLM call is fail-safe.

**LLM uses in the scored path (each a `Config` flag, `copilot/llm.py`):**
| use | when it fires | grounding | default |
|---|---|---|---|
| `llm_extract` | only when no simulator template matched the message (organizer paraphrasing) | constraints must be verbatim substrings of the message; category must be one of the offered vocab candidates; provenance `llm` → cutoff gate releases to a full shelf | on |
| `llm_polish` | every turn | output assigned to `message` only; URLs and store names stripped | on |
| `llm_rerank` | ablation: orders the top tier | only offered asins accepted, missing appended | **off** — measure, report, ship only if Δ ≥ +0.02 |

Guarantees: one shared per-turn wall-clock budget (4 s), `max_retries=0`, failure budget 3/20 → breaker for the run,
`thinking` disabled, structured JSON output with a plain-text fallback, usage summed per turn into `usage`. On clean
public data the templates match 100%, so `llm_extract` never fires and the score is identical to §3n (0.958);
its value shows only under paraphrase — which is why the fixture (below) comes first.

**Build sequence changes.**
- P3 (was P3a) is now on the critical path right after v1.0: `tools/gen_paraphrases.py` (Batches API, ~4k requests,
  Haiku, <$5) → `data/paraphrases.jsonl` committed → `tools/paraphrase_eval.py` reports, side by side: clean; paraphrased
  with deterministic clause extraction (`llm=false`); paraphrased with `llm_extract`. Decision rule unchanged (§3h).
- P4 merges into P3: the invariance test (recs/ask bit-identical with polish on) is a unit test with a fake client and a
  real-API run on 40 sessions; a 100-call latency/cost probe picks the models (`COPILOT_LLM_EXTRACT_MODEL` default
  `claude-haiku-4-5`, `COPILOT_LLM_MODEL` default `claude-sonnet-5`).
- README/REPORT: the organizer must export `ANTHROPIC_API_KEY` to get the LLM layer; without it the run is the
  deterministic core (state both scores). Cost/latency disclosed from `usage` and `run_eval --profile`.

**Risk register deltas.** R2 (network disabled) downgraded to medium — same score either way by construction, verified by
`test_offline_flags_do_not_change_results`. New R15: API latency/429s in an 800-session run → budget + breaker + failure
budget; a run with the breaker open is still a valid 0.958 run. New R16: key handling — never committed; `.env.example`
documents it; the organizer's environment is assumed to carry it.
