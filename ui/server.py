from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402
from flask_cors import CORS  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
DATASET = ROOT / "data" / "public_set.jsonl"

# ---------------------------------------------------------------------------------------------------
# Cost model. USD per 1M tokens, list price at time of writing (Sep 2026). Edit here if rates change --
# every dollar figure the UI shows is derived from this table alone, so it stays auditable.
# ---------------------------------------------------------------------------------------------------
PRICING = {
    "claude-haiku-4-5":  {"input": 1.00, "output":  5.00},
    "claude-sonnet-5":   {"input": 3.00, "output": 15.00},
    "claude-opus-5":     {"input": 15.00, "output": 75.00},
    "gpt-4.1-mini":      {"input": 0.40, "output":  1.60},
    "gpt-4.1":           {"input": 2.00, "output":  8.00},
}
PRIVATE_SET_SIZE = 800          # organizer's held-out sessions, for the projected-cost figure
MEAN_TURNS = 2.155              # measured MTTC over the 200 public sessions (results.json) — projecting from a
                                # single session's turn count would skew badly on one that hits on turn 1


def price_for(model: str):
    """Longest-prefix match so dated snapshots (claude-haiku-4-5-20251001) resolve to their family.
    Returns None for a model absent from the table — the caller must surface that rather than bill it at zero."""
    best = max((k for k in PRICING if model.startswith(k)), key=len, default=None)
    return PRICING[best] if best else None


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = price_for(model)
    return 0.0 if p is None else (prompt_tokens * p["input"] + completion_tokens * p["output"]) / 1e6


# ---------------------------------------------------------------------------------------------------
# Per-call LLM accounting. `llm.turn_usage` aggregates every call in a turn, but extract/polish/rerank can
# run on different models at different rates — so we wrap the transport to record (model, in, out) per call.
# Wrapping happens in the UI layer only; copilot/llm.py is untouched.
# ---------------------------------------------------------------------------------------------------
class CallLog:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def install(self, llm) -> None:
        if llm is None or getattr(llm, "_ui_wrapped", False):
            return
        inner = llm._request

        def wrapped(client, model, system, user, schema, max_tokens, remaining):
            t0 = time.perf_counter()
            text, used = inner(client, model, system, user, schema, max_tokens, remaining)
            self.calls.append({
                "model": model,
                "layer": "extract" if schema and "constraints" in json.dumps(schema) else ("rerank" if schema else "polish"),
                "prompt_tokens": int(used[0]), "completion_tokens": int(used[1]),
                "cost_usd": cost_usd(model, used[0], used[1]),
                "unpriced": price_for(model) is None,     # model missing from PRICING → shown as such, never billed at $0
                "ms": round((time.perf_counter() - t0) * 1000, 1),
            })
            return text, used

        llm._request = wrapped
        llm._ui_wrapped = True

    def drain(self) -> list[dict]:
        out, self.calls = self.calls, []
        return out


# ---------------------------------------------------------------------------------------------------
app = Flask(__name__, static_folder=None)
CORS(app)

_state: dict = {"agent": None, "samples": None, "startup_s": 0.0, "calls": CallLog()}

# The catalog's FTS5 index lives in an in-memory sqlite connection, and sqlite connections are bound to the
# thread that created them (`check_same_thread` defaults to True). Flask serves each request on a different
# worker thread, so every touch of the catalog — the agent's own retrieval included — is marshalled onto this
# single dedicated thread. Fixing it here keeps `copilot/catalog.py` (the scored path) untouched, and it also
# serialises concurrent demo runs, which we want anyway since the agent holds one live session at a time.
AGENT_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent")


def on_agent_thread(fn, *args, **kwargs):
    return AGENT_THREAD.submit(fn, *args, **kwargs).result()


# Only one session may be in flight. `Agent.reset()` keeps a single live session (`self.sessions = {sid: st}`),
# so a second concurrent run — a double-click, a second tab, or a reload while a stream is open — wipes the
# first run's constraint ledger mid-flight and both produce garbage. A browser that disconnects does not stop
# the generator here either; Flask only notices on the next failed write. So each run takes a token, and every
# loop iteration re-checks that it is still the current one and bails out if a newer run has superseded it.
_run_lock = threading.Lock()


def claim_run() -> int:
    with _run_lock:
        _state["run_token"] = _state.get("run_token", 0) + 1
        return _state["run_token"]


def still_current(token: int) -> bool:
    return _state.get("run_token") == token


