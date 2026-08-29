"""Every layer is a flag; defaults are the shipped configuration (docs/PLAN.md §3n, revised §11 for the LLM layer)."""
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
    pool_union_category: bool = False  # measured: clean −0.003, paraphrased −0.015 (MRR) → flag only, re-test in P3
    # rerank
    rerank: bool = True
    cat_sort_key: bool = True
    norm_match: bool = True
    match_fields: str = "six"          # six | three
    tiebreak: str = "popularity"       # popularity | bm25 | blend
    blend_w: float = 0.0
    # cutoff / exclusion
    cutoff: str = "gated"              # none | R6 | gated | gated2 | top1
    exclusion: str = "prev_turn"       # none | prev_turn | turn5 | naive
    # LLM layer (Claude API). Master switch `llm` comes from the environment (see from_env); each use is its own flag.
    llm: bool = False
    llm_extract: bool = True           # grounded extraction fallback — only when no simulator template matched (paraphrase)
    llm_polish: bool = True            # rewrite the customer-facing `message` only
    llm_rerank: bool = False           # ABLATION: LLM orders the top tier; measured, never on by default
    llm_budget_s: float = 4.0          # per-turn wall-clock budget for ALL LLM calls
    turn_budget_s: float = 8.0         # if a whole turn exceeds this, assume the harness may have dropped it (don't mark prev)


def llm_enabled_from_env() -> bool:
    """On when an API key is present, unless COPILOT_OFFLINE=1 or COPILOT_LLM=0. COPILOT_LLM=1 forces on."""
    if os.environ.get("COPILOT_OFFLINE") == "1":
        return False
    flag = os.environ.get("COPILOT_LLM")
    if flag is not None:
        return flag.strip() == "1"
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def from_env(base: Config | None = None) -> Config:
    return replace(base or Config(), llm=llm_enabled_from_env())
