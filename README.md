# TechJam Conversational E-Commerce Search Challenge

Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer keeps 800 additional sessions private for final evaluation.

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Download the Catalog

Download `catalog.jsonl.gz` from the GitHub Release attached to this repository, then run:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify the downloaded file using the published `SHA256SUMS` file.

## Run the Starter

Python 3.10 or later is recommended. The starter uses only the Python standard library.

```bash
python3 -m evaluator.local_evaluator
```

Edit `starter/agent.py` to implement your system. Do not edit the evaluator or public labels when reporting your local score.
The command writes per-session results and aggregate metrics to `results.json`.

The included weak BM25 starter scores Hit Rate@10 `0.125`, MRR `0.068034`, and
MTTC `9.81` on the released public set. See `docs/baseline_results.json`.

## Team Agent vs Baseline

`starter/agent.py` is the harness entry point and exports the **team agent** (`copilot/`, deterministic and
stdlib-only) by default. The kit's original weak BM25 starter is kept unchanged as `starter/baseline_agent.py`.
Same command, either agent:

```bash
python3 -m evaluator.local_evaluator                  # team agent   → TechnicalScore 0.958 on the public set
AGENT=baseline python3 -m evaluator.local_evaluator   # kit baseline → TechnicalScore 0.107
python3 tools/run_eval.py --profile                   # team agent + latency / memory / contract checks
```

LLM layer (optional, on when a key is present): put `OPENAI_API_KEY=…` (or `ANTHROPIC_API_KEY=…`) in a git-ignored `.env`
at the repo root — or export it — and run the same command; the agent
rewrites the customer-facing message with the model (`ask_attribute` and `recommendations` are unaffected by design —
verified turn-for-turn against the offline run). A grounded LLM constraint-extraction fallback exists as an ablation flag
(`--config llm_extract=true` in `tools/run_eval.py`); it measured no gain over the deterministic extractor on the paraphrase fixture. `COPILOT_LLM=0` or
`COPILOT_OFFLINE=1` switches it off; token usage appears in `reported_token_usage`. Paraphrase robustness:
`python3 tools/gen_paraphrases.py` once (Batches API) then `python3 tools/paraphrase_eval.py`.

Layout: `agent.py` (submission entry file, re-exports the same `Agent`) · `copilot/` (implementation) ·
`tools/` (evaluation, contract validation, data download) · `tests/` (kit unittest + ours) ·
`analysis/experiments/` (measured ablation ladder) · `docs/PLAN.md` (build plan) · `docs/results/` (committed scores).
Tests: `pip install -r requirements-dev.txt && pytest -q`.

