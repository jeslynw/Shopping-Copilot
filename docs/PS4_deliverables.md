# PS4 deliverables, rules and logistics (TikTok TechJam 2026)

Source: the TechJam 2026 info doc (Lark, login-only — `bytedance.larkoffice.com/wiki/GdYFwzWNLiREsSkuIjZcDznInWc`),
extracted 28 Aug 2026; kit docs in `docs/` (`submission_rules.md`, `competition_specification.md`).

## Deliverables (Problem Statement 4 — Shopping Copilot)
1. **Written project description on Devpost** — how the solution addresses the problem statement; development tools,
   APIs, libraries/frameworks, datasets and assets used.
2. **Public GitHub repository** — well-structured, commented code covering all components, plus a README with:
   project overview · setup and installation · steps to reproduce results · a brief reflection on limitations and
   what you'd improve with more time · team member contributions.
3. **Demo video** — short, end-to-end, uploaded to **YouTube as public**, linked in the Devpost description,
   **free of third-party trademarks or copyrighted content**. For backend/NLP tracks a walkthrough of API usage,
   inference examples, or result analysis is accepted in place of a front-end.

## Submission package (kit `submission_rules.md` / `competition_specification.md`)
- One Python agent entry file exporting `Agent` + local helper modules + setup instructions.
- Short report: method, model choice, limitations; **disclosure of latency, token usage, estimated model cost**; team contributions.
- Exact Python version if non-default; dependency install steps; **one command** to run in the official harness; non-obvious env vars.
- State whether network access is required; describe the offline fallback (final scoring may disable network).
- No private eval data, organizer-only files, secrets, privileged host access, evaluator modification, or undeclared external services.
- One demonstrated multi-turn session.

## Judging
| Criterion | Weight |
|---|---|
| Technical Execution (TechnicalScore = 0.5·HR@10 + 0.3·MRR + 0.2·Efficiency is an *input*, not the whole criterion) | 35% |
| Innovation & Problem Insight | 20% |
| Impact & Relevance | 20% |
| Feasibility & Practicality | 15% |
| Presentation & Communication (final event only) | 10% |

## Dates (SGT)
- **29 Aug 12:00 → 1 Sep 12:00** — 72-hour challenge; Devpost submission window (submissions only inside the window).
  Team plan: feature freeze 31 Aug 12:00, submit by **31 Aug 23:59** (12 h buffer).
- 1 Sep 15:00 → 4 Sep 15:00 People's Choice voting · 8 Sep finalists · 11 Sep Grand Final @ TikTok Singapore · 15 Sep winners.

## Devpost logistics
- Every member registers on **both** the registration form (`bit.ly/TikTokTechJam2026Registration`) and Devpost
  (`tiktoktechjam2026.devpost.com`); teams ≤ 5; a late joiner re-submits the form listing all teammates (by 1 Sep 12:00).
- Rules page: `tiktoktechjam2026.devpost.com/rules`. "New & Existing" clause: prior work is allowed only if
  **significantly updated after the start** → the 28 Aug commit holds kit vendoring, env, analysis scripts and docs;
  the `copilot/` package lands from 29 Aug 12:00 and the README states the timeline.
- Devpost draft (human action — needs a login): create the project, add every teammate, pick the **representative**,
  fill built-with tags, member bios, problem-statement selection (PS4), repo link, YouTube link, ≥ 2 images
  (architecture diagram, ablation chart — judges may judge on text/images/video alone).
- Video: text-only CLI recording from a tagged build with `tools/demo.py --redact-brands` (the popularity prior surfaces
  branded bestsellers); dataset attribution (Amazon Reviews 2023, McAuley Lab) in the description.

## Data
`DATA_ATTRIBUTION.md`: derived from Amazon Reviews 2023 (McAuley Lab, UCSD); use only for the competition/research.
→ the catalog is **not** committed; `tools/download_data.sh` fetches `catalog.jsonl.gz` from the kit release and
verifies SHA256 `07fd142631fd6b03e2b4d09988c3eb7d53720e9d57010c79db48eeaada50a8f8`.
