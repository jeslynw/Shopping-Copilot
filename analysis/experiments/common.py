"""Shared harness for the PLAN.md §3 experiments — the reference implementation of every layer.

Everything runs through the REAL vendored evaluator (`evaluator/local_evaluator.py`, never
modified) on the 200 public sessions.  Each `exp_NN_*.py` builds one `Catalog`, evaluates a
list of `Config` variants with `run()` and prints a markdown table via `table()`.

Layers (each a `Config` flag, see PLAN.md §3 / §5):
  dialog policy   ask queue, boundary re-ask, re-ask-on-2, `other` exploit
  extraction      template regexes -> clause fallback, provenance tags; vocab category matcher
  retrieval       FTS5 OR-query (starter schema + weights), token cap, DF ordering, phrase terms,
                  hard category filter, pool size, pool ∪ category members
  rerank          verbatim constraint satisfaction, category sort key, popularity tie-break / blend,
                  norm() matcher over three or six fields, soft matching
  cutoff          R0..R8, information-gated, always-top-1 (degenerate reference row)
  exclusion       naive / override-safe / turn>=5 / previous-turn-only

Regenerated on 28 Aug 2026 from the §3 specifications (the original in-session scripts were
not persisted); numbers are re-measured, not copied.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import random
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace, asdict
from pathlib import Path
from typing import Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from evaluator import local_evaluator as ev  # noqa: E402  (vendored, unmodified)

CATALOG_PATH = ROOT / "data" / "catalog.jsonl"
PUBLIC_PATH = ROOT / "data" / "public_set.jsonl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

ATTRS = ("feature", "material", "color", "style", "size", "use_case", "budget")
TOP_K = 10
TOKEN_RE = re.compile(r"[a-z0-9]+")

# starter stoplist + a little generic English
GENERIC_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "i", "in", "is", "it",
    "me", "my", "of", "on", "or", "please", "some", "that", "the", "this", "to", "want", "with",
    "would", "you", "looking", "im", "am", "we", "our", "your", "its", "he", "she", "they", "them",
    "so", "if", "then", "than", "there", "here", "also", "just", "very", "can", "could", "should",
    "will", "do", "does", "did", "have", "has", "had", "not", "no", "yes", "up", "out", "any",
}
# words that only ever come from the simulator's templates (never from a constraint value)
TEMPLATE_STOP = {
    "key", "requirement", "matters", "actually", "ignore", "earlier", "preference", "need", "still",
    "exploring", "don", "additional", "judgment", "use", "options", "quite", "right", "yet", "ask",
    "about", "one", "specific", "attribute", "those", "what",
}
STOP = GENERIC_STOP | TEMPLATE_STOP


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in STOP]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold().strip()


def stem(tok: str) -> str:
    """Light plural stemmer: dresses→dress, watches→watch, necklaces→necklace, wallets→wallet; never touches 'ss'."""
    if len(tok) > 4 and tok.endswith(("sses", "shes", "ches", "xes", "zes")):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


# --------------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Config:
    label: str = ""
    # dialog policy
    accumulate: bool = True
    ask: bool = True
    ask_order: tuple = ATTRS
    ask_other: bool = False            # V4 rule exploit — reference row only
    boundary_reask: bool = True        # re-ask the attribute after "no preference ... use your judgment"
    reask_on_yield2: bool = False      # V2: re-ask while a reply yields 2 items
    # extraction
    extractor: str = "template"        # template | clause | hybrid
    # retrieval
    query_source: str = "messages"     # messages (accumulated message tokens) | extracted (category + constraint tokens)
    max_terms: int = 40
    df_order: bool = False             # when over the cap: keep newest-constraint tokens, fill by ascending DF
    phrase_terms: bool = False         # V7: constraints also as FTS5 phrase terms
    cat_hard_filter: bool = False      # V3: AND categories:"<coarse category>"
    pool: int = 300
    pool_union_category: bool = False  # pool = FTS top-N ∪ members of the matched category set
    # rerank
    rerank: bool = False
    cat_sort_key: bool = False
    match_mode: str = "exact"          # exact | soft
    soft_threshold: float = 0.8
    norm_match: bool = False           # norm() casefold + ws collapse; color:/budget normalisation; both detail forms
    match_fields: str = "three"        # three (title/features/details) | six (+description/categories/store)
    tiebreak: str = "bm25"             # bm25 | popularity | blend
    blend_w: float = 0.0
    # cutoff / exclusion
    cutoff: str = "none"               # none | R1..R8 | gated | gated2 | top1
    exclusion: str = "none"            # none | naive | override_safe | turn5 | prev_turn


def V0() -> Config:
    return Config(label="V0 stateless, never asks", accumulate=False, ask=False, boundary_reask=False)


def V1() -> Config:
    return Config(label="V1 accumulate + ask feature→material→color→…", boundary_reask=False)


def V2() -> Config:
    return replace(V1(), label="V2 = V1 + boundary re-ask + re-ask while reply yields 2", boundary_reask=True, reask_on_yield2=True)


def BASE() -> Config:  # "V2's boundary handling, V1's everything else"
    return replace(V1(), label="V1 + boundary re-ask", boundary_reask=True)


def V6() -> Config:
    return replace(BASE(), label="V6 rerank top-300 by #verbatim matches, category 2nd key", rerank=True, cat_sort_key=True)


def POP() -> Config:
    return replace(V6(), label="+ popularity tie-break", tiebreak="popularity")


def NORM() -> Config:
    return replace(POP(), label="+ norm() six-field matcher", norm_match=True, match_fields="six")


def R6() -> Config:
    return replace(NORM(), label="+ R6 cutoff (tier>10 & turn≤3 → top-1)", cutoff="R6")


def SHIPPED() -> Config:
    return replace(NORM(), label="SHIPPED: norm() + info-gated cutoff + previous-turn-only exclusion",
                   extractor="hybrid", cutoff="gated", exclusion="prev_turn")


# --------------------------------------------------------------------------------------------
# Catalog + FTS5 index (experiments keep per-product text in memory; copilot/ will not)
# --------------------------------------------------------------------------------------------
def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())   # intent_card form; identical FTS5 tokens
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


class CategoryMatcher:
    """coarse_category() vocabulary matcher: exact template → longest exact token-subsequence → order-aware fuzzy.

    Returns (candidates: tuple[str], provenance: 'template'|'exact'|'fuzzy'|'none').
    """

    def __init__(self, phrases: Iterable[str]):
        self.phrases = sorted(set(phrases), key=lambda p: (-len(p), p))
        self.seq = {p: tuple(TOKEN_RE.findall(p.lower())) for p in self.phrases}
        self.by_seq: dict[tuple, list[str]] = defaultdict(list)
        self.by_multiset: dict[tuple, list[str]] = defaultdict(list)
        for p, s in self.seq.items():
            self.by_seq[s].append(p)
            self.by_multiset[tuple(sorted(stem(t) for t in s))].append(p)
        self.norm_set = {norm(p): p for p in self.phrases}
        self.seqs_by_len: dict[int, list[tuple]] = defaultdict(list)
        for s in self.by_seq:
            if s:
                self.seqs_by_len[len(s)].append(s)

    def exact(self, phrase: str) -> tuple[str, ...]:
        p = self.norm_set.get(norm(phrase))
        return (p,) if p else ()

    def longest_substring(self, text: str) -> tuple[str, ...]:
        toks = tuple(TOKEN_RE.findall(text.lower()))
        best: tuple = ()
        for n in sorted(self.seqs_by_len, reverse=True):
            if n > len(toks) or (best and n < len(best)):
                break
            windows = {toks[i:i + n] for i in range(len(toks) - n + 1)}
            for s in self.seqs_by_len[n]:
                if s in windows:
                    best = s
                    break
            if best:
                break
        return tuple(self.by_seq[best]) if best else ()

    def fuzzy(self, text: str, threshold: float = 0.8) -> tuple[str, ...]:
        toks = [stem(t) for t in TOKEN_RE.findall(text.lower()) if t not in GENERIC_STOP]
        best_ratio, best_seq = 0.0, ()
        for s in self.by_seq:
            if not s:
                continue
            ss = [stem(t) for t in s]
            n = len(ss)
            for w in range(max(1, n - 1), n + 2):
                for i in range(max(1, len(toks) - w + 1)):
                    r = difflib.SequenceMatcher(None, ss, toks[i:i + w]).ratio()
                    if r > best_ratio or (r == best_ratio and n > len(best_seq)):
                        best_ratio, best_seq = r, s
        if best_ratio < threshold:
            return ()
        return tuple(self.by_multiset[tuple(sorted(stem(t) for t in best_seq))])

    def match(self, text: str) -> tuple[tuple[str, ...], str]:
        c = self.longest_substring(text)
        if c:
            return c, "exact"
        c = self.fuzzy(text)
        if c:
            return c, "fuzzy"
        return (), "none"


class Catalog:
    def __init__(self, path: Path = CATALOG_PATH, verbose: bool = True):
        t0 = time.perf_counter()
        self.ids, self.cats, self.products = ev.catalog_index(path)
        self.coarse = {a: ev.coarse_category(c) for a, c in self.cats.items()}
        self.members: dict[str, list[str]] = defaultdict(list)
        for a, c in self.coarse.items():
            self.members[c].append(a)
        self.pop = {a: int(p.get("rating_number") or 0) for a, p in self.products.items()}
        self.price = {a: p.get("price") for a, p in self.products.items()}
        self.matcher = CategoryMatcher(self.coarse.values())
        self._texts: dict[tuple, dict[str, str]] = {}
        self._toksets: dict[str, set] = {}
        self._build_fts()
        if verbose:
            print(f"[catalog] {len(self.ids)} products, {len(self.matcher.phrases)} coarse categories, "
                  f"loaded+indexed in {time.perf_counter() - t0:.1f}s", file=sys.stderr)

    def _build_fts(self) -> None:
        con = sqlite3.connect(":memory:")
        con.execute(
            "CREATE VIRTUAL TABLE products USING fts5(parent_asin UNINDEXED, title, categories, features, "
            "details, store, description, tokenize='unicode61 remove_diacritics 2')")
        rows = []
        for a, p in self.products.items():
            rows.append((a, _text(p.get("title")), _text(p.get("categories")), _text(p.get("features")),
                         _text(p.get("details")), _text(p.get("store")), _text(p.get("description"))))
        con.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?)", rows)
        con.execute("CREATE VIRTUAL TABLE v USING fts5vocab(products, 'row')")
        self.df = {term: doc for term, doc, _ in con.execute("SELECT term, doc, cnt FROM v")}
        con.commit()
        self.con = con

    def texts(self, fields: str, normalize: bool) -> dict[str, str]:
        key = (fields, normalize)
        if key not in self._texts:
            out = {}
            for a, p in self.products.items():
                parts = [_text(p.get("title")), _text(p.get("features")), _text(p.get("details"))]
                if isinstance(p.get("details"), dict):
                    parts.append(" ".join(f"{k} {v}" for k, v in p["details"].items()))  # searchable_text form
                if fields == "six":
                    parts += [_text(p.get("description")), _text(p.get("categories")), _text(p.get("store"))]
                t = " ".join(parts)
                out[a] = norm(t) if normalize else t.lower()
            self._texts[key] = out
        return self._texts[key]

    def tokset(self, asin: str) -> set:
        s = self._toksets.get(asin)
        if s is None:
            s = set(TOKEN_RE.findall(self.texts("six", True)[asin]))
            self._toksets[asin] = s
        return s

    def fts(self, expr: str, limit: int) -> list[tuple[str, float]]:
        return self.con.execute(
            "SELECT parent_asin, bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) AS s FROM products "
            "WHERE products MATCH ? ORDER BY s, parent_asin LIMIT ?", (expr, limit)).fetchall()


# --------------------------------------------------------------------------------------------
# Extraction (template regexes → clause fallback; provenance-tagged)
# --------------------------------------------------------------------------------------------
RE_BUY = re.compile(r"^I'm looking for (.+?)\. A key requirement is: (.+)\.$", re.S)
RE_BROWSE = re.compile(r"^I'm looking for (.+?), but I'm still exploring\.$", re.S)
RE_OVER_OPEN = re.compile(r"^I'm looking for (.+?)\. (.+)$", re.S)
RE_YIELD = re.compile(r"^For that, what matters is: (.+)\.$", re.S)
RE_EXH = re.compile(r"^I don't have an additional preference for (\w+)\.$")
RE_BOUND = re.compile(r"^I don't have a preference for (\w+); please use your judgment\.$")
RE_OVERRIDE = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (.+)\.$", re.S)
RE_NOINFO = re.compile(r"^Those options are not quite right yet")

BOILERPLATE = re.compile(
    r"\b(hi|hello|hey|honestly|mostly|also|today|"
    r"i'?m looking for|i am looking for|looking for|looking at|searching for|i'?d like to look at|i'?d like|i'?d say|"
    r"i need|i want|i'?m after|now i need|i'?m browsing|just exploring( options)?( in)?|show me( some)?|"
    r"can you help me find|help me find|it must have|non-?negotiable|one thing that'?s essential|the key thing for me is|"
    r"a key requirement is|what matters to me( is)?|here'?s what i care about|for that,? what matters is|"
    r"that'?s important to me|actually,? ignore my earlier preference|ignore my previous point|forget what i said( before)?|"
    r"scratch that earlier preference|change of plans|what i actually need is|what i need is|priority now|"
    r"but i'?m still exploring|no firm idea yet|still deciding|nothing specific yet|"
    r"i don'?t have (an additional |a )?preference (for|on)|no (particular )?preference (on|for)|nothing specific about|"
    r"i'?m flexible on|doesn'?t matter to me|whatever you think is best for|not fussy about|your call|please use your judgment|"
    r"use your judgment|those options are not quite right yet|ask me about one specific attribute|ask me something specific)\b",
    re.I)
ATTR_WORD = re.compile(r"\b(feature|material|color|size|style|use_case|budget|category|brand|other)\b", re.I)


@dataclass
class Parsed:
    kind: str                                  # open_buying|open_browsing|open_override|yield|exhausted|boundary|override|noinfo|unknown
    categories: tuple = ()
    cat_prov: str = "none"                     # template|exact|fuzzy|none
    constraints: list = field(default_factory=list)   # [(text, provenance)]
    attribute: Optional[str] = None
    template: bool = True                      # whole message recognised by a template


def split_constraints(body: str) -> list[str]:
    return [c.strip() for c in re.split(r";\s", body) if c.strip()]


def extract_template(msg: str, turn: int, cm: CategoryMatcher) -> Optional[Parsed]:
    m = msg.strip()
    if turn == 1:
        if (g := RE_BUY.match(m)):
            cat = cm.exact(g.group(1)) or cm.longest_substring(g.group(1))
            return Parsed("open_buying", cat, "template" if cat else "none", [(g.group(2).strip(), "template")])
        if (g := RE_BROWSE.match(m)):
            cat = cm.exact(g.group(1)) or cm.longest_substring(g.group(1))
            return Parsed("open_browsing", cat, "template" if cat else "none", [])
        if (g := RE_OVER_OPEN.match(m)):
            cat = cm.exact(g.group(1))
            if not cat:  # category itself may contain ". " → find the longest vocab prefix
                cat = cm.longest_substring(g.group(1))
            return Parsed("open_override", cat, "template" if cat else "none", [(g.group(2).strip(), "template")])
        return None
    if (g := RE_YIELD.match(m)):
        return Parsed("yield", constraints=[(c, "template") for c in split_constraints(g.group(1))])
    if (g := RE_EXH.match(m)):
        return Parsed("exhausted", attribute=g.group(1))
    if (g := RE_BOUND.match(m)):
        return Parsed("boundary", attribute=g.group(1))
    if (g := RE_OVERRIDE.match(m)):
        return Parsed("override", constraints=[(c, "template") for c in split_constraints(g.group(1))])
    if RE_NOINFO.match(m):
        return Parsed("noinfo")
    return None


def extract_clause(msg: str, turn: int, cm: CategoryMatcher) -> Parsed:
    """Template-free fallback: category by vocabulary, constraints = residual clauses."""
    cats, prov = ((), "none")
    text = msg
    if turn == 1:
        cats, prov = cm.match(msg)
        if cats:
            # remove the category phrase (any tied spelling) from the text so it is not a constraint
            for c in cats:
                text = re.sub(r"\s+".join(re.escape(t) for t in TOKEN_RE.findall(c.lower())), " ", text, flags=re.I)
    attr = None
    low = text.lower()
    if turn > 1 and re.search(r"preference|judgment|flexible|doesn'?t matter|not fussy|your call|nothing specific", low):
        a = ATTR_WORD.search(text)
        attr = a.group(1).lower() if a else None
        kind = "boundary" if re.search(r"judgment|your call|whatever you think", low) else "exhausted"
        return Parsed(kind, cats, prov, [], attr, template=False)
    if turn > 1 and re.search(r"not quite right|ask me (something|about)", low):
        return Parsed("noinfo", cats, prov, [], None, template=False)
    cleaned = BOILERPLATE.sub(" ", text)
    cons = []
    for clause in re.split(r"\.\s|\.$|;\s|[!?\n]|\s[—–-]\s", cleaned):
        c = clause.strip(" ,:-—–\"'")
        if len(c) < 3 or not TOKEN_RE.search(c.lower()):
            continue
        if all(t in STOP for t in TOKEN_RE.findall(c.lower())):
            continue
        cons.append((c, "clause"))
    kind = ("open_buying" if cons else "open_browsing") if turn == 1 else ("override" if re.search(
        r"forget|scratch|ignore|change of plans|actually|now i need|priority now", msg.lower()) else "yield")
    return Parsed(kind, cats, prov, cons, None, template=False)


def extract(msg: str, turn: int, mode: str, cm: CategoryMatcher) -> Parsed:
    if mode == "template":
        return extract_template(msg, turn, cm) or Parsed("unknown", template=False)
    if mode == "clause":
        return extract_clause(msg, turn, cm)
    return extract_template(msg, turn, cm) or extract_clause(msg, turn, cm)   # hybrid


# --------------------------------------------------------------------------------------------
# Session state + experiment agent
# --------------------------------------------------------------------------------------------
@dataclass
class State:
    turn: int = 0
    messages: list = field(default_factory=list)
    constraints: list = field(default_factory=list)       # [(text, provenance)] accumulate-only
    cat_set: tuple = ()
    cat_prov: str = "none"
    scenario: str = "unknown"                             # DIAGNOSTIC only (feeds exclusion=override_safe reference rows)
    consumed: set = field(default_factory=set)
    last_asked: Optional[str] = None
    boundary_attr: Optional[str] = None
    last_yield_count: int = 0
    override_seen_turn: Optional[int] = None
    shown: dict = field(default_factory=dict)             # turn -> [asin]
    diag: list = field(default_factory=list)


COLOR_WORDS = "black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange"


class ExpAgent:
    def __init__(self, cfg: Config, cat: Catalog, diag_targets: Optional[list] = None):
        self.cfg, self.cat = cfg, cat
        self.texts = cat.texts(cfg.match_fields, cfg.norm_match) if cfg.rerank else None
        self._targets = iter(diag_targets) if diag_targets is not None else None
        self.target: Optional[str] = None
        self.sessions: list[State] = []
        self.latencies: list[float] = []
        self.exceptions = 0

    # -- harness interface ----------------------------------------------------------------
    def reset(self, session_id: str, user_profile: dict) -> None:
        self.st = State()
        self.sessions.append(self.st)
        self.target = next(self._targets) if self._targets is not None else None

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        t0 = time.perf_counter()
        try:
            out = self._respond(user_message, turn, top_k)
        except Exception as e:  # counted; the official agent must never get here
            self.exceptions += 1
            out = {"message": f"error: {type(e).__name__}", "ask_attribute": "feature", "recommendations": [],
                   "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        self.latencies.append((time.perf_counter() - t0) * 1000)
        return out

    # -- per-turn pipeline ----------------------------------------------------------------
    def _respond(self, msg: str, turn: int, top_k: int) -> dict:
        cfg, st, cat = self.cfg, self.st, self.cat
        st.turn = turn
        if not cfg.accumulate:
            st.messages, st.constraints = [], []
        st.messages.append(msg)

        parsed = extract(msg, turn, cfg.extractor, cat.matcher)
        if turn == 1:
            st.cat_set, st.cat_prov = parsed.categories, parsed.cat_prov
            st.scenario = {"open_buying": "buying", "open_browsing": "browsing"}.get(parsed.kind, "override_suspect")
        seen = {c for c, _ in st.constraints}
        new = [(c, p) for c, p in parsed.constraints if c not in seen]
        st.constraints.extend(new)
        if parsed.kind == "yield" and st.last_asked:
            st.consumed.add(st.last_asked)
            st.last_yield_count = len(parsed.constraints)
        elif parsed.kind == "exhausted":
            st.consumed.add(parsed.attribute or st.last_asked)
            st.last_yield_count = 0
        elif parsed.kind == "boundary":
            st.last_yield_count = 0
            if cfg.boundary_reask:
                st.boundary_attr = parsed.attribute or st.last_asked
            else:
                st.consumed.add(parsed.attribute or st.last_asked)
        else:
            st.last_yield_count = 0
        if parsed.kind == "override":
            st.override_seen_turn = turn

        # ---- retrieve
        terms, phrases = self._terms(st, new)
        pool: list[tuple[str, int, float]] = []          # (asin, bm25_rank, bm25_score)
        if terms:
            expr = " OR ".join(f'"{t}"' for t in terms)
            if phrases:
                expr += "".join(f' OR "{p}"' for p in phrases)
            if cfg.cat_hard_filter and st.cat_set:
                cat_toks = TOKEN_RE.findall(st.cat_set[0].lower())
                if cat_toks:
                    expr = f'({expr}) AND categories:"{" ".join(cat_toks)}"'
            limit = cfg.pool if cfg.rerank else top_k
            pool = [(a, i, s) for i, (a, s) in enumerate(cat.fts(expr, limit))]
        if cfg.rerank and cfg.pool_union_category and st.cat_set:
            have = {a for a, _, _ in pool}
            extra = sorted({a for c in st.cat_set for a in cat.members.get(c, ())} - have)
            pool += [(a, len(pool) + 10_000, 0.0) for a in extra]

        # ---- rank
        tier_size = 0
        if cfg.rerank:
            ranked, tier_size = self._rerank(pool, st)
        else:
            ranked = [a for a, _, _ in pool]

        # ---- exclusion (implicit negative feedback)
        excl = self._exclusion(st, turn)
        if excl:
            ranked = [a for a in ranked if a not in excl]

        # ---- cutoff
        k = self._cutoff_k(st, turn, tier_size, parsed, top_k)
        recs = ranked[:k]

        # ---- ask
        ask = self._next_ask(st, turn)
        st.last_asked = ask
        st.boundary_attr = None
        st.shown[turn] = list(recs)
        if self.target is not None:
            pool_asins = [a for a, _, _ in pool]
            st.diag.append({"turn": turn, "in_pool": self.target in pool_asins,
                            "rank": (ranked.index(self.target) + 1) if self.target in ranked else None,
                            "tier": tier_size, "k": k, "n_cons": len(st.constraints), "kind": parsed.kind,
                            "top1": ranked[0] if ranked else None,
                            "terms": terms})
        return {"message": f"Here are my best matches. ({len(recs)} shown, {len(st.constraints)} constraints)",
                "ask_attribute": ask, "recommendations": [{"parent_asin": a} for a in recs],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    # -- retrieval terms --------------------------------------------------------------------
    def _terms(self, st: State, new: list) -> tuple[list[str], list[str]]:
        cfg, cat = self.cfg, self.cat
        phrases: list[str] = []
        if cfg.query_source == "messages":
            toks = tokens(" ".join(st.messages))
            terms = list(dict.fromkeys(toks))
        else:
            must = list(dict.fromkeys(t for c, _ in new for t in tokens(c)))
            rest = list(dict.fromkeys([t for c in st.cat_set for t in tokens(c)] +
                                      [t for c, _ in st.constraints for t in tokens(c)]))
            rest = [t for t in rest if t not in must]
            if cfg.df_order:
                rest.sort(key=lambda t: (cat.df.get(t, 0), t))
            terms = (must + rest)
        if len(terms) > cfg.max_terms:
            if cfg.df_order and cfg.query_source == "messages":
                terms = sorted(terms, key=lambda t: (cat.df.get(t, 0), t))
            terms = terms[:cfg.max_terms]
        if cfg.phrase_terms:
            for c, _ in st.constraints:
                ct = TOKEN_RE.findall(c.lower())
                if 2 <= len(ct) <= 8:
                    phrases.append(" ".join(ct))
        return terms, phrases

    # -- constraint satisfaction rerank -----------------------------------------------------
    def _matchers(self, st: State) -> list[Callable[[str, str], bool]]:
        cfg, cat = self.cfg, self.cat
        out = []
        for c, _ in st.constraints:
            if cfg.match_mode == "soft":
                ct = set(TOKEN_RE.findall(c.lower()))
                if not ct:
                    continue
                thr = cfg.soft_threshold
                out.append(lambda text, asin, ct=ct, thr=thr: len(ct & cat.tokset(asin)) / len(ct) >= thr)
                continue
            if cfg.norm_match:
                n = norm(c)
                if (g := re.fullmatch(rf"color: ({COLOR_WORDS})", n)):
                    rx = re.compile(rf"\b{g.group(1)}\b")
                    out.append(lambda text, asin, rx=rx: bool(rx.search(text)))
                    continue
                if (g := re.fullmatch(r"budget around \$([0-9.]+)", n)):
                    try:
                        p = float(g.group(1))
                    except ValueError:
                        p = None
                    if p:
                        out.append(lambda text, asin, p=p: isinstance(cat.price.get(asin), (int, float)) and
                                   abs(float(cat.price[asin]) - p) <= 0.2 * p)
                        continue
                out.append(lambda text, asin, n=n: n in text)
            else:
                lc = c.lower()
                out.append(lambda text, asin, lc=lc: lc in text)
        return out

    def _rerank(self, pool: list, st: State) -> tuple[list[str], int]:
        cfg, cat, texts = self.cfg, self.cat, self.texts
        matchers = self._matchers(st)
        cat_set = set(st.cat_set)
        keyed = []
        for asin, rank, score in pool:
            text = texts[asin]
            n = sum(1 for m in matchers if m(text, asin))
            cm = 1 if (cfg.cat_sort_key and cat.coarse[asin] in cat_set) else 0
            if cfg.tiebreak == "popularity":
                key = (-n, -cm, -cat.pop[asin], rank, asin)
            elif cfg.tiebreak == "blend":
                key = (-n, -cm, score - cfg.blend_w * math.log1p(cat.pop[asin]), asin)
            else:
                key = (-n, -cm, rank, asin)
            keyed.append((key, asin, n, cm))
        keyed.sort(key=lambda x: x[0])
        if not keyed:
            return [], 0
        top_n, top_cm = keyed[0][2], keyed[0][3]
        tier = sum(1 for _, _, n, cm in keyed if n == top_n and cm == top_cm)
        return [a for _, a, _, _ in keyed], tier

    # -- cutoff -----------------------------------------------------------------------------
    def _cutoff_k(self, st: State, turn: int, tier: int, parsed: Parsed, top_k: int) -> int:
        r, n = self.cfg.cutoff, len(st.constraints)
        if r in ("none", "R0"):
            return top_k
        if r == "top1":
            return 1
        if r == "R1":
            return 3 if (turn == 1 and n == 0) else top_k
        if r == "R2":
            return 1 if (turn == 1 and n == 0) else top_k
        if r == "R3":
            return 0 if (turn == 1 and n == 0) else top_k
        if r == "R4":
            return 3 if (turn <= 2 and n < 2) else top_k
        if r == "R5":
            return 3 if (tier > 10 and turn <= 2) else top_k
        if r == "R6":
            return 1 if (tier > 10 and turn <= 3) else top_k
        if r == "R7":
            return 1 if (tier > 30 and turn <= 2) else top_k
        if r == "R8":
            return 1 if turn == 1 else top_k
        if r in ("gated", "gated2"):
            if not (tier > 10 and turn <= 3):
                return top_k
            all_template = all(p == "template" for _, p in st.constraints) and st.cat_prov in ("template", "exact")
            yielded = turn == 1 or (parsed.template and any(p == "template" for _, p in parsed.constraints))
            if r == "gated2":
                yielded = yielded or (parsed.template and parsed.kind in ("exhausted", "boundary"))
            return 1 if (all_template and yielded) else top_k
        raise ValueError(r)

    # -- exclusion --------------------------------------------------------------------------
    def _exclusion(self, st: State, turn: int) -> set:
        r = self.cfg.exclusion
        if r == "none" or turn == 1:
            return set()
        if r == "prev_turn":
            return set(st.shown.get(turn - 1, ()))
        if r == "naive":
            return {a for t, s in st.shown.items() if t < turn for a in s}
        if r == "turn5":
            return {a for t, s in st.shown.items() if 4 <= t < turn for a in s} if turn >= 5 else set()
        if r == "override_safe":
            def ok(t: int) -> bool:
                return (st.scenario in ("buying", "browsing")
                        or (st.override_seen_turn is not None and t >= st.override_seen_turn)
                        or t >= 4)
            return {a for t, s in st.shown.items() if t < turn and ok(t) for a in s}
        raise ValueError(r)

    # -- ask policy -------------------------------------------------------------------------
    def _next_ask(self, st: State, turn: int) -> Optional[str]:
        cfg = self.cfg
        if not cfg.ask:
            return None
        if cfg.ask_other:
            return "other"
        if st.boundary_attr and cfg.boundary_reask:
            return st.boundary_attr
        if cfg.reask_on_yield2 and st.last_yield_count == 2 and st.last_asked and st.last_asked in cfg.ask_order:
            return st.last_asked
        for a in cfg.ask_order:
            if a not in st.consumed:
                return a
        return cfg.ask_order[turn % len(cfg.ask_order)]   # never null; re-asking is harmless


# --------------------------------------------------------------------------------------------
# Paraphrase harness (dev-time proxy for organizer paraphrasing; monkeypatches the simulator
# strings in-process — the evaluator file is never edited)
# --------------------------------------------------------------------------------------------
P_BUY = ["Hi! I need {cat}. It must have: {c}.", "Searching for {cat} — one thing that's essential: {c}",
         "Can you help me find {cat}? Non-negotiable: {c}.", "I want {cat}; the key thing for me is {c}."]
P_BROWSE = ["I'm browsing {cat}, no firm idea yet.", "Just exploring options in {cat}.",
            "Show me some {cat} — still deciding.", "Hi, I'd like to look at {cat}. Nothing specific yet!"]
P_OVER_OPEN = ["Hi, I want {cat}. {old}", "Show me {cat}. {old}", "Looking at {cat} today. {old}", "I'd like {cat} — {old}"]
P_YIELD = ["What matters to me: {c}.", "Here's what I care about — {c}", "Mostly {c}.", "I'd say {c}; that's important to me."]
P_EXH = ["No particular preference on {a}.", "Nothing specific about {a}, honestly.", "I'm flexible on {a}.",
         "{a}? Doesn't matter to me."]
P_BOUND = ["No preference on {a} — your call.", "Whatever you think is best for {a}.", "Not fussy about {a}; use your judgment."]
P_OVERRIDE = ["Forget what I said before. Now I need: {new}.", "Scratch that earlier preference; I'm after: {new}.",
              "Change of plans — what I actually need is {new}.", "Ignore my previous point. Priority now: {new}."]
P_NOINFO = ["Hmm, not quite. Ask me something specific.", "Those aren't right yet — ask about one attribute."]


def _pick(templates: list[str], key: str) -> str:
    return templates[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(templates)]


class Paraphraser:
    """install() swaps the simulator's string builders for paraphrased ones; uninstall() restores them."""

    def __init__(self, lowercase_category: bool = True):
        self.lc = lowercase_category
        self._orig = (ev.initial_message, ev.customer_reply, ev.behavior_for)

    def _cat(self, cat: str, key: str) -> str:
        return cat.lower() if (self.lc and int(hashlib.md5(key.encode()).hexdigest(), 16) % 2) else cat

    def initial_message(self, sample, category, disclosed):
        scenario = sample["scenario_type"]
        sid = sample.get("sample_id", "")
        if scenario == "buying" and sample["intent_card"].get("hard_constraints"):
            c = str(sample["intent_card"]["hard_constraints"][0])
            disclosed.add(c)
            return _pick(P_BUY, sid + "b").format(cat=self._cat(category, sid), c=c)
        if scenario == "intent_override":
            old = str(sample["behavior"]["override"]["old_value"])
            return _pick(P_OVER_OPEN, sid + "o").format(cat=self._cat(category, sid), old=old)
        return _pick(P_BROWSE, sid + "w").format(cat=self._cat(category, sid))

    def customer_reply(self, sample, ask_attribute, disclosed, boundary_used):
        attribute = ask_attribute if isinstance(ask_attribute, str) else None
        sid = sample.get("sample_id", "")
        if sample["scenario_type"] == "boundary" and not boundary_used and attribute:
            return _pick(P_BOUND, sid + attribute).format(a=attribute), True
        if not attribute:
            return _pick(P_NOINFO, sid), boundary_used
        if attribute not in ev.ALLOWED_ATTRIBUTES:
            attribute = "other"
        constraints = [*map(str, sample["intent_card"].get("hard_constraints", [])),
                       *map(str, sample["intent_card"].get("soft_preferences", []))]
        matches = [v for v in constraints if v not in disclosed and
                   (attribute == "other" or ev.classify_constraint(v) == attribute)][:2]
        if not matches:
            return _pick(P_EXH, sid + attribute + "x").format(a=attribute), boundary_used
        disclosed.update(matches)
        return _pick(P_YIELD, sid + "; ".join(matches)).format(c="; ".join(matches)), boundary_used

    def behavior_for(self, scenario, card, rng):
        b = self._orig[2](scenario, card, rng)
        if "override" in b:
            new = b["override"]["new_value"]
            b["override"]["message"] = _pick(P_OVERRIDE, new).format(new=new)
        return b

    def install(self) -> "Paraphraser":
        ev.initial_message, ev.customer_reply, ev.behavior_for = self.initial_message, self.customer_reply, self.behavior_for
        return self

    def uninstall(self) -> None:
        ev.initial_message, ev.customer_reply, ev.behavior_for = self._orig


