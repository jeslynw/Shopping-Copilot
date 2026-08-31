from __future__ import annotations

import gzip
import io
import json
import math
import sqlite3
from array import array
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .extract import CategoryMatcher, TOKEN_RE, norm, tokens

EXCLUDED_CATS = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}


def coarse_category(values: list) -> str:
    """Verbatim copy of the evaluator's coarse_category() (kept here so the agent never imports organizer code)."""
    cleaned: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if part and part.lower() not in EXCLUDED_CATS:
                cleaned.append(part)
    return " ".join(cleaned[-2:]) if cleaned else "clothing item"


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())  # intent_card form; same FTS5 tokens as "k v"
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def resolve_catalog_path(given: str | Path = "data/catalog.jsonl") -> Optional[Path]:
    """Try the given path, its .gz / non-.gz twin, relative to CWD and to the repo root (parent of this package)."""
    given = Path(given)
    names = [given]
    if given.suffix == ".gz":
        names.append(given.with_suffix(""))
    else:
        names.append(Path(str(given) + ".gz"))
    roots = [Path.cwd(), Path(__file__).resolve().parent.parent]
    for name in names:
        cands = [name] if name.is_absolute() else [r / name for r in roots]
        for c in cands:
            if c.is_file():
                return c
    return None


def _open_text(path: Path):
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic == b"\x1f\x8b":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, encoding="utf-8")


class VectorIndex:
    """TF-IDF cosine similarity route (`vector_route` ablation flag). Pure Python, deterministic, in-memory; built
    lazily on first use so the shipped configuration pays nothing. Postings over title+features+categories tokens;
    idf = log(1 + N/df); documents and the query are L2-normalised."""

    def __init__(self, con: sqlite3.Connection, rid_to_asin: dict[int, str]):
        self.asins = rid_to_asin
        by_term: dict[str, list] = defaultdict(list)
        for rid, title, feats, cats in con.execute("SELECT rowid, title, features, categories FROM products"):
            for t, f in Counter(tokens(f"{title} {feats} {cats}")).items():
                by_term[t].append((rid, f))
        n = max(len(rid_to_asin), 1)
        self.idf = {t: math.log(1.0 + n / len(ps)) for t, ps in by_term.items()}
        norm2: dict[int, float] = defaultdict(float)
        for t, ps in by_term.items():
            w = self.idf[t]
            for rid, f in ps:
                norm2[rid] += (w * f) ** 2
        self.norm = {rid: (math.sqrt(v) or 1.0) for rid, v in norm2.items()}
        self.post = {t: (array("l", [r for r, _ in ps]), array("f", [f for _, f in ps])) for t, ps in by_term.items()}

    def search(self, terms: list[str], limit: int) -> list[tuple[str, float]]:
        q = [t for t in dict.fromkeys(terms) if t in self.post]
        if not q:
            return []
        qn = math.sqrt(sum(self.idf[t] ** 2 for t in q)) or 1.0
        scores: dict[int, float] = defaultdict(float)
        for t in q:
            w2 = self.idf[t] ** 2
            rids, tfs = self.post[t]
            for rid, f in zip(rids, tfs):
                scores[rid] += w2 * f
        best = sorted(((s / (self.norm[rid] * qn), self.asins[rid]) for rid, s in scores.items()),
                      key=lambda x: (-x[0], x[1]))[:limit]
        return [(a, s) for s, a in best]


