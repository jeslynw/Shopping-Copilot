"""Shopping Copilot Agent — deterministic, offline, stdlib-only core (PLAN.md §5).

Per turn: extract → apply_reply → build_terms → retrieve → rank → exclusion → cutoff → ask → message → (polish) → validate.
`__init__`, `reset` and `respond` never raise; every response has exactly the four contract keys.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .catalog import Catalog
from .config import Config, from_env
from .contract import validate_response
from .extract import Parsed, extract
from .llm import Polisher
from .policy import apply_reply, cutoff_k, exclusion, next_ask
from .rank import Ranked, rank
from .respond import build_message
from .retrieve import build_terms, retrieve
from .state import SessionState


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl", config: Optional[Config] = None) -> None:
        self.cfg = config or from_env()
        self.sessions: dict[str, SessionState] = {}
        self.catalog: Optional[Catalog] = None
        self.init_error: Optional[str] = None
        self.internal_exceptions = 0
        self.contract_violations = 0
        self.turn_times: list[float] = []
        t0 = time.perf_counter()
        try:
            self.catalog = Catalog(catalog_path)
        except Exception as e:  # degrade to an empty-recommendation agent rather than abort the run
            self.init_error = f"{type(e).__name__}: {e}"
        self.startup_s = time.perf_counter() - t0
        try:
            self.polisher = Polisher(self.cfg)
        except Exception:
            self.polisher = None

    # -- harness interface ------------------------------------------------------------------
    def reset(self, session_id: str, user_profile: dict) -> None:
        try:
            sid = str(session_id)
            self.sessions = {sid: SessionState(session_id=sid)}   # keep only the live session
        except Exception:
            self.internal_exceptions += 1

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        t0 = time.perf_counter()
        sid = str(session_id)
        st = self.sessions.get(sid)
        if st is None:
            st = SessionState(session_id=sid)
            self.sessions[sid] = st
        recs: list[str] = []
        try:
            out, recs = self._turn(st, user_message, turn, top_k)
        except Exception:
            self.internal_exceptions += 1
            out, recs = self._fallback(st), []
        if validate_response(out):
            self.contract_violations += 1
            out, recs = self._fallback(st), []
        elapsed = time.perf_counter() - t0
        self.turn_times.append(elapsed)
        # mark "seen" only when the response is valid AND fast enough that the harness will have kept it
        st.prev = recs if elapsed <= self.cfg.turn_budget_s else []
        st.shown[st.turn] = list(st.prev)
        return out

    # -- one turn -----------------------------------------------------------------------------
    def _turn(self, st: SessionState, user_message: object, turn: object, top_k: object) -> tuple[dict, list[str]]:
        msg = user_message if isinstance(user_message, str) else ("" if user_message is None else str(user_message))
        st.turn = int(turn) if isinstance(turn, int) and not isinstance(turn, bool) and turn >= 1 else st.turn + 1
        k_max = int(top_k) if isinstance(top_k, int) and not isinstance(top_k, bool) and top_k >= 1 else 10
        k_max = min(k_max, 100)
        st.messages.append(msg)
        cfg, cat = self.cfg, self.catalog
        if cat is None:
            return self._fallback(st), []
        parsed = extract(msg, st.turn, cfg.extractor, cat.matcher)
        new = apply_reply(st, parsed, cfg)
        terms = build_terms(st, new, cfg, cat)
        cands = retrieve(cat, terms, st, cfg, k_max)
        if cfg.rerank:
            ranked, tier = rank(cands, st, cfg, cat)
        else:
            ranked = [Ranked(c.asin, 0, 0, cat.pop.get(c.asin, 0), c.bm25_rank, ()) for c in cands]
            tier = 0
        excl = exclusion(cfg, st, st.turn)
        if excl:
            ranked = [r for r in ranked if r.asin not in excl]
        k = cutoff_k(cfg, st, st.turn, tier, parsed, k_max)
        top = ranked[:k]
        ask = next_ask(st, cfg)
        st.last_asked = ask
        st.boundary_attr = None
        titles = cat.titles([top[0].asin]) if top else {}
        message = build_message(st, parsed, ask, top, k, tier, titles)
        usage = (0, 0)
        if self.polisher is not None and self.polisher.enabled:
            facts = {"category": st.categories[0] if st.categories else None,
                     "constraints": [c.text for c in st.constraints][-4:],
                     "shown": len(top), "tier_size": tier, "ask": ask,
                     "stores": [s for _, s in titles.values() if s]}
            polished = self.polisher.rewrite(message, facts)
            if polished:
                message, usage = polished, self.polisher.last_usage
        out = {"message": message, "ask_attribute": ask,
               "recommendations": [{"parent_asin": r.asin} for r in top],
               "usage": {"prompt_tokens": int(usage[0]), "completion_tokens": int(usage[1])}}
        return out, [r.asin for r in top]

    def _fallback(self, st: SessionState) -> dict:
        try:
            ask = next_ask(st, self.cfg)
        except Exception:
            ask = "feature"
        if ask not in {"category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"}:
            ask = "feature"
        return {"message": "Let me narrow this down — which features matter most to you?", "ask_attribute": ask,
                "recommendations": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
