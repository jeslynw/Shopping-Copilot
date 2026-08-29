"""Deterministic customer-facing message with a verifiable explanation. Never asserts 'found it'."""
from __future__ import annotations

from .extract import Parsed
from .rank import Ranked
from .state import SessionState

ASK_PHRASE = {
    "feature": "Which features matter most to you?",
    "material": "Do you have a material preference?",
    "color": "Any colour you'd prefer?",
    "style": "Any style or fit preference?",
    "size": "What size do you need?",
    "use_case": "What will you mainly use it for?",
    "budget": "Do you have a budget in mind?",
}


def _q(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return f'"{text[:n]}…"' if len(text) > n else f'"{text}"'


def build_message(state: SessionState, parsed: Parsed, ask: str, top: list[Ranked], k: int, tier_size: int,
                  titles: dict) -> str:
    cat = state.categories[0] if state.categories else "what you're after"
    n = len(state.constraints)
    kind = parsed.kind
    parts: list[str] = []
    if kind == "open_buying":
        parts.append(f"Got it — {cat}, and it must have {_q(parsed.constraints[0][0]) if parsed.constraints else 'that'}.")
    elif kind == "open_browsing":
        parts.append(f"Happy to help with {cat}. Since you're still exploring, I'll start from the most popular picks.")
    elif kind == "open_override":
        parts.append(f"Got it — {cat}. I'll keep {_q(parsed.constraints[0][0]) if parsed.constraints else 'that'} in mind.")
    elif kind == "yield":
        parts.append("Noted: " + "; ".join(_q(c, 40) for c, _ in parsed.constraints[:2]) + ".")
    elif kind == "override":
        parts.append("Understood — I'll prioritise " + "; ".join(_q(c, 40) for c, _ in parsed.constraints[:2]) +
                     " (and keep your earlier notes as context).")
    elif kind == "exhausted":
        parts.append("No problem.")
    elif kind == "boundary":
        parts.append(f"Understood — I'll use my judgment on {parsed.attribute or 'that'}.")
    elif kind == "noinfo":
        parts.append("Let me narrow it down.")
    else:
        parts.append("Thanks — I've taken that on board.")
    if top:
        if k == 1 and tier_size > 10:
            parts.append(f"Many {cat} items fit everything so far, so I'm committing to my single best guess and asking one "
                         f"question to split the tie.")
        elif n:
            parts.append(f"Showing {len(top)} item{'s' if len(top) != 1 else ''} that satisfy {n} requirement{'s' if n != 1 else ''} you've stated, best-sellers first.")
        else:
            parts.append(f"Showing the {len(top)} most popular {cat} to start.")
        t0 = top[0]
        title = titles.get(t0.asin, ("", ""))[0]
        if title:
            why = f" — matched on: {'; '.join(_q(m, 30) for m in t0.matched[:3])}" if t0.matched else ""
            parts.append(f"Top pick: {' '.join(title.split())[:80]}{why}.")
    else:
        parts.append("I don't have a confident match yet.")
    parts.append(ASK_PHRASE.get(ask, "What else matters to you?"))
    return " ".join(parts)
