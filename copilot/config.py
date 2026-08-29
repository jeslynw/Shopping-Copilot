"""Every §3 layer is a flag; defaults are the shipped configuration (PLAN.md §3n)."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace

ATTRS = ("feature", "material", "color", "style", "size", "use_case", "budget")


@dataclass(frozen=True)
class Config:
    # dialog policy
    ask_order: tuple = ATTRS
    boundary_reask: bool = True
    reask_on_yield2: bool = False
    # extraction
    extractor: str = "hybrid"          # template | clause | hybrid
    # retrieval
    query_source: str = "extracted"    # extracted | messages
    max_terms: int = 32
    pool: int = 300
    pool_union_category: bool = False  # measured: clean −0.003, paraphrased −0.015 (MRR) → flag only, re-test in P3a
    # rerank
    rerank: bool = True
    cat_sort_key: bool = True
    norm_match: bool = True
    match_fields: str = "six"          # six | three
    tiebreak: str = "popularity"       # popularity | bm25 | blend
    blend_w: float = 0.0
    # cutoff / exclusion
    cutoff: str = "gated"              # none | R6 | gated | top1
    exclusion: str = "prev_turn"       # none | prev_turn | turn5 | naive
    # LLM polisher (message only, never in the scored path)
    llm: bool = False
    turn_budget_s: float = 2.0         # if a deterministic turn exceeds this, assume the harness may have dropped it


def from_env(base: Config | None = None) -> Config:
    cfg = base or Config()
    llm = os.environ.get("COPILOT_LLM") == "1" and os.environ.get("COPILOT_OFFLINE") != "1"
    return replace(cfg, llm=llm)