def _boot():
    """Load the catalog once (50k products → FTS5 index, a few seconds) and keep the agent warm."""
    if _state["agent"] is not None:
        return _state
    from evaluator import local_evaluator as ev
    from copilot.agent import Agent
    t0 = time.perf_counter()
    agent = Agent(str(CATALOG))
    if agent.catalog is None:
        raise SystemExit(f"catalog failed to load: {agent.init_error}")
    _state.update(agent=agent, samples=ev.load_jsonl(DATASET), startup_s=time.perf_counter() - t0)
    _state["calls"].install(agent.llm)
    return _state


def boot():
    return on_agent_thread(_boot)


def llm_availability() -> tuple[bool, str, str]:
    """Can online mode actually run? Needs both a provider key and that provider's SDK importable.
    Resolves the provider from the environment on every call: `LLM.provider` is fixed at construction and
    falls back to "anthropic" when no key was present, so a server booted before .env existed would keep
    reporting a provider it cannot actually use. Returns (available, reason, provider)."""
    from copilot.config import llm_provider_from_env
    provider = llm_provider_from_env()
    if not provider:
        return False, "no API key — add ANTHROPIC_API_KEY or OPENAI_API_KEY to .env", ""
    try:
        __import__(provider)
    except ImportError:
        return False, f"{provider} SDK not installed — pip install {provider}", provider
    return True, "", provider


def set_mode(agent, online: bool) -> None:
    """Flip the LLM layer for the next run. `Agent._turn` gates every LLM use on `llm.enabled`, so toggling
    that one attribute switches the whole layer without rebuilding the agent (a 7 s catalog reload)."""
    llm = agent.llm
    if llm is None:
        return
    llm.enabled = bool(online) and bool(agent.cfg.llm_polish or agent.cfg.llm_extract or agent.cfg.llm_rerank)
    if llm.enabled:
        llm.breaker_open = False      # a previous failed online run must not poison this one
        llm.recent.clear()


def target_product(asin: str) -> dict:
    """One streaming pass over the catalog; only lines mentioning the asin are parsed (same as tools/demo.py)."""
    from copilot.catalog import _open_text, resolve_catalog_path
    path = resolve_catalog_path(CATALOG) or CATALOG
    needle = f'"{asin}"'
    with _open_text(Path(path)) as fh:
        for line in fh:
            if needle in line:
                p = json.loads(line)
                if str(p.get("parent_asin")) == asin:
                    return p
    return {}


def shelf_delta(asin: str, rank: int, prev: list[str]) -> str:
    if not prev:
        return ""
    if asin not in prev:
        return "NEW"
    was = prev.index(asin) + 1
    return "=" if was == rank else f"{'↑' if was > rank else '↓'}{abs(was - rank)}"


# -- routes ------------------------------------------------------------------------------------------
@app.route("/api/health")
def health():
    s = boot()
    llm = s["agent"].llm
    available, reason, provider = llm_availability()
    return jsonify({
        "catalog_size": len(s["agent"].catalog.ids),
        "startup_s": round(s["startup_s"], 1),
        "sessions": len(s["samples"]),
        "llm_available": available,                 # can online mode be selected at all?
        "llm_reason": reason,                       # if not, why
        "llm_enabled": bool(llm and llm.enabled),   # mode of the most recent run
        "llm_provider": provider or None,
        "models": ({"extract": llm.extract_model, "polish": llm.polish_model} if (llm and available) else {}),
        "layers": {"polish": s["agent"].cfg.llm_polish, "extract": s["agent"].cfg.llm_extract,
                   "rerank": s["agent"].cfg.llm_rerank},
        "config": {"extractor": s["agent"].cfg.extractor, "cutoff": s["agent"].cfg.cutoff,
                   "llm_polish": s["agent"].cfg.llm_polish, "llm_extract": s["agent"].cfg.llm_extract},
    })


@app.route("/api/sessions")
def sessions():
    s = boot()
    scenario = request.args.get("scenario")
    return jsonify([
        {"session_id": x["sample_id"], "scenario": x["scenario_type"],
         "difficulty": x.get("difficulty_bucket", "?"), "category": x.get("category_bucket", "?"),
         "preference_tags": x["user_profile"].get("preference_tags", [])}
        for x in s["samples"] if not scenario or x["scenario_type"] == scenario
    ])


