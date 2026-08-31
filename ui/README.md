# Demo UI

A browser view of one public session playing out turn by turn: the customer's messages, what the copilot
understood, the shelf reordering underneath it, the per-turn pipeline trace, and the token/USD cost.

**This is a demo harness, not part of the submitted agent.** Nothing in `copilot/` imports it, and the scored
evaluator run never touches it. Flask is required only to *watch* the agent.

## Run

```bash
# 1. deps (once)
pip install -r ui/requirements.txt
cd ui/web && npm install && npm run build && cd ../..

# 2. go
python ui/server.py            # → http://localhost:5000
```

The catalog (50k products → in-memory FTS5) loads once at startup, about 7 s; sessions then run warm.

For frontend development, run the Vite dev server alongside it for hot reload:

```bash
python ui/server.py            # API on :5000
cd ui/web && npm run dev       # UI on :5173, proxies /api → :5000
```

### Offline vs. LLM mode

| | command | cost |
|---|---|---|
| **Offline** (default) | `python ui/server.py` | `$0.00` — no network, no key, fully deterministic |
| **LLM polish on** | `COPILOT_LLM=1 python ui/server.py` | priced live, per turn and per layer |

Offline is the configuration that gets scored. LLM mode exists to show the cost of the optional polish layer;
the cost panel then reports per-turn USD, per-layer model attribution, and a projected total for the
organizer's 800-session private set.

## What it shows

- **Hidden intent card** — the target and its hard/soft constraints, which the agent never sees. Watching the
  copilot converge on them from the customer's phrasing alone is the point of the demo.
- **Extraction path per turn** — `template` / `clause` / `llm`, so the hybrid fallback chain is visible.
- **The constraint ledger** growing (accumulate-only, never erased).
- **Shelf movement** — `NEW`, `↑n`, `↓n`, `=`, plus what dropped out, so reranking is legible turn to turn.
- **`counts: false`** before an intent override fires — pre-override hits do not score, per the rules.
- **Trace panel** — `extract → state → build_terms → retrieve → rank → respond` with the actual query terms
  and matched constraint labels for each turn.

## Design notes

**The UI observes the agent; it does not modify it.** Each turn calls the same `copilot.agent.Agent.respond()`
the evaluator calls, then reconstructs the trace afterwards from session state (`st.last_parsed`,
`st.constraints`) plus a re-run of the pure `build_terms` / `compile_matchers` functions. No hooks or
instrumentation are added to `copilot/`, so what you see on screen is what the scored run does.

**The customer is the real simulator.** `data/public_set.jsonl` contains no dialogue — the organizer's
simulator generates messages at evaluation time from the hidden target. This server drives that same
simulator (`initial_message`, `customer_reply`, `materialize_hidden_fields`), exactly as `tools/demo.py` does.

**Why SSE.** A session is one stateful loop: the simulator carries `disclosed` / `boundary_used` / override
state between turns, so turns cannot be fetched independently. The server streams the whole session and the
client paces it out on a timer (the speed slider) for watchability.

**Threading.** The FTS5 index lives in an in-memory sqlite connection, and sqlite connections are bound to
their creating thread. Every catalog touch is therefore marshalled onto one dedicated worker thread
(`AGENT_THREAD` in `server.py`) rather than relaxing `check_same_thread` in `copilot/catalog.py`.

**Pricing** lives in the `PRICING` table at the top of `server.py` — USD per 1M tokens, per model. Every
dollar figure in the UI derives from that table alone.

## Suggested sessions

| session | why |
|---|---|
| `public_0002` | intent override — target sits at rank 1 on turn 2 but `counts: false`; the override lands on turn 3, hit on turn 4 |
| `public_0001` | buying, easy — hits on turn 1 from a single template-extracted constraint |

`python tools/demo.py --list buying` lists ids by scenario.

## Terminal equivalent

`tools/demo.py` prints the same session to stdout and remains the reference for the recorded walkthrough:

```bash
python tools/demo.py --session public_0002 --redact-brands --reveal --top 5
```
