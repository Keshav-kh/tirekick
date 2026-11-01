"""C5: negotiation study. Owner: C.

  python eval/negotiation_study.py eval/data/negotiation_study.csv

surplus captured = (asking - final) / (asking - reservation): 0 = paid asking, 1 = got the seller's
secret lowest price. Walk-aways are counted separately, not as 0.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from _common import median, read_rows


def surplus(row: dict) -> float | None:
    if (row.get("walked_away") or "").lower() in {"1", "y", "yes", "true"}:
        return None
    asking, reservation, final = (int(row[k]) for k in ("asking", "reservation", "final_price"))
    if asking <= reservation:
        return None
    return (asking - final) / (asking - reservation)


def main(path: str) -> None:
    by_cond: dict[str, list[dict]] = defaultdict(list)
    for r in read_rows(path):
        by_cond[r["condition"].strip().upper()].append(r)
    for cond, label in (("H", "Student alone"), ("T", "TireKick")):
        rows = by_cond.get(cond, [])
        vals = [s for s in (surplus(r) for r in rows) if s is not None]
        walks = sum((r.get("walked_away") or "").lower() in {"1", "y", "yes", "true"} for r in rows)
        mean = sum(vals) / len(vals) if vals else None
        disc = [(int(r["asking"]) - int(r["final_price"])) / int(r["asking"]) for r in rows
                if r.get("final_price") and (r.get("walked_away") or "").lower() not in {"1", "y", "yes", "true"}]
        print(f"{label:14} n={len(rows):2}  surplus mean={mean if mean is None else round(mean, 2)} "
              f"median={median(vals) if not vals else round(median(vals), 2)}  "
              f"avg discount={round(100 * sum(disc) / len(disc), 1) if disc else '-'}%  walk-aways={walks}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/data/negotiation_study.csv")