# --------------------------------------------------------------------------------------------
# Runner, metrics, tables
# --------------------------------------------------------------------------------------------
def load_samples() -> list[dict]:
    return ev.load_jsonl(PUBLIC_PATH)


def run(cfg: Config, cat: Catalog, samples: list[dict], label: Optional[str] = None, paraphrase: bool = False,
        diag: bool = False, agent_wrapper: Optional[Callable] = None, verbose: bool = True) -> dict:
    """Evaluate one Config through the REAL evaluate(). Returns the evaluator result + extras."""
    targets = [str(s["ground_truth"]["parent_asin"]) for s in samples] if diag else None
    agent = ExpAgent(cfg, cat, diag_targets=targets)
    subject = agent_wrapper(agent) if agent_wrapper else agent
    para = Paraphraser().install() if paraphrase else None
    t0 = time.perf_counter()
    try:
        res = ev.evaluate(subject, samples, cat.ids, cat.cats, cat.products)
    finally:
        if para:
            para.uninstall()
    lat = sorted(agent.latencies) or [0.0]
    res.update({
        "label": label or cfg.label,
        "config": asdict(cfg),
        "paraphrase": paraphrase,
        "p50_ms": round(lat[len(lat) // 2], 1),
        "p95_ms": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
        "wall_s": round(time.perf_counter() - t0, 1),
        "agent_exceptions": agent.exceptions,
        "override_hr": res["scenario_metrics"].get("intent_override", {}).get("hit_rate_at_10"),
        "hit_turns": dict(sorted(Counter(s["first_hit_turn"] for s in res["sessions"] if s["hit"]).items())),
        "rank_at_hit": dict(sorted(Counter(s["best_rank"] for s in res["sessions"] if s["hit"]).items())),
    })
    if diag:
        res["_agent"] = agent
    if verbose:
        print(f"  {res['label']:<70} TS {res['recommended_technical_score']:.3f}  HR {res['hit_rate_at_10']:.3f}  "
              f"MRR {res['mrr']:.3f}  MTTC {res['mttc']:.2f}  ovr {res['override_hr']:.2f}  "
              f"p50/p95 {res['p50_ms']}/{res['p95_ms']} ms  ({res['wall_s']}s)", file=sys.stderr)
    return res


def technical_score(hits: list[int], rr: list[float], turns: list[int]) -> float:
    hr, mrr, mttc = statistics.fmean(hits), statistics.fmean(rr), statistics.fmean(turns)
    eff = max(0.0, min(1.0, (11.0 - mttc) / 10.0))
    return 0.5 * hr + 0.3 * mrr + 0.2 * eff


def bootstrap_ci(sessions: list[dict], n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    rng = random.Random(seed)
    hits = [1 if s["hit"] else 0 for s in sessions]
    rr = [s["reciprocal_rank"] for s in sessions]
    turns = [s["first_hit_turn"] if s["first_hit_turn"] is not None else ev.MAX_TURNS + 1 for s in sessions]
    N = len(sessions)
    scores = []
    for _ in range(n):
        idx = [rng.randrange(N) for _ in range(N)]
        scores.append(technical_score([hits[i] for i in idx], [rr[i] for i in idx], [turns[i] for i in idx]))
    scores.sort()
    return technical_score(hits, rr, turns), scores[int(0.025 * n)], scores[int(0.975 * n) - 1]


def table(rows: list[dict], extra_cols: Iterable[str] = ()) -> str:
    cols = ["Variant", "HR@10", "MRR", "MTTC", "TechScore", "override HR", "p50/p95 ms", *extra_cols]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        cells = [r["label"], f"{r['hit_rate_at_10']:.3f}", f"{r['mrr']:.3f}", f"{r['mttc']:.2f}",
                 f"**{r['recommended_technical_score']:.3f}**", f"{r['override_hr']:.2f}",
                 f"{r['p50_ms']}/{r['p95_ms']}", *[str(r.get(c, "")) for c in extra_cols]]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def per_scenario(res: dict) -> str:
    sm = res["scenario_metrics"]
    return " · ".join(f"{k} HR {v['hit_rate_at_10']:.3f}/MRR {v['mrr']:.2f}/MTTC {v['mttc']:.2f}" for k, v in sm.items())


def save(name: str, rows: list[dict], notes: Optional[dict] = None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    slim = [{k: v for k, v in r.items() if k not in ("sessions", "_agent")} for r in rows]
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps({"experiment": name, "rows": slim, "notes": notes or {}}, indent=1) + "\n")
    return path


def header(title: str) -> None:
    print(f"\n## {title}\n")
