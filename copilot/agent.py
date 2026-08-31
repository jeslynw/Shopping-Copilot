from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .catalog import Catalog
from .config import Config, from_env
from .contract import validate_response
from .extract import Parsed, extract
from .llm import LLM
from .policy import apply_reply, cutoff_k, exclusion, next_ask
from .rank import Ranked, rank
from .respond import build_message
from .retrieve import build_terms, retrieve
from .state import SessionState

ALLOWED = {"category", "material", "color", "size", "style", "brand", "budget", "feature", "use_case", "other"}


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl", config: Optional[Config] = None,
                 llm_client=None) -> None:
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
            self.llm = LLM(self.cfg, client=llm_client)
        except Exception:
            self.llm = None

    # -- harness interface ------------------------------------------------------------------
    def reset(self, session_id: str, user_profile: dict) -> None:
        try:
            sid = str(session_id)
            st = SessionState(session_id=sid)
            try:
                tags = user_profile.get("preference_tags") if isinstance(user_profile, dict) else None
                if isinstance(tags, (list, tuple)):
                    st.profile_tags = tuple(str(t).strip().lower() for t in tags[:8])
            except Exception:
                pass
            self.sessions = {sid: st}                             # keep only the live session
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
        cfg, cat, llm = self.cfg, self.catalog, self.llm
        if cat is None:
            return self._fallback(st), []
        if llm is not None:
            llm.begin_turn()

        # ---- extraction: simulator templates first; LLM-grounded when they don't match; clause heuristic as the floor
        parsed = extract(msg, st.turn, cfg.extractor, cat.matcher)
        if not parsed.template and llm is not None and llm.enabled and cfg.llm_extract:
            cands = cat.matcher.candidates(msg) if st.turn == 1 else []
            lp = llm.extract(msg, st.turn, cands)
            if lp is not None:
                if parsed.cat_prov == "exact" or not lp.categories:      # keep a deterministic exact category
                    lp.categories, lp.cat_prov = parsed.categories, parsed.cat_prov
                if not lp.constraints:                                    # keep the clause constraints as the floor
                    lp.constraints = parsed.constraints
                parsed = lp
        new = apply_reply(st, parsed, cfg)

        # ---- retrieve + rank
        terms = build_terms(st, new, cfg, cat)
        cands = retrieve(cat, terms, st, cfg, k_max)
        if cfg.rerank:
            ranked, tier = rank(cands, st, cfg, cat)
        else:
            ranked = [Ranked(c.asin, 0, 0, cat.pop.get(c.asin, 0), c.bm25_rank, ()) for c in cands]
            tier = 0
        if cfg.llm_rerank and llm is not None and llm.enabled and tier > 1:     # ablation only
            head = ranked[:min(tier, k_max)]
            titles = cat.titles([r.asin for r in head])
            items = [{"asin": r.asin, "title": titles.get(r.asin, ("", ""))[0][:120], "matches": list(r.matched)[:4]} for r in head]
            order = llm.rerank(items, [c.text for c in st.constraints], st.categories[0] if st.categories else None)
            if order:
                by = {r.asin: r for r in head}
                ranked = [by[a] for a in order] + ranked[len(head):]

        # ---- exclusion, cutoff, ask
        excl = exclusion(cfg, st, st.turn)
        if excl:
            ranked = [r for r in ranked if r.asin not in excl]
        k = cutoff_k(cfg, st, st.turn, tier, parsed, k_max)
        top = ranked[:k]
        ask = next_ask(st, cfg)
        st.last_asked = ask
        st.boundary_attr = None

        # ---- message (+ optional polish)
        titles = cat.titles([top[0].asin]) if top else {}
        message = build_message(st, parsed, ask, top, k, tier, titles)
        if llm is not None and llm.enabled and cfg.llm_polish:
            facts = {"category": st.categories[0] if st.categories else None,
                     "constraints": [c.text for c in st.constraints][-4:], "shown": len(top), "tier_size": tier,
                     "ask": ask, "stores": [s for _, s in titles.values() if s]}
            polished = llm.polish(message, facts)
            if polished:
                message = polished
        usage = llm.turn_usage if llm is not None else (0, 0)
        out = {"message": message, "ask_attribute": ask,
               "recommendations": [{"parent_asin": r.asin} for r in top],
               "usage": {"prompt_tokens": int(usage[0]), "completion_tokens": int(usage[1])}}
        return out, [r.asin for r in top]

    def _fallback(self, st: SessionState) -> dict:
        try:
            ask = next_ask(st, self.cfg)
        except Exception:
            ask = "feature"
        if ask not in ALLOWED:
            ask = "feature"
        return {"message": "Let me narrow this down — which features matter most to you?", "ask_attribute": ask,
                "recommendations": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
