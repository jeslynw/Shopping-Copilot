from __future__ import annotations

from .config import Config
from .extract import Parsed
from .state import Constraint, SessionState


def apply_reply(state: SessionState, parsed: Parsed, cfg: Config) -> list[Constraint]:
    """Update state from the parsed message; return the NEW constraints (accumulate-only, never erase)."""
    if parsed.categories and (state.turn == 1 or not state.categories):
        state.categories, state.cat_prov = tuple(parsed.categories), parsed.cat_prov
    seen = state.texts()
    new: list[Constraint] = []
    for text, prov in parsed.constraints:
        if text and text not in seen:
            c = Constraint(text, prov, state.turn)
            new.append(c)
            seen.add(text)
    state.constraints.extend(new)
    kind = parsed.kind
    state.last_yield_count = 0
    if kind == "yield" and state.last_asked:
        state.consumed.add(state.last_asked)
        state.last_yield_count = len(parsed.constraints)
    elif kind == "exhausted":
        attr = parsed.attribute or state.last_asked
        if attr:
            state.consumed.add(attr)
    elif kind == "boundary":
        attr = parsed.attribute or state.last_asked
        if cfg.boundary_reask:
            state.boundary_attr = attr
        elif attr:
            state.consumed.add(attr)
    state.last_parsed = parsed
    return new


def next_ask(state: SessionState, cfg: Config) -> str:
    """Fixed-order queue feature→material→color→style→size→use_case→budget; skip consumed; re-ask after boundary; never None."""
    if state.boundary_attr and cfg.boundary_reask and state.boundary_attr in cfg.ask_order:
        return state.boundary_attr
    if cfg.reask_on_yield2 and state.last_yield_count == 2 and state.last_asked in cfg.ask_order:
        return state.last_asked
    for a in cfg.ask_order:
        if a not in state.consumed:
            return a
    return cfg.ask_order[state.turn % len(cfg.ask_order)]


def cutoff_k(cfg: Config, state: SessionState, turn: int, tier_size: int, parsed: Parsed, top_k: int) -> int:
    r = cfg.cutoff
    if r == "none":
        return top_k
    if r == "top1":                       # degenerate reference row — never shipped
        return 1
    if not (tier_size > 10 and turn <= 3):
        return top_k
    if r == "R6":
        return 1
    if r in ("gated", "gated2"):
        all_template = all(c.provenance == "template" for c in state.constraints) and state.cat_prov in ("template", "exact")
        yielded = turn == 1 or (parsed.template and any(p == "template" for _, p in parsed.constraints))
        if r == "gated2":
            yielded = yielded or (parsed.template and parsed.kind in ("exhausted", "boundary"))
        return 1 if (all_template and yielded) else top_k
    return top_k


def exclusion(cfg: Config, state: SessionState, turn: int) -> set:
    r = cfg.exclusion
    if r == "none" or turn <= 1:
        return set()
    if r == "prev_turn":
        return set(state.prev)
    if r == "turn5":
        return {a for t, s in state.shown.items() if 4 <= t < turn for a in s} if turn >= 5 else set()
    if r == "naive":
        return {a for t, s in state.shown.items() if t < turn for a in s}
    return set()
