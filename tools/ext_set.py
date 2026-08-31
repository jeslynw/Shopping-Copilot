from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evaluator import local_evaluator as ev  # noqa: E402

CATALOG = ROOT / "data" / "catalog.jsonl"
PUBLIC = ROOT / "data" / "public_set.jsonl"
HF = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/benchmark/5core/{split}/Clothing_Shoes_and_Jewelry.test.csv"
MIX = ["buying"] * 8 + ["browsing"] * 8 + ["intent_override"] * 3 + ["boundary"]   # 40/40/15/5


def stream_lastout_targets(ids: set[str], exclude: set[str], n: int, max_rows: int = 3_000_000) -> tuple[list[str], int]:
    """Stream the last-out test split; keep the first n distinct parent_asins that are in the catalog."""
    last_err = None
    for split in ("last_out", "last_out_w_his"):
        try:
            resp = urllib.request.urlopen(HF.format(split=split), timeout=60)
        except Exception as e:  # 404 on one layout → try the other
            last_err = e
            continue
        reader = csv.reader(io.TextIOWrapper(resp, encoding="utf-8", errors="replace"))
        header = next(reader)
        col = header.index("parent_asin")
        seen: dict[str, None] = {}
        rows = 0
        for row in reader:
            rows += 1
            if len(row) > col:
                a = row[col].strip()
                if a in ids and a not in exclude and a not in seen:
                    seen[a] = None
                    if len(seen) >= n:
                        break
            if rows >= max_rows:
                break
        resp.close()
        return list(seen), rows
    raise SystemExit(f"could not open the HF split: {last_err}")


def make_samples(prefix: str, targets: list[str], profiles: list[dict], products: dict[str, dict]) -> list[dict]:
    out = []
    for i, a in enumerate(targets):
        cats = [str(c) for c in (products[a].get("categories") or [])]
        out.append({
            "sample_id": f"{prefix}_{i + 1:04d}",
            "scenario_type": MIX[i % len(MIX)],            # round-robin → exact public mix for n divisible by 20
            "category_bucket": (cats[1].lower() if len(cats) > 1 else "unknown"),
            "difficulty_bucket": "unknown",
            "user_profile": profiles[i % len(profiles)],
            "ground_truth": {"parent_asin": a},
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    ids, cats, products = ev.catalog_index(CATALOG)
    public = ev.load_jsonl(PUBLIC)
    exclude = {str(s["ground_truth"]["parent_asin"]) for s in public}
    profiles = [s["user_profile"] for s in public]

    lastout, rows = stream_lastout_targets(ids, exclude, args.n)
    print(f"last-out: scanned {rows:,} rows of the 5-core test split → {len(lastout)} distinct catalog targets", file=sys.stderr)
    pool = sorted(a for a in ids if a not in exclude)
    uniform = random.Random(args.seed).sample(pool, args.n)

    for name, targets in (("lastout", lastout), ("uniform", uniform)):
        path = ROOT / "data" / f"ext_{name}_{len(targets)}.jsonl"
        samples = make_samples(f"ext{name}", targets, profiles, products)
        path.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples), encoding="utf-8")
        pops = sorted(int(products[a].get("rating_number") or 0) for a in targets)
        print(f"wrote {path.relative_to(ROOT)}  ({len(samples)} sessions; target rating_number median {pops[len(pops) // 2]:,})",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