## Reproduce Our Results

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate   # Python ≥ 3.10 works; 3.11 is pinned in .python-version
bash tools/download_data.sh                                  # catalog.jsonl.gz from the kit release → SHA256 check → data/catalog.jsonl
python3 -m evaluator.local_evaluator                         # TechnicalScore 0.958 (HR@10 1.000 · MRR 0.937 · MTTC 2.155) → results.json
python3 tools/run_eval.py --profile                          # same run + contract check on every response, p50/p95 latency, RSS
pip install -r requirements-dev.txt && pytest -q             # 45 tests (≈ 5 min — they re-run the evaluator)
```

- **Runtime dependencies: none.** The scored path is the Python standard library (SQLite FTS5); `requirements.txt` has nothing
  to install. Dev/optional extras (`pytest`, `jsonschema`, `openai`, `anthropic`) are in `requirements-dev.txt`.
- **Network: not required.** With no API key the run is the deterministic core above. With `OPENAI_API_KEY` (or
  `ANTHROPIC_API_KEY`) exported or in a git-ignored `.env`, the LLM layer rewrites the customer-facing `message` only —
  `ask_attribute` and `recommendations` are unchanged by construction (verified live: 83/83 turns identical) — and any
  failure or timeout switches the layer off for the rest of the run. Latency, tokens and cost are disclosed in `REPORT.md`.
- Env vars (all optional): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `COPILOT_LLM=0|1`, `COPILOT_OFFLINE=1`,
  `COPILOT_LLM_PROVIDER=openai|anthropic`, `AGENT=baseline`.
- Committed scores: `docs/results/` (`official_shipped.json` = the official command; `v1.0.json` = the tagged build, offline;
  `v1.0_llm_polish.json` = the same run with the LLM polish on — all 200 per-session results identical; `ablation.json` =
  the REPORT §6 tables).
  CI (`.github/workflows/eval.yml`) reproduces the score on a fresh Ubuntu clone, asserts ≥ 0.94, override HR 1.00 and
  zero exceptions/contract violations, and checks that two `PYTHONHASHSEED` values give identical per-session results.
- Ablation ladder from code: `python3 tools/ablate.py` (`--reference` adds the layers that exist only in
  `analysis/experiments/`; `--paraphrase` runs the same rows under the paraphrase fixture). Demo transcript for the video:
  `python3 tools/demo.py --session public_0042 --redact-brands` (offline, a few seconds).

## Limitations and What We'd Improve

- **Tuned to the simulator's information channel.** Requirements are matched *verbatim* against catalog text because the
  kit's customer simulator lifts them verbatim from the target listing. Under LLM paraphrase of every simulator string
  (our dev harness, `tools/paraphrase_eval.py`) the score drops from 0.958 to 0.924; against free-form human language the
  clause extractor would need real entity linking to the catalog's attribute vocabulary (materials, closures, care
  instructions…). That is the first thing we would build with more time.
- **The popularity prior is MostPop and it works because of how sessions are sampled.** Targets are leave-last-out
  purchases from 5-core reviews, so heavily-reviewed items are over-represented (163/200 public targets are in the top 10
  by review count of their coarse category). A store with different traffic needs its own prior; it is one flag
  (`tiebreak`) and the no-popularity row is in the ablation table.
- **The one-item shelf is a product choice.** When more than ten items tie on everything the shopper has said, the
  copilot commits to a single pick and asks the question that splits the tie, then releases to a full shelf as soon as
  the constraints discriminate. We measured the ungated "always return one item" policy and disclose it in `REPORT.md`
  rather than ship it.
- **No dense retrieval and no LLM inside ranking.** Both were measured (docs/PLAN.md §3, §7b) and did not pay here: the
  discriminating signal is exact attribute strings, and one hallucinated constraint per session costs −0.066. A catalog
  with populated prices, sizes and materials (here < 5 % coverage) would make structured filters and semantic matching
  worthwhile.
- **No cross-session personalization.** The profile is nine review-aspect tags and each session is scored independently;
  a deployment would carry a slow user profile as *priors*, never as filters.
- **Public-set overfitting risk.** 200 sessions; bootstrap 95 % CI half-width ≈ 0.01–0.016. Every shipped knob had to
  clear Δ ≥ +0.02 or show a robustness gain with no regression; pool size (300) is a tuned hyper-parameter.

## Team Contributions

| Member | Contribution |
|---|---|
| Kevin Aldrin Tan (`KevinAldrinTan900`) | Problem analysis and evaluator/catalog profiling; build plan (`docs/PLAN.md`); deterministic core (`copilot/`); measured ablation ladder (`analysis/experiments/`); LLM layer (`copilot/llm.py`); paraphrase fixture and harness; tests; tooling (`tools/`); report. |
| `jeslynw` | _to fill in_ |
| `tiffabytes` | _to fill in_ |
| `jessnoellyn` | _to fill in_ |

Build timeline (Devpost "new & existing work" rule): 28 Aug 2026 — planning, kit vendoring, catalog profiling and the
experiment scripts; from 29 Aug 12:00 SGT (challenge start) — the `copilot/` package, LLM layer, paraphrase fixture,
tooling, CI and documentation.

## Agent Interface

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` is one of `category`, `material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. See `docs/agent_api_contract.json`.

## Technical Metrics

- **Hit Rate@10:** fraction of sessions that find the target within 10 turns.
- **MRR:** mean reciprocal rank of the target; a miss contributes zero.
- **MTTC:** mean first-hit turn; a miss is assigned turn 11.
- **Reported token usage:** prompt and completion tokens returned by the team's model client.

```text
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency = clip((11 - MTTC) / 10, 0, 1)
```

`TechnicalScore` is an objective input to the `Technical Execution` assessment. It is not a separate judging criterion and does not represent the entire `Technical Execution` score.

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

Teams may use any legally accessible LLM API or local model. Teams manage their own credentials and must never commit API keys. Model choice, estimated cost, token usage, and latency must be disclosed. Token usage is a feasibility metric, not part of the core technical score. The organizer does not provide or reimburse model API credits; teams are responsible for any costs incurred through optional external services.

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  editable weak starter
evaluator/local_evaluator.py      public-set simulator and scorer
```

## Judging and Submission Policy

- Participant submission requirements: `docs/submission_rules.md`
- Organizer-only final judging controls: `organizer/JUDGING_RUNBOOK.md`
- Organizer private release checklist: `organizer/private_release_checklist.md`
- Judging day operations SOP: `organizer/JUDGING_DAY_SOP.md`

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.
