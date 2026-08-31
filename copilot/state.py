from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Constraint:
    text: str
    provenance: str      # template | clause
    turn: int


@dataclass
class SessionState:
    session_id: str
    turn: int = 0
    profile_tags: tuple = ()                             # user_profile.preference_tags (lowercased); read only by profile_prior
    messages: list = field(default_factory=list)
    constraints: list = field(default_factory=list)      # list[Constraint], de-duplicated by text, insertion order
    categories: tuple = ()
    cat_prov: str = "none"
    consumed: set = field(default_factory=set)
    last_asked: Optional[str] = None
    boundary_attr: Optional[str] = None
    last_yield_count: int = 0
    last_parsed: object = None
    prev: list = field(default_factory=list)            # previous turn's recommendations; [] after a fallback turn
    shown: dict = field(default_factory=dict)           # turn -> [asin] (turn5 / naive reference rules only)
    usage: tuple = (0, 0)

    def texts(self) -> set:
        return {c.text for c in self.constraints}
