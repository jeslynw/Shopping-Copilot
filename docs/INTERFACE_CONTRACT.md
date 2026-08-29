# Interface contract — `copilot/` package (P0 deliverable, docs/PLAN.md §5/§6)

One page so tracks B (robustness), C (LLM polisher) and D (tooling/demo) can code against the core
before A finishes it. Names here are binding; change them only via a PR that also updates this file.
Reference implementation of every layer: `analysis/experiments/common.py` (same names, in-memory).

## Invariants (never negotiable)
- `Agent.__init__`, `reset`, `respond` never raise. `respond` always returns exactly the four keys
  `{"message": str, "ask_attribute": str, "recommendations": [{"parent_asin": str}, …], "usage": {"prompt_tokens": int, "completion_tokens": int}}`
  — no extra keys anywhere (contract has `additionalProperties: false`). `ask_attribute` is never `null`.
- Scored configuration = deterministic core, LLM **off**. `COPILOT_LLM=1` opts in; LLM output is assigned to `message` only.
- Accumulate-only state: nothing is ever erased on "ignore my earlier preference".
- No scenario / override-message detection anywhere in the scoring path (ranking, cutoff, exclusion).
- `state.prev` (last turn's recommendations) is written **only** after the outgoing dict validates; the fallback path never writes it.
- Final sort key ends in `parent_asin`; never iterate a `set` in ranking code.

## `copilot/config.py`
```python
@dataclass(frozen=True)
class Config:                         # shipped defaults; every §3 layer is a flag (ablate.py flips them)
    ask_order: tuple[str, ...] = ("feature", "material", "color", "style", "size", "use_case", "budget")
    boundary_reask: bool = True       # re-ask after "no preference … use your judgment"
    reask_on_yield2: bool = False     # V2 (neutral)
    extractor: str = "hybrid"         # template | clause | hybrid (template first, clause fallback)
    query_source: str = "extracted"   # extracted (category + constraint tokens) | messages (V1-style)
    max_terms: int = 32               # newest-constraint tokens always kept; fill by ascending DF
    pool: int = 300                   # FTS5 top-N, ORDER BY bm25, parent_asin
    pool_union_category: bool = False # pool ∪ matched-category members — measured neutral/negative (exp_10), flag only
    rerank: bool = True               # verbatim constraint-satisfaction rerank
    cat_sort_key: bool = True         # coarse-category match as 2nd key
    norm_match: bool = True           # norm() = casefold + whitespace collapse; color:/budget forms; both detail forms
    match_fields: str = "six"         # title, features, details, description, categories, store
    tiebreak: str = "popularity"      # popularity (rating_number, lexicographic) | bm25 | blend
    blend_w: float = 0.0
    cutoff: str = "gated"             # none | R6 | gated | top1 (reference rows)
    exclusion: str = "prev_turn"      # none | prev_turn | turn5 | naive (reference row)
    llm: bool = False                 # on iff an API key is present (OPENAI_API_KEY / ANTHROPIC_API_KEY, .env read); COPILOT_LLM=1/0, COPILOT_OFFLINE=1
    llm_extract: bool = False         # grounded extraction fallback — ablation flag (measured 0.918 vs deterministic 0.924 on the fixture)
    llm_polish: bool = True           # rewrite `message` only
    llm_rerank: bool = False          # ablation flag
```

## `copilot/state.py`
```python
@dataclass
class SessionState:
    session_id: str
    turn: int = 0
    messages: list[str]                            # raw, accumulate-only
    constraints: list[Constraint]                  # Constraint(text: str, provenance: "template"|"clause", turn: int); de-duplicated, ordered
    categories: tuple[str, ...] = ()               # matched coarse_category() phrases (tie set); "" never
    cat_prov: str = "none"                         # template | exact | fuzzy | none
    consumed: set[str]                             # attributes whose REPLY was parsed (marked on parse, not on send)
    last_asked: str | None = None
    boundary_attr: str | None = None               # set when a boundary reply is parsed → re-ask once
    last_parsed: Parsed | None = None
    prev: list[str]                                # previous turn's recommendations (exclusion); [] after a fallback turn
    usage: tuple[int, int] = (0, 0)
```

## `copilot/extract.py`
```python
@dataclass
class Parsed:
    kind: str            # open_buying | open_browsing | open_override | yield | exhausted | boundary | override | noinfo | unknown
    categories: tuple[str, ...] = ()
    cat_prov: str = "none"
    constraints: list[tuple[str, str]] = []        # (verbatim text, provenance "template"|"clause")
    attribute: str | None = None                   # for exhausted/boundary
    template: bool = True                          # whole message matched a simulator template

def extract(message: str, turn: int, mode: str, matcher: CategoryMatcher) -> Parsed
class CategoryMatcher:                             # built from coarse_category() over the catalog (1,115 phrases)
    def exact(self, phrase: str) -> tuple[str, ...]              # template path
    def longest_substring(self, text: str) -> tuple[str, ...]    # longest vocab token-subsequence in the message
    def fuzzy(self, text: str, threshold=0.8) -> tuple[str, ...] # order-aware difflib over stemmed tokens → tie set
    def match(self, text: str) -> tuple[tuple[str, ...], str]    # (candidates, provenance)
```
`kind` and `cat_prov` are **diagnostic / phrasing / gate** inputs only — never fed to exclusion.

## `copilot/catalog.py`
```python
def resolve_catalog_path(given: str | Path) -> Path      # .jsonl / .jsonl.gz, gzip magic sniff, CWD and __file__-relative
class Catalog:
    def __init__(self, path)                             # FTS5 (starter schema + weights); Python keeps only asin→(rowid, rating_number, coarse), df, matcher
    ids: set[str]; pop: dict[str, int]; coarse: dict[str, str]; members: dict[str, list[str]]; df: dict[str, int]; matcher: CategoryMatcher
    def search(self, terms: list[str], limit: int) -> list[tuple[str, float]]    # (parent_asin, bm25) — tokens-only MATCH, never raw text
    def texts(self, asins: list[str]) -> dict[str, str]                          # six-field matcher text, norm()-ed, fetched from FTS5 per turn
    price(self, asin) -> float | None
```

## `copilot/retrieve.py`
```python
def build_terms(state: SessionState, new: list[Constraint], cfg: Config, df: dict[str, int]) -> list[str]
def retrieve(catalog: Catalog, terms: list[str], state: SessionState, cfg: Config) -> list[Candidate]   # Candidate(asin, bm25_rank, bm25)
```

## `copilot/rank.py`
```python
def norm(text: str) -> str
def compile_matchers(constraints: list[Constraint], cfg: Config, catalog: Catalog) -> list[Matcher]   # Matcher(text, asin) -> bool; label = constraint text
@dataclass
class Ranked: asin: str; n_match: int; cat_score: int; pop: int; bm25_rank: int; matched: tuple[str, ...]   # `matched` = explanation
def rank(cands: list[Candidate], state, cfg, catalog) -> tuple[list[Ranked], int]   # (sorted best→worst, tier_size)
# sort key: (-n_match, -cat_score, -rating_number, bm25_rank, parent_asin); tier_size = |top (n_match, cat_score) tier|
```

## `copilot/policy.py`
```python
def next_ask(state: SessionState, cfg: Config) -> str                                   # never None
def cutoff_k(cfg: Config, state, turn: int, tier_size: int, parsed: Parsed, top_k: int) -> int
#   gated: 1 iff tier_size > 10 and turn ≤ 3 and (turn == 1 or parsed yielded ≥ 1 template constraint)
#          and every counted constraint is template-tagged and cat_prov ∈ {template, exact}; else top_k
def exclusion(cfg: Config, state, turn: int) -> set[str]                                # prev_turn → set(state.prev)
def apply_reply(state: SessionState, parsed: Parsed, cfg: Config) -> list[Constraint]   # updates consumed/boundary/constraints; returns NEW constraints
```

## `copilot/respond.py`
```python
def build_message(state, parsed, ask: str, top: list[Ranked], k: int, tier_size: int) -> str
#   deterministic; includes "matched on: …" from Ranked.matched; never asserts "found it" before turn 3
```

## `copilot/llm.py` (track C)
```python
class Polisher:
    def __init__(self, cfg: Config, budget_s: float = 1.5)   # disabled unless COPILOT_LLM=1 and not COPILOT_OFFLINE=1; lazy `import anthropic`
    enabled: bool
    def rewrite(self, draft: str, facts: dict) -> str | None  # ONE call/turn; returns None on ANY failure/timeout/budget miss/disabled; never raises
    last_usage: tuple[int, int]                              # (prompt_tokens, completion_tokens) of the last successful call, else (0, 0)
    def summary(self) -> dict                                # calls, failures, p95_ms, breaker_open — printed once per run
```
Failure budget 3 per 20 calls → breaker opens for the run. Product text and user messages are passed as
delimited data; the result is post-filtered (URLs, `store` names) before assignment to `message`.

## `copilot/agent.py` + shims
```python
class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl", config: Config | None = None)
    def reset(self, session_id: str, user_profile: dict) -> None
    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict
```
Per-turn flow: `extract → apply_reply → build_terms → retrieve → rank → exclusion → cutoff_k → next_ask → build_message → (llm.rewrite) → validate → state.prev = recs`.
Root `agent.py` and `starter/agent.py` are shims: `sys.path.insert(0, <their dir / parent>)` then `from copilot.agent import Agent`.

## Tools (track D) against this contract
`tools/run_eval.py` (official evaluator + contract validation on every response + `--profile`: p50/p95, RSS incl. harness, internal-exception count) ·
`tools/ablate.py` (ladder from `Config` flags incl. not-shipped rows; `--per-session` cutoff accounting) ·
`tools/paraphrase_eval.py` (reads `data/paraphrases.jsonl`; monkeypatches simulator in-process) ·
`tools/demo.py --session public_0042 [--redact-brands]` · `tools/validate_contract.py`.
