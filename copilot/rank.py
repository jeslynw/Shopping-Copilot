from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable

from .catalog import Catalog
from .config import Config
from .extract import TOKEN_RE, norm  # noqa: F401  (norm re-exported for tools)
from .retrieve import Candidate
from .state import Constraint, SessionState

COLOR_WORDS = "black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange"

# profile_prior (ablation): lexical stem per preference tag; a tag counts when its stem appears in the item's match text.
PROFILE_STEMS = {"fit": "fit", "comfort": "comfort", "durability": "durab", "style": "styl",
                 "material": "material", "performance": "perform", "warmth": "warm", "weather": "weather"}


@dataclass(frozen=True)
class Matcher:
    label: str
    fn: Callable[[str, str], bool]


def compile_matchers(constraints: list[Constraint], cfg: Config, catalog: Catalog) -> list[Matcher]:
    out: list[Matcher] = []
    for c in constraints:
        if not cfg.norm_match:
            lc = c.text.lower()
            out.append(Matcher(c.text, lambda text, asin, lc=lc: lc in text))
            continue
        n = norm(c.text)
        if not n:
            continue
        if (g := re.fullmatch(rf"color: ({COLOR_WORDS})", n)):
            rx = re.compile(rf"\b{g.group(1)}\b")
            out.append(Matcher(c.text, lambda text, asin, rx=rx: bool(rx.search(text))))
        elif (g := re.fullmatch(r"budget around \$([0-9]+(?:\.[0-9]+)?)", n)):
            p = float(g.group(1))
            if p > 0:
                out.append(Matcher(c.text, lambda text, asin, p=p: asin in catalog.price and
                                   abs(catalog.price[asin] - p) <= 0.2 * p))
        else:
            out.append(Matcher(c.text, lambda text, asin, n=n: n in text))
    return out


@dataclass(frozen=True)
class Ranked:
    asin: str
    n_match: int
    cat_score: int
    pop: int
    bm25_rank: int
    matched: tuple


def rank(cands: list[Candidate], state: SessionState, cfg: Config, catalog: Catalog) -> tuple[list[Ranked], int]:
    if not cands:
        return [], 0
    matchers = compile_matchers(state.constraints, cfg, catalog)
    stems = tuple(PROFILE_STEMS[t] for t in state.profile_tags if t in PROFILE_STEMS) if cfg.profile_prior else ()
    texts = catalog.texts([c.asin for c in cands], cfg.match_fields) if (matchers or stems) else {}
    cat_set = set(state.categories) if cfg.cat_sort_key else set()
    keyed = []
    for c in cands:
        text = texts.get(c.asin, "")
        matched = tuple(m.label for m in matchers if m.fn(text, c.asin))
        n = len(matched)
        cm = 1 if catalog.coarse.get(c.asin) in cat_set else 0
        ph = sum(1 for s in stems if s in text) if stems else 0    # profile prior: soft key only, never a filter
        pop = catalog.pop.get(c.asin, 0)
        if cfg.tiebreak == "popularity":
            key = (-n, -cm, -ph, -pop, c.bm25_rank, c.asin)
        elif cfg.tiebreak == "blend":
            key = (-n, -cm, -ph, c.bm25 - cfg.blend_w * math.log1p(pop), c.asin)
        else:
            key = (-n, -cm, -ph, c.bm25_rank, c.asin)
        keyed.append((key, Ranked(c.asin, n, cm, pop, c.bm25_rank, matched)))
    keyed.sort(key=lambda x: x[0])
    ranked = [r for _, r in keyed]
    top = ranked[0]
    tier = sum(1 for r in ranked if r.n_match == top.n_match and r.cat_score == top.cat_score)
    return ranked, tier