class Catalog:
    def __init__(self, path: str | Path = "data/catalog.jsonl"):
        resolved = resolve_catalog_path(path)
        if resolved is None:
            raise FileNotFoundError(f"catalog not found: {path}")
        self.path = resolved
        self.con = sqlite3.connect(":memory:")
        self.con.execute(
            "CREATE VIRTUAL TABLE products USING fts5(parent_asin UNINDEXED, title, categories, features, details, "
            "store, description, tokenize='unicode61 remove_diacritics 2')")
        self.rowid: dict[str, int] = {}
        self.pop: dict[str, int] = {}
        self.coarse: dict[str, str] = {}
        self.price: dict[str, float] = {}
        self.members: dict[str, list[str]] = defaultdict(list)
        batch = []
        rid = 0
        with _open_text(resolved) as fh:
            for line in fh:
                if not line.strip():
                    continue
                p = json.loads(line)
                asin = str(p.get("parent_asin", "")).strip()
                if not asin or asin in self.rowid:
                    continue
                rid += 1
                self.rowid[asin] = rid
                try:
                    self.pop[asin] = int(p.get("rating_number") or 0)
                except (TypeError, ValueError):
                    self.pop[asin] = 0
                c = coarse_category(p.get("categories") or [])
                self.coarse[asin] = c
                self.members[c].append(asin)
                pr = p.get("price")
                if isinstance(pr, (int, float)):
                    self.price[asin] = float(pr)
                batch.append((rid, asin, _text(p.get("title")), _text(p.get("categories")), _text(p.get("features")),
                              _text(p.get("details")), _text(p.get("store")), _text(p.get("description"))))
                if len(batch) >= 2000:
                    self.con.executemany("INSERT INTO products(rowid, parent_asin, title, categories, features, details, "
                                         "store, description) VALUES (?,?,?,?,?,?,?,?)", batch)
                    batch.clear()
        if batch:
            self.con.executemany("INSERT INTO products(rowid, parent_asin, title, categories, features, details, store, "
                                 "description) VALUES (?,?,?,?,?,?,?,?)", batch)
        self.con.execute("CREATE VIRTUAL TABLE v USING fts5vocab(products, 'row')")
        self.con.commit()
        for c in self.members.values():
            c.sort()
        self.ids = set(self.rowid)
        self.matcher = CategoryMatcher(self.members.keys())
        self._vec: Optional[VectorIndex] = None            # lazy; only the vector_route ablation builds it

    # -- retrieval ------------------------------------------------------------------------
    def df(self, terms: Iterable[str]) -> dict[str, int]:
        terms = list(dict.fromkeys(terms))
        out = {t: 0 for t in terms}
        for i in range(0, len(terms), 500):
            chunk = terms[i:i + 500]
            q = f"SELECT term, doc FROM v WHERE term IN ({','.join('?' * len(chunk))})"
            for term, doc in self.con.execute(q, chunk):
                out[term] = doc
        return out

    def search(self, terms: list[str], limit: int) -> list[tuple[str, float]]:
        safe = [t for t in dict.fromkeys(terms) if TOKEN_RE.fullmatch(t)]
        if not safe:
            return []
        expr = " OR ".join(f'"{t}"' for t in safe)
        try:
            return self.con.execute(
                "SELECT parent_asin, bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) AS s FROM products "
                "WHERE products MATCH ? ORDER BY s, parent_asin LIMIT ?", (expr, limit)).fetchall()
        except sqlite3.OperationalError:
            return []

    def vector_search(self, terms: list[str], limit: int) -> list[tuple[str, float]]:
        if self._vec is None:
            self._vec = VectorIndex(self.con, {rid: a for a, rid in self.rowid.items()})
        return self._vec.search(terms, limit)

    def titles(self, asins: list[str]) -> dict[str, str]:
        rids = [self.rowid[a] for a in asins if a in self.rowid]
        if not rids:
            return {}
        q = f"SELECT parent_asin, title, store FROM products WHERE rowid IN ({','.join('?' * len(rids))})"
        return {asin: (title, store) for asin, title, store in self.con.execute(q, rids)}

    # -- matcher text ---------------------------------------------------------------------
    def texts(self, asins: list[str], fields: str = "six") -> dict[str, str]:
        rids = [self.rowid[a] for a in asins if a in self.rowid]
        out: dict[str, str] = {}
        for i in range(0, len(rids), 900):
            chunk = rids[i:i + 900]
            q = (f"SELECT parent_asin, title, categories, features, details, store, description FROM products "
                 f"WHERE rowid IN ({','.join('?' * len(chunk))})")
            for asin, title, cats, feats, details, store, desc in self.con.execute(q, chunk):
                parts = [title, feats, details, details.replace(": ", " ")]       # both detail forms
                if fields == "six":
                    parts += [desc, cats, store]
                out[asin] = norm(" ".join(parts))
        return out