@app.route("/api/run/<session_id>")
def run(session_id: str):
    """Stream one full session as SSE: `turn` events, then a final `done` event."""
    top = max(1, min(int(request.args.get("top", 10)), 10))
    online = request.args.get("mode", "offline") == "online"
    s = boot()
    sample = next((x for x in s["samples"] if x["sample_id"] == session_id), None)
    if sample is None:
        return jsonify({"error": f"no session {session_id}"}), 404
    if online:
        available, reason, _ = llm_availability()
        if not available:
            return jsonify({"error": f"online mode unavailable: {reason}"}), 400
    on_agent_thread(set_mode, s["agent"], online)

    def event(kind: str, payload: dict) -> str:
        return f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def stream():
        from evaluator import local_evaluator as ev
        from copilot.rank import compile_matchers
        from copilot.retrieve import build_terms

        agent, cat, cfg, calls = s["agent"], s["agent"].catalog, s["agent"].cfg, s["calls"]
        target = str(sample["ground_truth"]["parent_asin"])
        product = target_product(target)
        card, behavior = ev.materialize_hidden_fields(sample, {target: product})
        eff = {**sample, "intent_card": card, "behavior": behavior}
        category = ev.coarse_category([str(v) for v in product.get("categories") or []])

        yield event("start", {
            "session_id": session_id, "scenario": sample["scenario_type"],
            "difficulty": sample.get("difficulty_bucket", "?"), "category": category,
            "profile": sample["user_profile"],
            "target": {"asin": target, "title": " ".join(str(product.get("title", "")).split())[:90],
                       "price": product.get("price"), "reviews": cat.pop.get(target, 0)},
            "intent_card": {"hard": card.get("hard_constraints", []), "soft": card.get("soft_preferences", [])},
            "llm_enabled": bool(agent.llm and agent.llm.enabled),
            "mode": "online" if online else "offline",
            "models": ({"extract": agent.llm.extract_model, "polish": agent.llm.polish_model}
                       if (online and agent.llm) else {}),
        })

        token = claim_run()
        sid = f"ui_{session_id}_{int(time.time())}"
        on_agent_thread(agent.reset, sid, sample["user_profile"])
        calls.drain()
        disclosed: set[str] = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        msg = ev.initial_message(eff, category, disclosed)
        prev_recs: list[str] = []
        hit_turn = best_rank = None
        tok_in = tok_out = 0
        total_cost = 0.0
        all_calls: list[dict] = []

        def one_turn(message: str, turn: int) -> dict:
            """Agent call + trace reconstruction, all on the agent thread (sqlite affinity)."""
            t0 = time.perf_counter()
            out = agent.respond(sid, message, turn, ev.TOP_K)
            ms = (time.perf_counter() - t0) * 1000
            st = agent.sessions.get(sid)
            parsed = getattr(st, "last_parsed", None)
            new = [c for c in st.constraints if c.turn == st.turn] if st else []

            # trace, reconstructed from state + pure re-runs (the agent itself is never instrumented)
            terms = build_terms(st, new, cfg, cat) if st else []
            recs = ev.normalize_recommendations(out.get("recommendations"), cat.ids)
            titles = cat.titles(recs)
            matched: dict[str, list] = {}
            if st and st.constraints and recs:
                matchers = compile_matchers(st.constraints, cfg, cat)
                texts = cat.texts(recs, cfg.match_fields)
                for a in recs:
                    matched[a] = [m.label for m in matchers if m.fn(texts.get(a, ""), a)]
            return {"out": out, "ms": ms, "st": st, "parsed": parsed, "new": new,
                    "terms": terms, "recs": recs, "titles": titles, "matched": matched}

        for turn in range(1, ev.MAX_TURNS + 1):
            if not still_current(token):
                yield event("superseded", {"turn": turn})
                return
            r = on_agent_thread(one_turn, msg, turn)
            out, ms, st, parsed = r["out"], r["ms"], r["st"], r["parsed"]
            new, terms, recs, titles, matched = r["new"], r["terms"], r["recs"], r["titles"], r["matched"]

            turn_calls = calls.drain()
            all_calls.extend(turn_calls)
            t_in = sum(c["prompt_tokens"] for c in turn_calls)
            t_out = sum(c["completion_tokens"] for c in turn_calls)
            t_cost = sum(c["cost_usd"] for c in turn_calls)
            tok_in += t_in
            tok_out += t_out
            total_cost += t_cost

            rank_of_target = recs.index(target) + 1 if target in recs else None
            counts_now = override_applied

            yield event("turn", {
                "turn": turn,
                "customer": msg,
                "agent": out["message"],
                "ask_attribute": out["ask_attribute"],
                "latency_ms": round(ms, 1),
                "shelf": [{
                    "rank": i, "asin": a,
                    "title": " ".join(str(titles.get(a, ("", ""))[0]).split())[:80],
                    "store": titles.get(a, ("", ""))[1],
                    "reviews": cat.pop.get(a, 0),
                    "delta": shelf_delta(a, i, prev_recs),
                    "matched": matched.get(a, [])[:3],
                    "is_target": a == target,
                } for i, a in enumerate(recs[:top], 1)],
                "shelf_size": len(recs),
                "dropped": [a for a in prev_recs[:top] if a not in recs[:top]] if prev_recs else [],
                "target_rank": rank_of_target,
                "counts": counts_now,
                "trace": {
                    "extract": {
                        "mode": cfg.extractor,
                        "path": "template" if (parsed and parsed.template) else
                                ("llm" if any(p == "llm" for _, p in (parsed.constraints if parsed else [])) else "clause"),
                        "kind": parsed.kind if parsed else None,
                        "new_constraints": [{"text": c.text, "provenance": c.provenance} for c in new],
                    },
                    "state": {
                        "ledger_size": len(st.constraints) if st else 0,
                        "ledger": [c.text for c in st.constraints] if st else [],
                        "categories": list(st.categories) if st else [],
                        "cat_prov": st.cat_prov if st else "none",
                        "consumed": sorted(st.consumed) if st else [],
                    },
                    "retrieve": {"terms": terms, "term_count": len(terms),
                                 "max_terms": cfg.max_terms, "pool": cfg.pool},
                    "rank": {"shown": len(recs), "cutoff_rule": cfg.cutoff,
                             "committed_to_one": len(recs) == 1,
                             "top_matched": matched.get(recs[0], []) if recs else []},
                    "llm_calls": turn_calls,
                },
                "cost": {"turn_usd": round(t_cost, 6), "total_usd": round(total_cost, 6),
                         "turn_tokens": [t_in, t_out], "total_tokens": [tok_in, tok_out]},
            })

            if counts_now and target in recs:
                best_rank, hit_turn = recs.index(target) + 1, turn
                break
            prev_recs = list(recs)
            if turn == ev.MAX_TURNS:
                break

            override = eff.get("behavior", {}).get("override") or {}
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                if str(override.get("new_value", "")):
                    disclosed.add(str(override["new_value"]))
                msg = str(override.get("message", "Actually, please ignore my earlier preference."))
            else:
                msg, boundary_used = ev.customer_reply(eff, out.get("ask_attribute"), disclosed, boundary_used)

        rr = 0.0 if best_rank is None else 1.0 / best_rank
        eff_turn = hit_turn if hit_turn is not None else ev.MAX_TURNS + 1
        turns_run = hit_turn if hit_turn is not None else ev.MAX_TURNS
        yield event("done", {
            "hit": hit_turn is not None, "hit_turn": hit_turn, "rank": best_rank,
            "reciprocal_rank": round(rr, 4),
            "score": round(0.5 * (1 if hit_turn else 0) + 0.3 * rr + 0.2 * (11 - eff_turn) / 10, 4),
            "target": {"asin": target, "title": " ".join(str(product.get("title", "")).split())[:90]},
            "cost": {
                "session_usd": round(total_cost, 6),
                "tokens": [tok_in, tok_out],
                "per_turn_usd": round(total_cost / max(turns_run, 1), 6),
                # extrapolated at the measured MTTC, not this session's turn count
                "projected_private_set_usd": round(total_cost / max(turns_run, 1) * MEAN_TURNS * PRIVATE_SET_SIZE, 2),
                "private_set_size": PRIVATE_SET_SIZE,
                "projection_basis": f"{MEAN_TURNS} turns/session (measured MTTC) × {PRIVATE_SET_SIZE} sessions",
                "unpriced_models": sorted({c["model"] for c in all_calls if c.get("unpriced")}),
            },
        })

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@app.route("/")
def index():
    dist = Path(__file__).parent / "web" / "dist"
    if (dist / "index.html").is_file():
        return send_from_directory(dist, "index.html")
    return ("<h2>Shopping Copilot demo API is running.</h2>"
            "<p>Start the React dev server: <code>cd ui/web && npm install && npm run dev</code></p>"
            "<p>API: <a href='/api/health'>/api/health</a></p>")


@app.route("/<path:path>")
def assets(path: str):
    dist = Path(__file__).parent / "web" / "dist"
    if (dist / path).is_file():
        return send_from_directory(dist, path)
    return index()


if __name__ == "__main__":
    # Mode is chosen per run from the UI dropdown, not pinned at startup, so the agent is built with its
    # provider and models resolved and `set_mode` flips the layer per request. Every run still starts
    # offline until the dropdown says otherwise. COPILOT_OFFLINE=1 remains a hard kill switch: it makes
    # `llm_enabled_from_env()` false, so online can never be selected for this process.
    print("loading catalog …")
    s = boot()
    on_agent_thread(set_mode, s["agent"], False)
    available, reason, provider = llm_availability()
    print(f"ready — {len(s['agent'].catalog.ids):,} products in {s['startup_s']:.1f}s · {len(s['samples'])} sessions")
    print(f"mode   — offline by default; online {'available (' + provider + ')' if available else 'UNAVAILABLE: ' + reason}")
    print("UI     — http://localhost:5000   (dev, hot reload: http://localhost:5173)")
    app.run(host="127.0.0.1", port=5000, threaded=True, debug=False)
