"""Extraction: simulator-template regexes first, template-free clause fallback second; every constraint carries provenance.

Category resolution is against the finite vocabulary of `coarse_category()` values computed over the catalog:
exact template → longest exact token-subsequence → order-aware fuzzy (tie SET returned). Never a bag of tokens
(vocab phrases are permutations/subsets of one another — PLAN.md §5 extract.py).
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

TOKEN_RE = re.compile(r"[a-z0-9]+")
GENERIC_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "i", "in", "is", "it", "me", "my", "of",
    "on", "or", "please", "some", "that", "the", "this", "to", "want", "with", "would", "you", "looking", "im", "am",
    "we", "our", "your", "its", "he", "she", "they", "them", "so", "if", "then", "than", "there", "here", "also",
    "just", "very", "can", "could", "should", "will", "do", "does", "did", "have", "has", "had", "not", "no", "yes",
    "up", "out", "any",
}
TEMPLATE_STOP = {
    "key", "requirement", "matters", "actually", "ignore", "earlier", "preference", "need", "still", "exploring",
    "don", "additional", "judgment", "use", "options", "quite", "right", "yet", "ask", "about", "one", "specific",
    "attribute", "those", "what",
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


class CategoryMatcher:
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

    def exact(self, phrase: str) -> tuple:
        p = self.norm_set.get(norm(phrase))
        return (p,) if p else ()

    def longest_substring(self, text: str) -> tuple:
        toks = tuple(TOKEN_RE.findall(text.lower()))
        for n in sorted(self.seqs_by_len, reverse=True):
            if n > len(toks):
                continue
            windows = {toks[i:i + n] for i in range(len(toks) - n + 1)}
            for s in self.seqs_by_len[n]:
                if s in windows:
                    return tuple(self.by_seq[s])
        return ()

    def fuzzy(self, text: str, threshold: float = 0.8) -> tuple:
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

    def candidates(self, text: str, k: int = 8) -> list[str]:
        """Plausible vocab phrases for an opener: every exact token-subsequence hit plus the top fuzzy matches (for the LLM to choose from)."""
        toks = tuple(TOKEN_RE.findall(text.lower()))
        out: list[str] = []
        for n in sorted(self.seqs_by_len, reverse=True):
            if n > len(toks):
                continue
            windows = {toks[i:i + n] for i in range(len(toks) - n + 1)}
            for s in self.seqs_by_len[n]:
                if s in windows:
                    out.extend(self.by_seq[s])
        stoks = [stem(t) for t in toks if t not in GENERIC_STOP]
        scored = []
        for s in self.by_seq:
            if not s:
                continue
            ss = [stem(t) for t in s]
            best = 0.0
            for w in range(max(1, len(ss) - 1), len(ss) + 2):
                for i in range(max(1, len(stoks) - w + 1)):
                    best = max(best, difflib.SequenceMatcher(None, ss, stoks[i:i + w]).ratio())
            if best >= 0.5:
                scored.append((-best, -len(ss), s))
        for _, _, s in sorted(scored)[:k]:
            out.extend(self.by_seq[s])
        return list(dict.fromkeys(out))[:max(k, len(out) if len(out) <= k else k)]

    def match(self, text: str) -> tuple[tuple, str]:
        c = self.longest_substring(text)
        if c:
            return c, "exact"
        c = self.fuzzy(text)
        return (c, "fuzzy") if c else ((), "none")


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
    kind: str
    categories: tuple = ()
    cat_prov: str = "none"
    constraints: list = field(default_factory=list)   # [(text, provenance)]
    attribute: Optional[str] = None
    template: bool = True


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
            cat = cm.exact(g.group(1)) or cm.longest_substring(g.group(1))
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
    cats, prov = ((), "none")
    text = msg
    if turn == 1:
        cats, prov = cm.match(msg)
        for c in cats:
            text = re.sub(r"\s+".join(re.escape(t) for t in TOKEN_RE.findall(c.lower())), " ", text, flags=re.I)
    low = text.lower()
    if turn > 1 and re.search(r"preference|judgment|flexible|doesn'?t matter|not fussy|your call|nothing specific", low):
        a = ATTR_WORD.search(text)
        kind = "boundary" if re.search(r"judgment|your call|whatever you think", low) else "exhausted"
        return Parsed(kind, cats, prov, [], a.group(1).lower() if a else None, template=False)
    if turn > 1 and re.search(r"not quite right|ask me (something|about)", low):
        return Parsed("noinfo", cats, prov, [], None, template=False)
    cons = []
    for clause in re.split(r"\.\s|\.$|;\s|[!?\n]|\s[—–-]\s", BOILERPLATE.sub(" ", text)):
        c = clause.strip(" ,:-—–\"'")
        if len(c) < 3 or not TOKEN_RE.search(c.lower()) or all(t in STOP for t in TOKEN_RE.findall(c.lower())):
            continue
        cons.append((c, "clause"))
    if turn == 1:
        kind = "open_buying" if cons else "open_browsing"
    else:
        kind = "override" if re.search(r"forget|scratch|ignore|change of plans|actually|now i need|priority now", msg.lower()) else "yield"
    return Parsed(kind, cats, prov, cons, None, template=False)


def extract(msg: str, turn: int, mode: str, cm: CategoryMatcher) -> Parsed:
    if mode == "template":
        return extract_template(msg, turn, cm) or Parsed("unknown", template=False)
    if mode == "clause":
        return extract_clause(msg, turn, cm)
    return extract_template(msg, turn, cm) or extract_clause(msg, turn, cm)
