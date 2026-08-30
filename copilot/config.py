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
    profile_prior: bool = False        # ABLATION: `user_profile.preference_tags` as a soft sort key between category and
                                       # popularity (never a filter; cannot change the tie width that drives the cutoff)
    vector_route: bool = False         # ABLATION: second retrieval route — TF-IDF cosine over title+features+categories,
                                       # top `vector_top` unioned into the BM25 pool (recall only; index built lazily)
    vector_top: int = 100
    # cutoff / exclusion
    cutoff: str = "gated"              # none | R6 | gated | gated2 | top1
    exclusion: str = "prev_turn"       # none | prev_turn | turn5 | naive
    # LLM layer (Claude API). Master switch `llm` comes from the environment (see from_env); each use is its own flag.
    llm: bool = False
    llm_extract: bool = False          # grounded extraction fallback when no template matched — MEASURED 0.918 vs deterministic 0.924 on the
                                       # paraphrase fixture (29 Aug): no gain, +1 s/turn → ablation flag, off (docs/results/paraphrase_*.json)
    llm_polish: bool = True            # rewrite the customer-facing `message` only
    llm_rerank: bool = False           # ABLATION: LLM orders the top tier; measured, never on by default
    llm_budget_s: float = 4.0          # per-turn wall-clock budget for ALL LLM calls
    turn_budget_s: float = 8.0         # if a whole turn exceeds this, assume the harness may have dropped it (don't mark prev)


def load_dotenv(path: "str | os.PathLike | None" = None) -> None:
    """Read KEY=VALUE lines from <repo root>/.env (git-ignored) into os.environ without overriding existing variables."""
    from pathlib import Path
    p = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    try:
        if not p.is_file():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lstrip("export ").strip()
            v = v.split(" #", 1)[0].strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    except Exception:
        return


def llm_provider_from_env() -> "str | None":
    """openai | anthropic | None. COPILOT_LLM_PROVIDER overrides; otherwise whichever key is present (OpenAI first)."""
    load_dotenv()
    explicit = os.environ.get("COPILOT_LLM_PROVIDER", "").strip().lower()
    if explicit in ("openai", "anthropic"):
        return explicit
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    return None


def llm_enabled_from_env() -> bool:
    """On when a provider key is present, unless COPILOT_OFFLINE=1 or COPILOT_LLM=0. COPILOT_LLM=1 forces on."""
    load_dotenv()
    if os.environ.get("COPILOT_OFFLINE") == "1":
        return False
    flag = os.environ.get("COPILOT_LLM")
    if flag is not None and flag.strip() != "":
        return flag.strip() == "1"
    return llm_provider_from_env() is not None


def from_env(base: Config | None = None) -> Config:
    return replace(base or Config(), llm=llm_enabled_from_env())
