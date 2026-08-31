from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog
from .config import Config
from .extract import tokens
from .state import Constraint, SessionState


@dataclass(frozen=True)
class Candidate:
    asin: str
    bm25_rank: int
    bm25: float


def build_terms(state: SessionState, new: list[Constraint], cfg: Config, catalog: Catalog) -> list[str]:
    if cfg.query_source == "messages":
        terms = list(dict.fromkeys(tokens(" ".join(state.messages))))
        return terms[:cfg.max_terms]
    must = list(dict.fromkeys(t for c in new for t in tokens(c.text)))
    rest = list(dict.fromkeys([t for c in state.categories for t in tokens(c)] +
                              [t for c in state.constraints for t in tokens(c.text)]))
    rest = [t for t in rest if t not in must]
    if len(must) + len(rest) > cfg.max_terms:
        df = catalog.df(rest)
        rest.sort(key=lambda t: (df.get(t, 0), t))   # rarest first
    return (must + rest)[:cfg.max_terms]


def retrieve(catalog: Catalog, terms: list[str], state: SessionState, cfg: Config, top_k: int) -> list[Candidate]:
    limit = cfg.pool if cfg.rerank else top_k
    pool = [Candidate(a, i, s) for i, (a, s) in enumerate(catalog.search(terms, limit))] if terms else []
    if cfg.rerank and cfg.pool_union_category and state.categories:
        have = {c.asin for c in pool}
        extra = sorted({a for c in state.categories for a in catalog.members.get(c, ())} - have)
        base = len(pool) + 10_000
        pool += [Candidate(a, base + i, 0.0) for i, a in enumerate(extra)]
    if cfg.rerank and cfg.vector_route and terms:
        have = {c.asin for c in pool}
        extra = [a for a, _ in catalog.vector_search(terms, cfg.vector_top) if a not in have]
        base = len(pool) + 20_000                          # recall-only: vector items rank below every BM25 item on ties
        pool += [Candidate(a, base + i, 0.0) for i, a in enumerate(extra)]
    return pool
